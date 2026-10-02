"""Synthetic-only controls for geometry/representation isolation and resumability."""

import copy
import importlib.util
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/benchmark_representation_control.py"
PLAN = ROOT / "docs/operations/benchmarks/2026-09-29-representation-control/protocol.json"
SPEC = importlib.util.spec_from_file_location("representation_control", SCRIPT)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def inputs(kind="identity", patch_side=4, side=320):
    params = copy.deepcopy(m.load_protocol(PLAN)["synthetic_preprocess"])
    params["small_content_patch_side"] = patch_side
    return m.controls(2049, side, kind, params)


def evaluate(kind="identity", patch_side=4, geometry_side=512, side=320):
    a, b = inputs(kind, patch_side, side)
    plan = m.load_protocol(PLAN)
    return m.evaluate_pair(
        a, b, geometry_side, 512, plan["rgb_local_parameters"], plan["quality_inputs"]
    )


def test_frozen_config_rejects_path_like_and_duplicate_kind_ids(tmp_path):
    plan = json.loads(PLAN.read_text())
    plan["cases"][0]["id"] = "../escape"
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="frozen list"):
        m.load_protocol(path)
    plan["cases"][0]["id"] = "identity"
    plan["cases"][1]["kind"] = "identity"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="frozen list"):
        m.load_protocol(path)


def test_center_aware_homography_uses_actual_unequal_shapes():
    H = np.array([[1.0, 0.1, 20.0], [0.05, 1.0, 10.0], [0.0002, 0.0001, 1.0]])
    source = np.zeros((600, 900, 3), np.uint8)
    target = np.zeros((750, 1300, 3), np.uint8)
    source_g, target_g = m.preview(source, 1024).shape[:2], m.preview(target, 1024).shape[:2]
    source_r, target_r = m.preview(source, 512).shape[:2], m.preview(target, 512).shape[:2]
    assert source_g != target_g and source_r != target_r
    converted = m.map_homography(H, source_g, target_g, source_r, target_r)
    point = np.array([80.0, 60.0, 1.0])
    out = converted @ point
    out /= out[2]
    sx, sy = source_r[1] / source_g[1], source_r[0] / source_g[0]
    tx, ty = target_r[1] / target_g[1], target_r[0] / target_g[0]
    source_center = np.array([(point[0] + 0.5) / sx - 0.5, (point[1] + 0.5) / sy - 0.5, 1.0])
    transformed = H @ source_center
    transformed /= transformed[2]
    expected = np.array([tx * (transformed[0] + 0.5) - 0.5, ty * (transformed[1] + 0.5) - 0.5])
    assert np.allclose(out[:2], expected)
    pure_scale = np.diag([tx, ty, 1]) @ H @ np.diag([1 / sx, 1 / sy, 1]) @ point
    pure_scale /= pure_scale[2]
    assert np.linalg.norm(out[:2] - pure_scale[:2]) > 0.05


@pytest.mark.parametrize("kind", ["identity", "jpeg", "small_luminance", "isoluminant_color"])
def test_actual_512_gray_matches_historical_relation(kind):
    result = evaluate(kind)
    assert result["parity_512_gray"] is True
    gray = result["arms"]["gray"]
    assert (gray["relation"], gray["reason"]) == (
        result["baseline_at_geometry"]["relation"],
        result["baseline_at_geometry"]["reason"],
    )
    if result["baseline_at_geometry"]["residual_evidence"]:
        assert gray["evidence"] == pytest.approx(
            result["baseline_at_geometry"]["residual_evidence"]
        )
    assert (
        gray["geometry_artifact_sha256"] == result["arms"]["rgb_local"]["geometry_artifact_sha256"]
    )
    assert result["arms"]["gray"]["residual_hw"] == result["arms"]["rgb_local"]["residual_hw"]


def test_rgb_residual_matches_historical_when_geometry_and_residual_both_512():
    a, b = inputs("identity")
    plan = m.load_protocol(PLAN)
    old = m.observability.evaluate_relation(a, b, {"max_side": 512, **plan["rgb_local_parameters"]})
    current = m.evaluate_pair(a, b, 512, 512, plan["rgb_local_parameters"], plan["quality_inputs"])
    assert (current["arms"]["rgb_local"]["relation"], current["arms"]["rgb_local"]["reason"]) == (
        old["relation"],
        old["reason"],
    )


def test_constructed_color_change_differentiates_representation():
    # Exact array control isolates chroma; the published four cases still use frozen JPEGs.
    a, b = inputs("identity")
    a, b = a.copy(), b.copy()
    a[100:124, 100:124] = [200, 0, 0]
    b[100:124, 100:124] = [0, 102, 0]
    assert np.array_equal(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b, cv2.COLOR_RGB2GRAY))
    plan = m.load_protocol(PLAN)
    result = m.evaluate_pair(a, b, 512, 512, plan["rgb_local_parameters"], plan["quality_inputs"])
    assert result["geometry"]["homography"] is not None
    assert result["arms"]["gray"]["relation"] == "cover"
    assert result["arms"]["rgb_local"]["relation"] == "unknown"
    assert (
        result["arms"]["gray"]["geometry_artifact_sha256"]
        == result["arms"]["rgb_local"]["geometry_artifact_sha256"]
    )


