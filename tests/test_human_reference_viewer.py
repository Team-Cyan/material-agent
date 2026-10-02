"""Execute the real template handlers under Node mocks; never browser/download acceptance."""

import base64
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

HARNESS = Path(__file__).with_name("human_reference_viewer_harness.mjs")
NODE = shutil.which("node")
SPEC = importlib.util.spec_from_file_location(
    "human_reference_test_fixtures", Path(__file__).with_name("test_human_reference.py")
)
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
empty_annotations, fixture, m = fixtures.empty_annotations, fixtures.fixture, fixtures.m


@pytest.fixture
def bundle(tmp_path):
    manifest = empty_annotations(fixture(tmp_path, count=1, declared_origin="synthetic"))
    mapping = m.bundle_mapping(manifest, "holdout", "person1")
    pairs, assets = m.indexed(manifest["pairs"]), m.indexed(manifest["assets"])
    panels = []
    for neutral, pair_id in mapping["mapping"].items():
        pair = pairs[pair_id]
        panels.append(
            {
                "id": neutral,
                "hashes": {s: assets[pair[s]]["preview"]["sha256"] for s in ("A", "B")},
                "images": {
                    s: "data:image/png;base64,"
                    + base64.b64encode(
                        (tmp_path / assets[pair[s]]["preview"]["path"]).read_bytes()
                    ).decode()
                    for s in ("A", "B")
                },
            }
        )
    return (
        manifest,
        mapping,
        {"bundle": mapping["bundle"], "annotator": "person1", "panels": panels},
    )


