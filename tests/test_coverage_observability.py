"""Safety checks for isolated residual attribution and the single new hypothesis."""

import importlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
m = importlib.import_module("benchmark_coverage_observability")
diagnose = importlib.import_module("diagnose_coverage_residuals")
sys.path.pop(0)
PLAN = json.loads(
    (ROOT / "docs/operations/benchmarks/2026-09-19-coverage-observability/plan.json").read_text()
)


def test_equal_luminance_color_difference_is_not_observable_in_gray():
    import cv2

    a = np.full((32, 32, 3), [200, 0, 0], np.uint8)
    b = np.full((32, 32, 3), [0, 102, 0], np.uint8)
    assert np.array_equal(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b, cv2.COLOR_RGB2GRAY))
    assert np.max(np.abs(a.astype(int) - b.astype(int))) == 200


@pytest.mark.parametrize("kind", ["small_luminance", "isoluminant_color"])
def test_localized_change_returns_unknown_without_claiming_semantic_difference(kind):
    a, b = m.controls(2050, 320, kind, PLAN["development"])
    answer = m.evaluate_relation(a, b, PLAN["protocol"])
    assert answer["relation"] == "unknown"
    assert answer["reason"] == "localized_unexplained_color_or_luminance"
    assert answer["evidence"]["largest_component"] >= 8


def test_identity_has_no_local_component():
    a, b = m.controls(2050, 320, "identity", PLAN["development"])
    answer = m.evaluate_relation(a, b, PLAN["protocol"])
    assert answer["relation"] == "cover"
    assert answer["evidence"]["largest_component"] == 0


def test_unobservable_blank_keeps_geometry_abstention():
    blank = np.zeros((64, 64, 3), np.uint8)
    answer = m.evaluate_relation(blank, blank, PLAN["protocol"])
    assert answer["relation"] == "unknown"
    assert answer["reason"] == "unchanged_geometry_or_observability_gate"


def test_diagnostic_moments_do_not_assign_content_labels():
    assert diagnose.moments(np.array([0.0, 0.0, 10.0]))["max"] == 10
    assert "relation" not in diagnose.moments(np.array([0.0, 1.0]))


def test_holdout_is_bounded_and_does_not_silently_expand():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        holdout = importlib.import_module("benchmark_observability_holdout")
    finally:
        sys.path.pop(0)
    rows = [{"event": e, "file": str(i)} for e in ["a", "b"] for i in range(3)]
    holdout.validate_rows(rows, 48)
    with pytest.raises(ValueError):
        holdout.validate_rows(rows + rows, 48)
    with pytest.raises(ValueError):
        holdout.validate_rows(rows, 1)
    with pytest.raises(ValueError):
        holdout.validate_rows(rows[:-1] + [rows[0]], 48)
