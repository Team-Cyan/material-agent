"""Human evidence contracts: fixtures are synthetic, never actual human gold."""

import copy
import importlib.util
import json
from pathlib import Path

from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "human_reference", Path(__file__).parents[1] / "scripts/human_reference.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def freeze(data):
    data["freeze"]["membership_sha256"] = m.digest(m.membership(data))
    return data


def record(pair, assets, negative=False, annotator="person1"):
    def region(side, phenomenon, importance):
        return {
            "side": side,
            "box": [0.1, 0.2, 0.7, 0.8],
            "importance": importance,
            "phenomenon": phenomenon,
            "visibility": "clear",
            "description": "Constructed test evidence",
        }

    return {
        "id": f"{pair['id']}_{annotator}",
        "annotator": annotator,
        "origin": "new_human",
        "role": "independent",
        "supersedes": [],
        "revision": "test-v1",
        "started_at": "2026-09-26T10:01:00Z",
        "completed_at": "2026-09-26T10:02:00Z",
        "correspondence": "yes",
        "a_to_b": "negative" if negative else "cover",
        "b_to_a": "negative" if negative else "cover",
        "quality": {"A": "readable", "B": "readable", "preference": "tie", "reason": "Test only"},
        "regions": [
            region("A", "hand_progression", "important"),
            region("B", "hand_progression", "important"),
        ]
        if negative
        else [region("A", "illumination", "nuisance"), region("B", "exposure", "nuisance")],
        "no_visible_change": False,
        "reason": "Synthetic unit test, not a human judgment",
        "preview_hashes": {side: assets[pair[side]]["preview"]["sha256"] for side in ("A", "B")},
    }


def fixture(base=None, count=16, declared_origin="new_still"):
    data = {
        "schema": "material-agent.human-reference.v1",
        "freeze": {"at": "2026-09-26T10:00:00Z", "membership_sha256": "0" * 64},
        "annotators": [{"id": "person1", "kind": "human"}, {"id": "person2", "kind": "human"}],
        "events": [],
        "assets": [],
        "pairs": [],
    }
    for i in range(count):
        event = f"E{i:02}"
        data["events"].append(
            {
                "id": event,
                "scene_family": f"F{i:02}",
                "related_sources": [f"L{i:02}"],
                "split": "development" if i < count // 2 else "holdout",
                "origin": declared_origin,
            }
        )
        for j in range(3):
            key = f"{event}_I{j}"
            path = f"{key}.png"
            sha = m.digest(key)
            if base:
                Image.new("RGB", (40 + j, 30), (i * 10, j * 70, 80)).save(base / path)
                sha = m.file_hash(base / path)
            data["assets"].append(
                {
                    "id": key,
                    "event": event,
                    "source": {
                        "path": path,
                        "sha256": sha,
                        "permission": "Generated test fixture only",
                        "capture_time": "2026-09-25T01:00:00+08:00",
                        "capture_time_provenance": "Synthetic fixture timestamp",
                    },
                    "preview": {
                        "path": path,
                        "sha256": sha,
                        "recipe": "Synthetic PNG already oriented; no resampling",
                        "width": 40 + j,
                        "height": 30,
                        "coordinates": "normalized_xyxy_oriented_image",
                    },
                }
            )
        assets = m.indexed(data["assets"])
        for j in range(2):
            pair = {
                "id": f"{event}_P{j}",
                "A": f"{event}_I0",
                "B": f"{event}_I{j + 1}",
                "annotations": [],
            }
            pair["annotations"] = [record(pair, assets, negative=bool(j))]
            data["pairs"].append(pair)
    return freeze(data)


def test_constructed_declared_quota_is_not_human_authentication(tmp_path):
    result = m.validate(fixture(tmp_path), tmp_path, verify_files=True)
    assert result["g1"] == "quota_ready_pending_human_audit"
    assert result["human_authenticity"] == "not_machine_verifiable"
    assert result["directions"]["development"]["cover"]["directions"] == 16
    assert result["independent_families"] == 16
    assert m.validate(fixture())["g1"] == "reference_insufficient"


@pytest.mark.parametrize(
    "origin", ["historical_inspected", "synthetic", "model_generated", "video"]
)
def test_nonfresh_event_never_counts(origin):
    result = m.validate(fixture(declared_origin=origin))
    assert result["eligible_pairs"] == 0


@pytest.mark.parametrize("origin", ["historical_inspected", "synthetic", "model_generated"])
def test_nonhuman_annotation_never_counts(origin):
    data = fixture()
    for pair in data["pairs"]:
        pair["annotations"][0]["origin"] = origin
    assert m.validate(data)["eligible_pairs"] == 0


