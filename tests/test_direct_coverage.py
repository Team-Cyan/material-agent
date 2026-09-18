"""Offline coverage safety and failure-mode regressions; no photo writes."""

import importlib.util
import itertools
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "direct_coverage", Path(__file__).parents[1] / "scripts/direct_coverage.py"
)
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)
P = m.Protocol()


def frame(key, total=50, sharpness=50, exposure=50, seconds=0):
    return {
        "id": key,
        "seconds": seconds,
        "quality": dict(total=total, sharpness=sharpness, exposure=exposure),
    }


def edges(*pairs):
    return {pair: {"relation": "cover"} for pair in pairs}


def texture():
    rng = np.random.default_rng(761)
    gray = rng.integers(35, 215, (320, 320), dtype=np.uint8)
    gray = cv2.GaussianBlur(gray, (3, 3), 0.5)
    return np.repeat(gray[..., None], 3, axis=2)


def test_direct_witness_does_not_use_transitive_chain():
    fs = [frame("a", 90), frame("b", 80), frame("c", 70)]
    es = edges(("a", "b"), ("b", "c"))
    ds = m.select(fs, es, P)
    assert ds["b"] == {"decision": "reject", "covered_by": "a"}
    assert ds["c"]["decision"] == "keep"
    assert m.audit(ds, es, {})["structural_violations"] == []


def test_cycles_never_reject_every_frame_and_permutations_are_stable():
    fs = [frame(k) for k in "abc"]
    es = edges(*itertools.permutations("abc", 2))
    expected = m.select(fs, es, P)
    assert [k for k, v in expected.items() if v["decision"] == "keep"] == ["a"]
    for ordering in itertools.permutations(fs):
        assert m.select(ordering, es, P) == expected


@pytest.mark.parametrize("quality", [dict(sharpness=10), dict(exposure=10), dict(total=None)])
def test_higher_degree_or_total_cannot_override_quality(quality):
    keeper = frame("a", 90)
    keeper["quality"].update(quality)
    fs = [keeper, frame("b", 80), frame("c", 70)]
    ds = m.select(fs, edges(("a", "b"), ("a", "c")), P)
    assert ds["b"]["decision"] == "keep"


def test_quality_alone_cannot_authorize_reject():
    assert all(
        v["decision"] == "keep" for v in m.select([frame("a", 90), frame("b", 10)], {}, P).values()
    )


def test_external_false_coverage_is_separate_from_structural_integrity():
    es = edges(("a", "b"))
    ds = m.select([frame("a"), frame("b")], es, P)
    audit = m.audit(ds, es, {("a", "b"): "different"})
    assert audit["structural_violations"] == []
    assert audit["false_covered_rejects"] == ["b"]
    assert m.audit(ds, es, {})["unjudged_rejects"] == ["b"]
    ds["a"]["decision"] = "reject"
    assert "b" in m.audit(ds, es, {})["structural_violations"]


def test_insertion_and_deletion_can_change_distant_witnesses():
    fs = [frame("a", 90), frame("b", 80), frame("c", 70)]
    es = edges(("a", "b"), ("b", "c"), ("x", "a"))
    before = m.select(fs, es, P)
    after = m.select(fs + [frame("x", 100)], es, P)
    assert before["c"]["decision"] == "keep"
    assert after["c"] == {"decision": "reject", "covered_by": "b"}
    assert m.select(fs, es, P) == before


def test_candidate_hash_bypass_time_and_global_caps():
    fs = [frame("a", seconds=0), frame("b", seconds=1), frame("c", seconds=20)]
    fs[0]["hash_distance"] = 64  # deliberately irrelevant to eligibility
    assert m.candidates(fs, P) == ([("a", "b")], 0)
    p = m.Protocol(max_pairs=1)
    assert m.candidates([frame(k, seconds=i) for i, k in enumerate("abcd")], p) == ([("a", "b")], 5)
    with pytest.raises(ValueError, match="duplicate"):
        m.candidates([frame("a"), frame("a")], P)
    with pytest.raises(ValueError, match="frame budget"):
        m.candidates(fs, m.Protocol(max_frames=2))


@pytest.mark.parametrize("kw", [{"max_pairs": 1.1}, {"ratio": 2}, {"max_seconds": float("nan")}])
def test_invalid_budget_rejected(kw):
    with pytest.raises(ValueError):
        m.Protocol(**kw)


