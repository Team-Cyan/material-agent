"""Spatial consensus is conditional evidence, never forced majority truth."""

import copy
import importlib.util
from pathlib import Path
import pytest

SPEC = importlib.util.spec_from_file_location(
    "spatial_reference", Path(__file__).parents[1] / "scripts/assess_spatial_reference.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def row(panel, index=1, category="object", importance="important", label="different"):
    ids = [f"{panel}{index:02}L", f"{panel}{index:02}R"]
    return {
        "ids": ids,
        "same_scene": "yes",
        "regions": [
            {
                "left_box": [0.1, 0.2, 0.4, 0.5],
                "right_box": [0.2, 0.2, 0.5, 0.5],
                "description": "visible change",
                "category": category,
                "visibility": "clear",
                "importance": importance,
                "confidence": 0.9,
                "reason": "visible evidence",
            }
        ],
        "directed_relations": [
            {
                "source": a,
                "target": b,
                "reference": label,
                "confidence": 0.9,
                "reason": "visible evidence",
            }
            for a, b in [ids, ids[::-1]]
        ],
        "preference_required": False,
        "uncertainty": "none",
        "reference_source": "model_generated",
    }


def fixture():
    a = row("A")
    b = row("B")
    b["regions"][0]["left_box"], b["regions"][0]["right_box"] = (
        a["regions"][0]["right_box"],
        a["regions"][0]["left_box"],
    )
    return {"pairs": [{"pair_id": "P01", "scene_id": "one"}]}, [a], [b]


def test_reverse_display_order_maps_corresponding_regions():
    inputs, a, b = fixture()
    result = m.assess(inputs, a, b)
    assert result["pairs"][0]["agreed_regions"][0]["minimum_box_iou"] == 1
    assert result["pairs"][0]["relations"][0]["reference"] == "different"
    assert result["summary"]["feasible_for_next_research_proposal"] is False


def test_relation_disagreement_is_unknown_not_majority():
    inputs, a, b = fixture()
    b[0]["directed_relations"][1]["reference"] = "cover"
    result = m.assess(inputs, a, b)
    assert result["pairs"][0]["relations"][0]["reference"] == "unknown"


@pytest.mark.parametrize(
    "field,value", [("confidence", 0.5), ("visibility", "limited"), ("importance", "nuisance")]
)
def test_weak_or_inconsistent_region_is_not_agreed(field, value):
    inputs, a, b = fixture()
    b[0]["regions"][0][field] = value
    assert m.assess(inputs, a, b)["pairs"][0]["agreed_regions"] == []


def test_nonoverlapping_boxes_do_not_manufacture_agreement():
    inputs, a, b = fixture()
    b[0]["regions"][0]["left_box"] = [0.8, 0.8, 0.9, 0.9]
    assert m.assess(inputs, a, b)["pairs"][0]["agreed_regions"] == []


def test_preference_in_either_panel_requires_user_reference():
    inputs, a, b = fixture()
    b[0]["regions"][0]["importance"] = "preference_dependent"
    result = m.assess(inputs, a, b)
    assert result["summary"]["preference_required_pairs"] == 1
    assert (
        result["summary"]["decision"]
        == "stop_algorithm_experiments_and_request_minimal_sample_preference"
    )


def test_invalid_or_incomplete_panel_rejected():
    _, a, _ = fixture()
    with pytest.raises(ValueError, match="incomplete"):
        m.validate_panel(a, "A", 2)
    altered = copy.deepcopy(a)
    altered[0]["regions"][0]["left_box"] = [0, 0, 2, 1]
    with pytest.raises(ValueError, match="box"):
        m.validate_panel(altered, "A", 1)


def test_null_boxes_do_not_agree_and_iou_is_bounded():
    assert m.iou(None, None) == 0
    assert m.iou([0, 0, 1, 1], [0, 0, 1, 1]) == 1
    assert m.iou([0, 0, 0.1, 0.1], [0.5, 0.5, 1, 1]) == 0


def test_category_agreement_does_not_bypass_minimum_sample_budget():
    inputs = {"pairs": [{"pair_id": str(i), "scene_id": str(i)} for i in range(4)]}
    cats = ["water", "illumination", "gesture", "object"]
    a = [row("A", i + 1, c, "nuisance" if i < 2 else "important") for i, c in enumerate(cats)]
    b = []
    for i, item in enumerate(reversed(a)):
        other = row("B", i + 1, item["regions"][0]["category"], item["regions"][0]["importance"])
        other["regions"][0]["left_box"], other["regions"][0]["right_box"] = (
            item["regions"][0]["right_box"],
            item["regions"][0]["left_box"],
        )
        b.append(other)
    summary = m.assess(inputs, a, b)["summary"]
    assert all(summary["required_category_coverage"].values())
    assert not summary["feasible_for_next_research_proposal"]