def test_missing_labels_and_fabricated_completion_cannot_pass():
    data = fixture()
    for pair in data["pairs"]:
        pair["annotations"] = []
    assert m.validate(data)["eligible_pairs"] == 0
    data["complete"] = True
    with pytest.raises(ValueError, match="missing/extra"):
        m.validate(data)


@pytest.mark.parametrize("label", ["unknown", "unjudgeable", "preference_dependent"])
def test_abstentions_do_not_satisfy_either_quota(label):
    data = fixture()
    for pair in data["pairs"]:
        pair["annotations"][0].update(a_to_b=label, b_to_a=label)
    result = m.validate(data)
    assert result["eligible_pairs"] == 0
    assert result["independent_families"] == 0
    assert result["directions"]["development"]["cover"]["directions"] == 0
    assert result["directions"]["holdout"]["negative"]["directions"] == 0
    assert result["phenomena"] == {"development": {}, "holdout": {}}


def test_abstention_padding_cannot_complete_pair_and_family_quotas(tmp_path):
    data = fixture(tmp_path)
    # Six definite pairs in three families per split meet the direction and
    # category quotas. Twenty abstention-only pairs must not fill the G1 total.
    for pair in data["pairs"]:
        if int(pair["id"][1:3]) % 8 >= 3:
            pair["annotations"][0].update(a_to_b="unknown", b_to_a="unknown")
    result = m.validate(data, tmp_path, verify_files=True)
    assert result["eligible_pairs"] == 12
    assert result["independent_families"] == 6
    assert result["g1"] == "reference_insufficient"
    assert result["missing"] == [
        "need 24..40 new human pairs; have 12",
        "need 12..20 independent scene families; have 6",
    ]


def test_one_definite_direction_counts_pair_once():
    data = fixture(count=1)
    data["pairs"][0]["annotations"][0]["b_to_a"] = "unknown"
    data["pairs"][1]["annotations"][0].update(a_to_b="unknown", b_to_a="unknown")
    result = m.validate(data)
    assert result["eligible_pairs"] == 1
    assert result["independent_families"] == 1
    assert result["directions"]["holdout"]["cover"]["directions"] == 1


@pytest.mark.parametrize("visibility", ["limited", "not_visible"])
def test_invisible_regions_never_satisfy_quota(visibility):
    data = fixture()
    for pair in data["pairs"]:
        pair["annotations"][0]["regions"][0]["visibility"] = visibility
    assert m.validate(data)["eligible_pairs"] == 0


@pytest.mark.parametrize("field", ["source", "preview"])
def test_duplicate_digests_across_splits_fail(field):
    data = fixture()
    data["assets"][-1][field]["sha256"] = data["assets"][0][field]["sha256"]
    with pytest.raises(ValueError, match="content reused"):
        m.validate(freeze(data))


@pytest.mark.parametrize("field", ["scene_family", "related_sources"])
def test_related_events_cannot_cross_split(field):
    data = fixture()
    data["events"][-1][field] = data["events"][0][field]
    with pytest.raises(ValueError, match="crosses split"):
        m.validate(freeze(data))


def test_shared_lineage_cannot_manufacture_independent_families():
    data = fixture()
    data["events"][1]["related_sources"] = data["events"][0]["related_sources"]
    with pytest.raises(ValueError, match="share scene family"):
        m.validate(freeze(data))


def test_two_directions_and_two_events_of_family_are_not_independent():
    data = fixture(count=2)
    data["events"][1].update(split="development", scene_family="F00")
    result = m.validate(freeze(data))
    assert result["directions"]["development"]["cover"]["directions"] == 4
    assert result["directions"]["development"]["cover"]["families"] == ["F00"]
    assert result["independent_families"] == 1


def test_history_in_same_family_excludes_new_claim():
    data = fixture(count=2)
    data["events"][1].update(split="development", scene_family="F00", origin="historical_inspected")
    assert m.validate(freeze(data))["eligible_pairs"] == 0


@pytest.mark.parametrize("key", ["annotator", "preview_hashes", "started_at", "regions"])
def test_required_provenance_is_not_optional(key):
    data = fixture(count=1)
    del data["pairs"][0]["annotations"][0][key]
    with pytest.raises(ValueError):
        m.validate(data)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda r: r.update(completed_at=r["started_at"]), "completion"),
        (lambda r: r.update(started_at="2026-09-26T09:00:00Z"), "predates"),
        (lambda r: r["preview_hashes"].update(A="0" * 64), "preview identity"),
        (lambda r: r["regions"][0].update(box=[0.8, 0.2, 0.4, 0.6]), "positive area"),
        (lambda r: r["regions"][0].update(box=[-0.1, 0.2, 0.4, 0.6]), "invalid number"),
        (lambda r: r.update(regions=[]), "localized"),
        (lambda r: r.update(no_visible_change=True), "conflicts"),
    ],
)
def test_invalid_provenance_or_regions_fail(mutation, match):
    data = fixture(count=1)
    mutation(data["pairs"][0]["annotations"][0])
    with pytest.raises(ValueError, match=match):
        m.validate(data)