def test_identity_and_moderate_exposure_are_supported():
    rgb = texture()
    a = m.prepare(rgb, P)
    assert m.relation(a, a, P)["relation"] == "cover"
    b = m.prepare((rgb.astype(float) * 0.7 + 10).astype(np.uint8), P)
    assert m.relation(a, b, P)["relation"] == "cover"


def test_blank_and_feature_failure_abstain(monkeypatch):
    blank = m.prepare(np.zeros((128, 128, 3), np.uint8), P)
    assert m.relation(blank, blank, P)["relation"] == "unknown"

    def fail(**kwargs):
        raise cv2.error("detector unavailable")

    monkeypatch.setattr(cv2, "SIFT_create", fail)
    a = m.prepare(texture(), P)
    assert m.relation(a, a, P)["reason"] == "opencv_feature_failure"


def test_local_change_is_unexplained_not_semantic_uniqueness():
    rgb = texture()
    altered = rgb.copy()
    altered[120:152, 120:152] = 60
    result = m.relation(m.prepare(rgb, P), m.prepare(altered, P), P)
    assert result["relation"] == "unknown"
    assert result["reason"] == "unexplained_local_change"


def test_exhausted_time_budget_keeps_every_frame():
    fs = [dict(frame(k), rgb=texture()) for k in "ab"]
    result = m.run(fs, m.Protocol(max_seconds=1e-12))
    assert result["budget_exceeded"]
    assert all(d["decision"] == "keep" for d in result["decisions"].values())


def test_global_pair_cap_insertion_displaces_unrelated_later_candidate():
    fs = [frame(k, seconds=i) for i, k in enumerate("abcd")]
    p = m.Protocol(max_pairs=2, neighbors_forward=1)
    before, _ = m.candidates(fs, p)
    after, _ = m.candidates([frame("x", seconds=-1)] + fs, p)
    assert ("b", "c") in before and ("b", "c") not in after


def test_component_merge_does_not_create_direct_cover_witness():
    fs = [frame("a", 90), frame("b", 80), frame("c", 70), frame("d", 60)]
    before = edges(("a", "b"), ("c", "d"))
    merged = {**before, **edges(("b", "c"))}
    assert m.select(fs, before, P) == m.select(fs, merged, P)
    assert m.select(fs, merged, P)["c"]["decision"] == "keep"


def test_full_geometry_recompute_is_permutation_stable():
    fs = [dict(frame(k, seconds=i), rgb=texture()) for i, k in enumerate("abc")]
    first = m.run(fs, P)
    reverse = m.run(list(reversed(fs)), P)
    assert first["decisions"] == reverse["decisions"]
    assert {k: v["relation"] for k, v in first["edges"].items()} == {
        k: v["relation"] for k, v in reverse["edges"].items()
    }


def benchmark_module():
    script_dir = str(Path(__file__).parents[1] / "scripts")
    sys.path.insert(0, script_dir)
    try:
        import benchmark_direct_coverage

        return benchmark_direct_coverage
    finally:
        sys.path.remove(script_dir)


def test_same_action_is_never_a_positive_coverage_reference():
    runner = benchmark_module()
    fs = [
        dict(frame("a"), actions=["cut"]),
        dict(frame("b"), actions=["cut"]),
        dict(frame("c"), actions=["peel"]),
    ]
    refs = runner.references({}, fs)
    assert refs["a", "b"] == "unknown"
    assert refs["a", "c"] == "different"


def test_metrics_separate_witness_integrity_from_unique_loss():
    runner = benchmark_module()
    fs = [frame("a"), frame("b")]
    es = edges(("a", "b"))
    ds = m.select(fs, es, P)
    result = runner.metrics(fs, ds, es, {("a", "b"): "different"})
    assert result["structural_violations"] == []
    assert result["false_covered_rejects"] == ["b"]
    assert result["final_unique_content_loss"] is True
    assert result["extra_retention"] is None
    unknown = runner.metrics(fs, ds, es, {})
    assert unknown["final_unique_content_loss"] is None


def test_expired_case_budget_aborts_before_more_work():
    runner = benchmark_module()
    with pytest.raises(TimeoutError):
        runner.remaining_protocol(
            P, 0, {"case_wall_seconds": 0.01, "process_peak_rss_bytes": 2_000_000_000}
        )