def run(bundle, *actions):
    if NODE is None:
        pytest.skip("Installed Node is required for template handler unit tests")
    result = subprocess.run(
        [NODE, str(HARNESS)],
        input=json.dumps({"payload": bundle[2], "actions": actions}),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def fill(values, event="input"):
    return {"op": "fill", "values": values, "event": event}


def click(key):
    return {"op": "click", "id": key}


def last(result):
    return result["snapshots"][-1]


def judged(**overrides):
    return fill(
        {
            "correspondence": "yes",
            "a_to_b": "cover",
            "b_to_a": "cover",
            "qualityA": "readable",
            "qualityB": "readable",
            "preference": "B",
            "qualityReason": "Independent synthetic quality assessment",
            "reason": "Synthetic handler test; not actual human reference",
            "no_visible_change": True,
            **overrides,
        }
    )


def region(**overrides):
    return fill(
        {
            "importance": "important",
            "phenomenon": "object_state",
            "visibility": "clear",
            "description": "Unique target detail in constructed fixture",
            **overrides,
        }
    )


def pointer(event, x=125, y=125, side="B", **kwargs):
    return {"op": "pointer", "event": event, "side": side, "x": x, "y": y, **kwargs}


def drag(side="B"):
    # Mock image rect is left=50, top=75, width=300, height=200.
    return [pointer("pointerdown", 125, 125, side), pointer("pointerup", 275, 225, side)]


def exported(result):
    assert len(result["blob_outputs"]) == 1
    output = result["blob_outputs"][0]
    assert output["type"] == "application/json"
    return json.loads(output["text"])


@pytest.mark.parametrize("field", ["reason", "qualityReason", "description"])
def test_input_before_blur_protects_unsaved_text(bundle, field):
    result = run(bundle, fill({field: "Still typing; no blur or change"}), {"op": "beforeunload"})
    assert last(result)["unload"] == {"prevented": True, "returnValue": ""}


def test_empty_form_and_empty_export_are_rejected(bundle):
    result = run(bundle, {"op": "beforeunload"}, click("save"), click("export"))
    assert result["snapshots"][1]["unload"]["prevented"] is False
    assert "Complete every judgment" in result["snapshots"][2]["status"]
    assert "No saved annotations" in last(result)["status"]
    assert result["blob_outputs"] == []


@pytest.mark.parametrize("action", ["next", "previous", "export"])
@pytest.mark.parametrize("field", ["reason", "qualityReason", "description"])
def test_unsaved_input_blocks_navigation_and_export(bundle, action, field):
    result = run(bundle, judged(), click("save"), fill({field: "Uncommitted edit"}), click(action))
    assert "Save " in last(result)["status"]
    assert last(result)["progress"].startswith("P001")
    assert last(result)["fields"][field] == "Uncommitted edit"
    assert result["blob_outputs"] == []


def test_change_event_still_marks_select_and_checkbox_dirty(bundle):
    result = run(
        bundle,
        fill({"correspondence": "unknown", "no_visible_change": True}, "change"),
        click("next"),
    )
    assert "before navigating" in last(result)["status"]
    assert last(result)["no_visible_change"] is True


def test_saved_export_shape_and_python_merge_with_synthetic_exclusion(bundle, tmp_path):
    result = run(bundle, judged(), click("save"), {"op": "beforeunload"}, click("export"))
    data = exported(result)
    assert set(data) == {"bundle", "annotations"}
    assert data["bundle"] == bundle[1]["bundle"]
    assert data["annotations"][0]["pair"] == "P001"
    row = data["annotations"][0]["record"]
    assert row["preview_hashes"] == bundle[2]["panels"][0]["hashes"]
    assert row["annotator"] == "person1"
    assert row["started_at"] < row["completed_at"]
    assert row["regions"] == [] and row["no_visible_change"] is True
    assert result["snapshots"][-2]["unload"]["prevented"] is True
    assert last(result)["anchors"] == [
        {"href": "mock-object-1", "filename": "human-annotations.json"}
    ]
    assert result["revoked"] == ["mock-object-1"]
    merged = m.merge(bundle[0], bundle[1], data)
    report = m.validate(merged, tmp_path, verify_files=True)
    assert report["schema_valid"] and report["files_verified"]
    assert report["eligible_pairs"] == 0
    assert report["g1"] == "reference_insufficient"
    assert bundle[0]["pairs"][0]["annotations"] == []


@pytest.mark.parametrize(
    "rect,start,end",
    [
        ({"left": 50, "top": 75, "width": 300, "height": 200}, (125, 125), (275, 225)),
        ({"left": 100, "top": 150, "width": 600, "height": 400}, (550, 450), (250, 250)),
    ],
)
def test_scaled_drag_and_reverse_drag_normalize_to_image(bundle, rect, start, end):
    result = run(
        bundle, region(), pointer("pointerdown", *start, rect=rect), pointer("pointerup", *end)
    )
    assert last(result)["regions"][0]["box"] == [0.25, 0.25, 0.75, 0.75]
    assert last(result)["boxes"] == [
        {"side": "photoB", "style": {"left": "25%", "top": "25%", "width": "50%", "height": "50%"}}
    ]


def test_drag_clamps_to_image_boundary(bundle):
    result = run(bundle, region(), pointer("pointerdown", -10, -10), pointer("pointerup", 999, 999))
    assert last(result)["regions"][0]["box"] == [0, 0, 1, 1]


def test_pointer_cancel_and_orphan_pointerup_do_not_create_regions(bundle):
    result = run(
        bundle,
        region(),
        pointer("pointerup"),
        pointer("pointerdown"),
        pointer("pointercancel"),
        pointer("pointerup", 200, 200),
    )
    assert last(result)["regions"] == []
    assert last(result)["boxes"] == []


def test_zero_area_drag_rejected_and_does_not_poison_next_drag(bundle):
    result = run(bundle, region(), pointer("pointerdown"), pointer("pointerup"), *drag())
    assert "nonempty region" in result["snapshots"][3]["status"]
    assert len(last(result)["regions"]) == 1


@pytest.mark.parametrize("missing", ["importance", "phenomenon", "visibility", "description"])
def test_incomplete_region_is_rejected(bundle, missing):
    result = run(bundle, region(**{missing: " " if missing == "description" else ""}), *drag())
    assert "Choose region labels" in last(result)["status"]
    assert last(result)["regions"] == []


def test_negative_target_region_and_independent_quality_survive_merge(bundle, tmp_path):
    result = run(
        bundle,
        judged(
            a_to_b="negative",
            b_to_a="cover",
            preference="A",
            qualityB="unknown",
            no_visible_change=False,
        ),
        region(),
        *drag("A"),
        click("save"),
        click("clearRegions"),
        *drag("B"),
        click("save"),
        click("export"),
    )
    assert "important region on target B" in result["snapshots"][5]["status"]
    row = exported(result)["annotations"][0]["record"]
    assert (row["a_to_b"], row["b_to_a"], row["quality"]["preference"]) == (
        "negative",
        "cover",
        "A",
    )
    assert row["quality"]["B"] == "unknown"
    assert row["regions"][0]["side"] == "B"
    assert row["regions"][0]["box"] == [0.25, 0.25, 0.75, 0.75]
    assert (
        m.validate(m.merge(bundle[0], bundle[1], exported(result)), tmp_path, True)[
            "eligible_pairs"
        ]
        == 0
    )


@pytest.mark.parametrize(
    "values,reason",
    [
        ({"correspondence": "unknown"}, "judgeable correspondence"),
        ({"no_visible_change": False}, "Mark evidence regions"),
        ({"a_to_b": "negative"}, "No visible change conflicts"),
        ({"reason": "   "}, "Complete every judgment"),
        ({"qualityReason": "   "}, "Complete every judgment"),
    ],
)
def test_inconsistent_or_incomplete_judgment_rejected(bundle, values, reason):
    result = run(bundle, judged(**values), click("save"))
    assert reason in last(result)["status"]
    assert "0 saved" in last(result)["progress"]


def test_saved_pair_revisit_restores_fields_regions_and_stable_export(bundle):
    result = run(
        bundle,
        judged(no_visible_change=False),
        region(importance="nuisance"),
        *drag(),
        click("save"),
        click("next"),
        judged(
            a_to_b="unknown",
            b_to_a="unjudgeable",
            correspondence="unjudgeable",
            no_visible_change=False,
            preference="unknown",
        ),
        click("save"),
        click("previous"),
        click("export"),
    )
    row = last(result)
    assert row["progress"].startswith("P001") and "2 saved" in row["progress"]
    assert row["fields"]["a_to_b"] == "cover"
    assert row["fields"]["preference"] == "B"
    assert row["regions"][0]["importance"] == "nuisance"
    assert len(row["boxes"]) == 1
    data = exported(result)
    assert [r["pair"] for r in data["annotations"]] == ["P001", "P002"]
    assert data["annotations"][1]["record"]["a_to_b"] == "unknown"
    assert data["annotations"][1]["record"]["regions"] == []