def test_bytes_dimensions_and_orientation_checked(tmp_path):
    data = fixture(tmp_path, count=1)
    m.validate(data, tmp_path, True)
    data["assets"][0]["preview"]["width"] = 999
    with pytest.raises(ValueError, match="dimension"):
        m.validate(freeze(data), tmp_path, True)
    data = fixture(tmp_path, count=1)
    (tmp_path / data["assets"][0]["source"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        m.validate(data, tmp_path, True)


def empty_annotations(data):
    for pair in data["pairs"]:
        pair["annotations"] = []
    return data


def export_for(data, annotator, negative=False):
    mapping = m.bundle_mapping(data, "holdout", annotator)
    pair_id = next(iter(mapping["mapping"].values()))
    pair = m.indexed(data["pairs"])[pair_id]
    return mapping, {
        "bundle": mapping["bundle"],
        "annotations": [
            {"pair": "P001", "record": record(pair, m.indexed(data["assets"]), negative, annotator)}
        ],
    }


def test_independent_bundles_merge_sequentially_preserves_disagreement():
    data = empty_annotations(fixture(count=1))
    first_map, first_export = export_for(data, "person1")
    second_map, second_export = export_for(data, "person2", True)
    result = m.merge(m.merge(data, first_map, first_export), second_map, second_export)
    assert len(result["pairs"][0]["annotations"]) == 2
    assert m.validate(result)["unresolved_pairs"] == ["E00_P0"]
    assert data["pairs"][0]["annotations"] == []
    with pytest.raises(ValueError, match="duplicate id"):
        m.merge(result, first_map, first_export)
    assert len(result["pairs"][0]["annotations"]) == 2


def test_adjudication_references_raw_disagreement_and_requires_later_time():
    data = fixture(count=1)
    pair = data["pairs"][0]
    pair["annotations"].append(record(pair, m.indexed(data["assets"]), True, "person2"))
    judgment = copy.deepcopy(pair["annotations"][0])
    judgment.update(
        id="adjudicated",
        role="adjudication",
        supersedes=[r["id"] for r in pair["annotations"]],
        started_at="2026-09-26T11:00:00Z",
        completed_at="2026-09-26T11:01:00Z",
    )
    pair["annotations"].append(judgment)
    assert m.validate(data)["unresolved_pairs"] == []
    judgment["supersedes"].pop()
    assert m.validate(data)["unresolved_pairs"] == ["E00_P0"]


@pytest.mark.parametrize("what", ["membership", "annotator", "preview", "bundle", "mapping"])
def test_export_rejects_stale_or_wrong_identity(what):
    data = empty_annotations(fixture(count=1))
    mapping, exported = export_for(data, "person1")
    if what == "membership":
        data["events"][0]["scene_family"] = "Changed"
        freeze(data)
    elif what == "preview":
        data["assets"][0]["preview"]["sha256"] = "1" * 64
        freeze(data)
    elif what == "annotator":
        exported["annotations"][0]["record"]["annotator"] = "person2"
    elif what == "bundle":
        exported["bundle"] = "wrong"
    else:
        mapping["mapping"]["P001"] = "E00_P1"
    with pytest.raises(ValueError):
        m.merge(data, mapping, exported)


def test_blinded_viewer_has_no_private_metadata_or_existing_labels(tmp_path, monkeypatch):
    data = fixture(tmp_path, count=2, declared_origin="synthetic")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    output = tmp_path / ".local/viewer.html"
    m.render(data, tmp_path, "development", "person2", output)
    html = output.read_text()
    assert "data:image/png;base64," in html
    for secret in [
        "Generated test fixture only",
        "E00_I0.png",
        "scene_family",
        "synthetic",
        "Synthetic unit test",
    ]:
        assert secret not in html
    payload = json.loads(html.split("const payload = ", 1)[1].split(";\n", 1)[0])
    assert len(payload["panels"]) == 2  # holdout excluded
    mapping = json.loads(output.with_suffix(".mapping.json").read_text())
    assert mapping["mapping"] == {"P001": "E00_P0", "P002": "E00_P1"}
    with pytest.raises(ValueError, match="overwrite"):
        m.render(data, tmp_path, "development", "person2", output)


def test_output_is_local_only_and_empty_data_insufficient(tmp_path):
    with pytest.raises(ValueError, match="repository .local"):
        m.local_output(tmp_path / "public.html")
    data = fixture(count=0)
    assert m.validate(data)["g1"] == "reference_insufficient"


def test_partial_merge_resume_skips_own_judgments_but_not_others(tmp_path, monkeypatch):
    data = empty_annotations(fixture(tmp_path, count=1, declared_origin="synthetic"))
    mapping, exported = export_for(data, "person1")
    merged = m.merge(data, mapping, exported)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    output = tmp_path / ".local/resume.html"
    m.render(merged, tmp_path, "holdout", "person1", output)
    html = output.read_text()
    payload = json.loads(html.split("const payload = ", 1)[1].split(";\n", 1)[0])
    assert [p["id"] for p in payload["panels"]] == ["P002"]
    other = tmp_path / ".local/other.html"
    m.render(merged, tmp_path, "holdout", "person2", other)
    payload2 = json.loads(other.read_text().split("const payload = ", 1)[1].split(";\n", 1)[0])
    assert len(payload2["panels"]) == 2
    pair = merged["pairs"][1]
    export2 = {
        "bundle": mapping["bundle"],
        "annotations": [{"pair": "P002", "record": record(pair, m.indexed(merged["assets"]))}],
    }
    completed = m.merge(merged, mapping, export2)
    with pytest.raises(ValueError, match="no unannotated pairs"):
        m.render(completed, tmp_path, "holdout", "person1", tmp_path / ".local/done.html")


def test_model_identity_never_counts_as_human():
    data = fixture()
    data["annotators"][0]["kind"] = "model"
    assert m.validate(data)["eligible_pairs"] == 0


@pytest.mark.parametrize("kind", ["source", "preview"])
def test_renamed_content_pair_does_not_inflate_quota(kind):
    data = fixture(count=1)
    duplicate = copy.deepcopy(data["assets"][1])
    duplicate["id"] = "renamed"
    if kind == "preview":
        duplicate["source"]["sha256"] = "1" * 64
    data["assets"].append(duplicate)
    pair = {"id": "duplicate_pair", "A": data["assets"][0]["id"], "B": "renamed", "annotations": []}
    data["pairs"].append(pair)
    with pytest.raises(ValueError, match=f"duplicate {kind} content pair"):
        m.validate(freeze(data))


def test_preview_orientation_and_icc_rejected(tmp_path):
    data = fixture(tmp_path, count=1)
    asset = data["assets"][0]
    path = tmp_path / asset["preview"]["path"]
    im = Image.new("RGB", (40, 30))
    exif = Image.Exif()
    exif[274] = 6
    im.save(path, exif=exif)
    for kind in ("source", "preview"):
        asset[kind]["sha256"] = m.file_hash(path)
    for pair in data["pairs"]:
        pair["annotations"][0]["preview_hashes"]["A"] = asset["preview"]["sha256"]
    with pytest.raises(ValueError, match="orientation applied"):
        m.validate(freeze(data), tmp_path, True)
    im.save(path, icc_profile=b"non-srgb")
    for kind in ("source", "preview"):
        asset[kind]["sha256"] = m.file_hash(path)
    with pytest.raises(ValueError, match="sRGB"):
        m.validate(freeze(data), tmp_path, True)


def test_render_strips_metadata_without_changing_source(tmp_path, monkeypatch):
    import base64
    import io

    data = empty_annotations(fixture(tmp_path, count=1, declared_origin="synthetic"))
    asset = data["assets"][0]
    path = tmp_path / asset["preview"]["path"]
    with Image.open(path) as original:
        im = original.copy()
    exif = Image.Exif()
    exif[270] = "private source metadata"
    im.save(path, exif=exif)
    before = m.file_hash(path)
    for kind in ("source", "preview"):
        asset[kind]["sha256"] = before
    freeze(data)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    output = tmp_path / ".local/stripped.html"
    m.render(data, tmp_path, "holdout", "person1", output)
    payload = json.loads(output.read_text().split("const payload = ", 1)[1].split(";\n", 1)[0])
    png = payload["panels"][0]["images"]["A"].split(",", 1)[1]
    with Image.open(io.BytesIO(base64.b64decode(png))) as shown:
        assert not shown.getexif()
    assert m.file_hash(path) == before
    with Image.open(path) as original:
        assert original.getexif()[270] == "private source metadata"