def test_geometry_is_prepared_and_related_once_for_both_arms(monkeypatch):
    a, b = inputs()
    plan = m.load_protocol(PLAN)
    counts = {"prepare": 0, "relation": 0}
    original_prepare, original_relation = m.prepare, m.relation

    def count_prepare(*args, **kwargs):
        counts["prepare"] += 1
        return original_prepare(*args, **kwargs)

    def count_relation(*args, **kwargs):
        counts["relation"] += 1
        return original_relation(*args, **kwargs)

    monkeypatch.setattr(m, "prepare", count_prepare)
    monkeypatch.setattr(m, "relation", count_relation)
    result = m.evaluate_pair(a, b, 512, 512, plan["rgb_local_parameters"], plan["quality_inputs"])
    assert counts == {"prepare": 2, "relation": 1}
    assert (
        result["arms"]["gray"]["geometry_artifact_sha256"]
        == result["arms"]["rgb_local"]["geometry_artifact_sha256"]
    )


def test_1024_cell_has_no_historical_512_parity_claim():
    result = evaluate(geometry_side=1024)
    assert result["parity_512_gray"] is None
    assert result["geometry"]["max_side"] == 1024
    assert result["arms"]["gray"]["residual_hw"][0] == [320, 320]


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    root = tmp_path_factory.mktemp("representation")
    old = m.ROOT
    m.ROOT = root
    try:
        out = root / ".local/representation-control-unit"
        result = m.run(PLAN, out)
        yield root, out, result
    finally:
        m.ROOT = old


def test_matrix_runs_all_four_cases_two_geometries_and_both_arms(completed):
    root, out, result = completed
    assert result["cases"] == 4 and result["matrix_arms"] == 16
    assert result["all_512_gray_parity"] is True
    assert result["all_arm_geometry_shared"] is True
    assert result["quality_gate"] == "not_applicable_synthetic_only"
    assert result["resource_overruns_observed"] == 0
    assert result["computed"] == 4 and result["reused"] == 0
    for case in m.load_protocol(PLAN)["cases"]:
        row = json.loads((out / f"{case['id']}.json").read_text())
        assert row["human_label_status"].startswith("none;")
        assert row["geometry_resolutions"]["1024"]["parity_512_gray"] is None
        assert (
            row["geometry_resolutions"]["512"]["arms"]["gray"]["residual_hw"]
            == row["geometry_resolutions"]["1024"]["arms"]["gray"]["residual_hw"]
        )
        assert (
            row["geometry_resolutions"]["512"]["geometry_artifact_sha256"]
            != row["geometry_resolutions"]["1024"]["geometry_artifact_sha256"]
        )
        assert not (root / "source.xmp").exists()


def test_resume_validation_and_interruption_recompute_only_missing_case(completed, monkeypatch):
    root, out, _ = completed
    monkeypatch.setattr(m, "ROOT", root)
    resumed = m.run(PLAN, out, resume=True, verify_only=True)
    assert resumed["computed"] == 0 and resumed["reused"] == 4
    interrupted = root / ".local/representation-control-interrupted"
    interrupted.mkdir(parents=True)
    for case in m.load_protocol(PLAN)["cases"][:3]:
        shutil.copy2(out / f"{case['id']}.json", interrupted / f"{case['id']}.json")
    answer = m.run(PLAN, interrupted, resume=True)
    assert answer["computed"] == 1 and answer["reused"] == 3
    assert m.run(PLAN, interrupted, resume=True, verify_only=True)["computed"] == 0
    original = json.loads((out / "summary.json").read_text())
    resumed_summary = json.loads((interrupted / "summary.json").read_text())
    assert original["case_semantic_digests"] == resumed_summary["case_semantic_digests"]
    assert original["identity"] == resumed_summary["identity"]


def test_tampered_case_or_config_cannot_be_reused(completed, tmp_path, monkeypatch):
    root, out, _ = completed
    monkeypatch.setattr(m, "ROOT", root)
    row_path = out / "identity.json"
    original = row_path.read_bytes()
    row = json.loads(original)
    row["case"]["id"] = "renamed"
    row["record_sha256"] = m.fingerprint({k: v for k, v in row.items() if k != "record_sha256"})
    row_path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="stale or corrupted"):
        m.run(PLAN, out, resume=True)
    row_path.write_bytes(original)
    copied = tmp_path / "protocol.json"
    copied.write_text(PLAN.read_text() + "\n")
    with pytest.raises(ValueError, match="stale or corrupted"):
        m.run(copied, out, resume=True)
    assert m.run(PLAN, out, resume=True, verify_only=True)["cases"] == 4


def test_overrun_case_is_saved_then_processing_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "ROOT", tmp_path)
    plan = json.loads(PLAN.read_text())
    plan["limits"]["process_rss_limit_bytes_observed"] = 1
    custom = tmp_path / "test-low-resource-limit.json"
    custom.write_text(json.dumps(plan))
    out = tmp_path / ".local/representation-control-overrun"
    with pytest.raises(ValueError, match="case saved, stop"):
        m.run(custom, out)
    row = json.loads((out / "identity.json").read_text())
    assert row["resource_overrun_observed"] is True
    assert not (out / "jpeg.json").exists() and not (out / "summary.json").exists()
    with pytest.raises(ValueError, match="case saved, stop"):
        m.run(custom, out, resume=True)


def test_rejects_output_outside_private_area(tmp_path):
    with pytest.raises(ValueError, match="output must"):
        m.run(PLAN, tmp_path / "public-results")
