from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "public_nima", Path(__file__).parents[1] / "scripts/benchmark_public_nima.py"
)
nima = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nima)


def fixture(tmp_path):
    root = tmp_path / "inputs"
    root.mkdir()
    items = []
    for track in ("koniq", "kadid"):
        for index in range(4):
            name = f"{track}-{index}.png"
            Image.new("RGB", (16, 16), (index * 50, 20, 20)).save(root / name)
            item = {"id": f"{track}:{index}", "path": name, "track": track,
                    "target": index + 1, "sha256": nima.hash_file(root / name)}
            if track == "kadid":
                item["group"] = f"I{index // 2:02d}.png"
            items.append(item)
    payload = {"schema_version": nima.base.SCHEMA, "items": items}
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(payload))
    baseline = tmp_path / "baseline" / "report.json"
    parent = nima.base.run(manifest, root, baseline.parent)
    model = tmp_path / "model.tflite"
    model.write_bytes(b"\x18\x00\x00\x00TFL3mock weights")
    plan = nima.freeze_protocol(payload, parent, nima.hash_file(model), "test-v1")
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(plan))
    output = tmp_path / "output"
    return root, manifest, baseline, protocol, model, output


def prediction(model_sha, revision, score=5.5):
    return {"model_digest": model_sha, "model_version": revision,
            "execution": {"model": {"revision": revision}, "status": "success",
                          "lifecycle": "shared_openvino", "fallback": {"kind": "none"},
                          "execution_devices": ["CPU"], "execution_device_readback": "actual",
                          "requested_device": "CPU", "compiled_device": "CPU",
                          "batch": {"actual": 1, "fallback": False}},
            "runtime": "openvino", "fallback_used": False,
            "execution_device_readback": "actual", "execution_devices": ["CPU"],
            "batch_size_actual": 1, "compiled_device": "CPU", "score": score,
            "distribution": [0.1] * 10}


def fake_adapter(monkeypatch, calls):
    class Fake:
        def __init__(self, config):
            assert config["device"] == "CPU"
            assert config["batch_size"] == 1
            assert config["fallback_device"] == ""
            self.config = config

        async def score_image(self, data):
            calls.append(data)
            return prediction(nima.hash_file(Path(self.config["model_path"])),
                              self.config["model_version"])
    monkeypatch.setattr(nima, "OpenVinoNimaAestheticAdapter", Fake)


def test_frozen_comparison_resume_cache_integrity_and_observational_timing(tmp_path, monkeypatch):
    args = fixture(tmp_path)
    calls = []
    fake_adapter(monkeypatch, calls)
    first = nima.run(*args)
    assert len(calls) == 8
    assert first["tracks"]["koniq"]["all"]["status"] == "complete"
    assert first["tracks"]["kadid"]["comparison"]["total"] == 2
    calls.clear()
    second = nima.run(*args)
    assert not calls
    assert second["cache_reused"] == 8
    assert first["semantic_records_sha256"] == second["semantic_records_sha256"]
    cache = next((args[-1] / "predictions").glob("*.json"))
    record = json.loads(cache.read_text())
    record["score"] = 1
    cache.write_text(json.dumps(record))
    third = nima.run(*args)
    assert len(calls) == 1
    assert third["cache_reused"] == 7
    assert third["semantic_records_sha256"] == first["semantic_records_sha256"]
    calls.clear()
    cache.write_text("broken JSON")
    assert nima.run(*args)["cache_reused"] == 7
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(fallback_used=True),
    lambda p: p.update(model_digest="stale"),
    lambda p: p.update(execution_devices=["GPU"]),
    lambda p: p.update(execution_device_readback="unknown"),
    lambda p: p.update(score=float("nan")),
    lambda p: p.update(distribution=[0.2] * 10),
    lambda p: p.update(score=7),
    lambda p: p["execution"].update(status="fallback"),
    lambda p: p["execution"].update(requested_device="AUTO"),
    lambda p: p["execution"]["batch"].update(fallback=True),
])
def test_no_fallback_or_invalid_distribution_can_score(mutation):
    result = prediction("abc", "v1")
    mutation(result)
    with pytest.raises(ValueError):
        nima.normalize_prediction(result, "abc", "v1")


@pytest.mark.parametrize("change", ["model", "protocol", "input", "feature"])
def test_stale_input_fails_before_any_output(tmp_path, change):
    args = fixture(tmp_path)
    root, manifest, baseline, protocol, model, output = args
    if change == "model":
        model.write_bytes(b"changed model")
    elif change == "protocol":
        plan = json.loads(protocol.read_text())
        plan["parent_baseline_identity"] = "changed"
        protocol.write_text(json.dumps(plan))
    elif change == "input":
        next(root.glob("*.png")).write_bytes(b"changed input")
    else:
        cache = next((baseline.parent / "features").glob("*.json"))
        record = json.loads(cache.read_text())
        record["score"] = 10
        cache.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        nima.preflight(*args)
    assert not output.exists()


