from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "public_composite", Path(__file__).parents[1] / "scripts/benchmark_public_composite.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture(tmp_path):
    root = tmp_path / "inputs"
    root.mkdir()
    for name, color in (("a", "gray"), ("b", "red"), ("q", "gray")):
        Image.new("RGB", (16, 16), color).save(root / f"{name}.png")
    payload = {"schema_version": module.SCHEMA, "items": [
        {"id": "a", "path": "a.png", "track": "koniq", "target": 1},
        {"id": "b", "path": "b.png", "track": "koniq", "target": 3},
        {"id": "g", "path": "a.png", "track": "copydays", "role": "gallery", "source_id": "1"},
        {"id": "q", "path": "q.png", "track": "copydays", "role": "query", "source_id": "1"}],
        "album_tasks": [{"id": "t", "task_type": "intent_selection", "album_id": "album",
                         "image_ids": ["1"], "target": {"selected_images": ["1"]}}]}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload))
    return root, manifest, payload


def test_native_metrics_use_join_and_tie_corrected_ranks():
    items = [{"id": str(i), "track": "koniq", "target": target}
             for i, target in enumerate((1, 2, 2, 4))]
    records = {str(i): {"status": "ok", "score": target}
               for i, target in enumerate((1, 2, 2, 4))}
    result = module.native_metrics(items, records, [])
    assert result["koniq"]["srocc"] == pytest.approx(1)
    assert result["koniq"]["plcc"] == pytest.approx(1)
    assert module.ranks([2, 1, 2]) == [1.5, 0, 1.5]
    assert module.correlation([1, 1], [1, 2]) is None


def test_copy_correspondence_is_not_path_order_or_quality():
    items = [
        {"id": "g0", "track": "copydays", "role": "gallery", "source_id": "wrong"},
        {"id": "g1", "track": "copydays", "role": "gallery", "source_id": "right"},
        {"id": "q", "track": "copydays", "role": "query", "source_id": "right"}]
    records = {"g0": {"status": "ok", "phash": "f" * 16},
               "g1": {"status": "ok", "phash": "0" * 16},
               "q": {"status": "ok", "phash": "0" * 16}}
    assert module.native_metrics(items, records, [1])["copydays"]["top1"] == 1
    records["g1"] = {"status": "error"}
    result = module.native_metrics(items, records, [1])
    assert result["copydays"]["evaluated_queries"] == 0
    assert result["copydays"]["top1"] is None
    assert result["albumbench"]["status"] == "unsupported"


def test_resume_input_change_and_failure_retry(tmp_path, monkeypatch):
    root, manifest, _ = fixture(tmp_path)
    output = tmp_path / "output"
    first = module.run(manifest, root, output)
    assert first["cache_reused"] == 0
    second = module.run(manifest, root, output)
    assert second["cache_reused"] == 4
    assert second["identity"] == first["identity"]
    assert second["tracks"] == first["tracks"]
    (root / "b.png").write_bytes(b"broken")
    third = module.run(manifest, root, output)
    assert third["cache_reused"] == 3
    assert third["tracks"]["koniq"]["failed"] == 1
    called = []
    original = module.extract

    async def spy(data, client):
        called.append(True)
        return await original(data, client)

    monkeypatch.setattr(module, "extract", spy)
    fourth = module.run(manifest, root, output)
    assert fourth["cache_reused"] == 3
    assert len(called) == 1


@pytest.mark.parametrize("mutation", [
    lambda p: p["items"][0].update(path="../manifest.json"),
    lambda p: p["items"][0].update(target=float("inf")),
    lambda p: p["items"][0].update(target=True),
    lambda p: p["items"][0].update(track="unknown"),
    lambda p: p["items"][1].update(id="a"),
    lambda p: p["items"][3].update(source_id="missing"),
    lambda p: p["items"][2].update(role="invalid"),
    lambda p: p.update(album_tasks=[{"id": "t"}]),
])
def test_invalid_inputs_fail_before_writing(tmp_path, mutation):
    root, manifest, payload = fixture(tmp_path)
    mutation(payload)
    manifest.write_text(json.dumps(payload))
    output = tmp_path / "out"
    with pytest.raises(ValueError):
        module.run(manifest, root, output)
    assert not output.exists()


def test_output_input_overlap_and_symlink_escape(tmp_path):
    root, manifest, payload = fixture(tmp_path)
    with pytest.raises(ValueError, match="output must not contain"):
        module.run(manifest, root, root)
    (root / "escape").symlink_to(manifest)
    payload["items"][0]["path"] = "escape"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="escapes root"):
        module.run(manifest, root, tmp_path / "out")