def test_kadid_reference_family_never_crosses_splits(tmp_path):
    args = fixture(tmp_path)
    plan = json.loads(args[3].read_text())
    family = [item for item in plan["items"] if item["id"] in {"kadid:0", "kadid:1"}]
    family[0]["split"] = "development"
    family[1]["split"] = "comparison"
    args[3].write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="reference group crosses"):
        nima.preflight(*args)


def test_frozen_protocol_requires_exact_parent_cohort_and_recipe(tmp_path):
    args = fixture(tmp_path)
    plan = json.loads(args[3].read_text())
    plan["items"].pop()
    args[3].write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="exact baseline quality cohort"):
        nima.preflight(*args)


def test_paired_metrics_have_same_denominator_and_null_incomplete_delta():
    items = [{"id": str(i), "track": "koniq", "split": "comparison", "target": i + 1}
             for i in range(3)]
    baseline = {"0": 3, "1": 2, "2": 1}
    records = {"0": {"status": "ok", "score": 1}, "1": {"status": "error"},
               "2": {"status": "ok", "score": 3}}
    metric = nima.metrics(items, baseline, records)["koniq"]["comparison"]
    assert metric["baseline_full"]["n"] == 3
    assert metric["baseline_paired"]["n"] == metric["nima_paired"]["n"] == 2
    assert metric["delta"] == {"plcc": None, "srocc": None}
    records["1"] = {"status": "ok", "score": 2}
    complete = nima.metrics(items, baseline, records)["koniq"]["all"]
    assert complete["delta"]["srocc"] == pytest.approx(2)


def test_output_symlinks_and_overlap_preserve_source(tmp_path):
    args = fixture(tmp_path)
    source = next(args[0].glob("*.png"))
    before = source.read_bytes()
    args[-1].mkdir()
    (args[-1] / "checkpoint.json.part").symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        nima.preflight(*args)
    assert source.read_bytes() == before
    with pytest.raises(ValueError, match="overlaps"):
        nima.preflight(*args[:-1], args[2].parent / "unsafe")


def test_record_hash_ignores_only_elapsed_time():
    record = {"status": "ok", "score": 5.5, "elapsed_ms": 1}
    before = nima.record_hash(record)
    record["elapsed_ms"] = 999
    assert nima.record_hash(record) == before
    record["score"] = 6
    assert nima.record_hash(record) != before


def test_runtime_fallback_failures_are_counted_and_retried(tmp_path, monkeypatch):
    args = fixture(tmp_path)
    calls = []

    class Fallback:
        def __init__(self, config):
            self.config = config

        async def score_image(self, data):
            calls.append(True)
            result = prediction(nima.hash_file(Path(self.config["model_path"])),
                                self.config["model_version"])
            result["fallback_used"] = True
            return result

    monkeypatch.setattr(nima, "OpenVinoNimaAestheticAdapter", Fallback)
    report = nima.run(*args)
    assert len(calls) == 8
    assert report["tracks"]["koniq"]["all"]["failed"] == 4
    assert report["tracks"]["koniq"]["all"]["nima_paired"]["n"] == 0
    assert report["tracks"]["koniq"]["all"]["baseline_full"]["n"] == 4
    assert report["tracks"]["koniq"]["all"]["delta"]["srocc"] is None
    calls.clear()
    assert nima.run(*args)["cache_reused"] == 0
    assert len(calls) == 8


def test_partition_recipe_independent_of_input_order(tmp_path):
    _, manifest, baseline, protocol, model, _ = fixture(tmp_path)
    payload = json.loads(manifest.read_text())
    parent = json.loads(baseline.read_text())
    payload["items"].reverse()
    parent["selected_ids"].reverse()
    assert nima.freeze_protocol(payload, parent, nima.hash_file(model), "test-v1") == json.loads(
        protocol.read_text())


def test_only_bounded_single_file_tflite_models_are_accepted(tmp_path):
    args = fixture(tmp_path)
    other = tmp_path / "model.xml"
    other.write_bytes(b"weights require a companion BIN")
    with pytest.raises(ValueError, match="single-file TFLite"):
        nima.preflight(*args[:4], other, args[-1])
    with args[-2].open("wb") as handle:
        handle.truncate(50_000_001)
    with pytest.raises(ValueError, match="50000000 bytes"):
        nima.preflight(*args)
    assert not args[-1].exists()


def test_renamed_external_model_cannot_pass_tflite_guard(tmp_path):
    args = fixture(tmp_path)
    args[-2].write_bytes(b"<?xml version='1.0'?> companion weights")
    with pytest.raises(ValueError, match="TFL3 header"):
        nima.preflight(*args)
    assert not args[-1].exists()