def test_selection_is_order_independent_and_preserves_gallery(tmp_path):
    _, _, payload = fixture(tmp_path)
    selected = module.select_items(payload["items"], 1)
    assert selected == module.select_items(list(reversed(payload["items"])), 1)
    assert {i["id"] for i in selected} >= {"g", "q"}
    assert len(selected) == 3
    for invalid in (0, 4097, True, float("inf")):
        with pytest.raises(ValueError):
            module.select_items(payload["items"], invalid)


def test_kadid_native_direction_and_distortion_breakdown():
    items = [{"id": str(i), "track": "kadid", "target": target, "distortion": "01"}
             for i, target in enumerate((1, 3, 5))]
    records = {str(i): {"status": "ok", "score": target}
               for i, target in enumerate((1, 3, 5))}
    metric = module.native_metrics(items, records, [])["kadid"]
    assert metric["target_direction"] == "higher is better"
    assert metric["srocc"] == pytest.approx(1)
    assert metric["per_distortion"]["01"]["srocc"] == pytest.approx(1)


def test_corrupt_cache_recomputed_and_input_fingerprint_changes(tmp_path):
    root, manifest, _ = fixture(tmp_path)
    output = tmp_path / "out"
    first = module.run(manifest, root, output)
    cache = output / "features" / (module.digest(b"b") + ".json")
    record = json.loads(cache.read_text())
    record["score"] = float("nan")
    cache.write_text(json.dumps(record))
    recovered = module.run(manifest, root, output)
    assert recovered["cache_reused"] == 3
    assert recovered["tracks"] == first["tracks"]
    Image.new("RGB", (16, 16), "blue").save(root / "b.png")
    changed = module.run(manifest, root, output)
    assert changed["identity"] != first["identity"]
    assert changed["config_identity"] == first["config_identity"]


@pytest.mark.parametrize("location", ["root", "features", "cache", "part"])
def test_output_symlinks_cannot_overwrite_source(tmp_path, location):
    root, manifest, _ = fixture(tmp_path)
    output = tmp_path / "out"
    source = root / "a.png"
    before = source.read_bytes()
    if location == "root":
        output.symlink_to(root, target_is_directory=True)
    else:
        output.mkdir()
        if location == "features":
            (output / "features").symlink_to(root, target_is_directory=True)
        elif location == "cache":
            (output / "features").mkdir()
            (output / "features" / (module.digest(b"a") + ".json")).symlink_to(source)
        else:
            (output / "checkpoint.json.part").symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        module.run(manifest, root, output)
    assert source.read_bytes() == before


def test_atomic_json_exclusive_temporary_never_follows_old_part(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"unchanged")
    target = tmp_path / "result.json"
    target.with_suffix(".json.part").symlink_to(source)
    module.atomic_json(target, {"ok": True})
    assert source.read_bytes() == b"unchanged"
    assert json.loads(target.read_text()) == {"ok": True}


def test_any_failed_gallery_invalidates_copy_metric():
    items = [
        {"id": "g0", "track": "copydays", "role": "gallery", "source_id": "wrong"},
        {"id": "g1", "track": "copydays", "role": "gallery", "source_id": "right"},
        {"id": "q", "track": "copydays", "role": "query", "source_id": "right"}]
    records = {"g0": {"status": "error"},
               "g1": {"status": "ok", "phash": "0" * 16},
               "q": {"status": "ok", "phash": "0" * 16}}
    metric = module.native_metrics(items, records, [])["copydays"]
    assert metric["status"] == "incomplete"
    assert metric["gallery_failed_count"] == 1
    assert metric["top1"] is None
    assert metric["mrr"] is None


def test_frozen_sha_mismatch_prevents_all_output(tmp_path):
    root, manifest, payload = fixture(tmp_path)
    for item in payload["items"]:
        item["sha256"] = module.digest((root / item["path"]).read_bytes())
    manifest.write_text(json.dumps(payload))
    (root / "q.png").write_bytes(b"changed")
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        module.run(manifest, root, output)
    assert not output.exists()


def test_valid_frozen_hashes_allow_resume(tmp_path):
    root, manifest, payload = fixture(tmp_path)
    for item in payload["items"]:
        item["sha256"] = module.digest((root / item["path"]).read_bytes())
    manifest.write_text(json.dumps(payload))
    first = module.run(manifest, root, tmp_path / "out")
    second = module.run(manifest, root, tmp_path / "out")
    assert first["identity"] == second["identity"]
    assert second["cache_reused"] == 4
