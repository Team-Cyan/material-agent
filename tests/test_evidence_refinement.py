from unittest.mock import Mock
from types import SimpleNamespace

import numpy as np

import pytest

from material_agent.domain.evidence_refinement import face_eye_evidence, refine_group
from material_agent.domain.scoring_engine import _build_layered_signals, ScoreBundle
from material_agent.utils.config_validator import normalize_config, validate_config


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"detection": {"faces": []}},
        {"subject_context": {"label": "back_view", "confidence": 1.0}},
        {
            "subject_context": {
                "label": "silhouette",
                "confidence": 0.2,
                "source": "annotator",
                "evidence": "outline",
            }
        },
    ],
)
def test_missing_face_or_unreliable_context_is_unknown(meta):
    assert face_eye_evidence(meta)["status"] == "unknown"
    assert face_eye_evidence(meta)["value"] is None


@pytest.mark.parametrize("label", ["back_view", "silhouette"])
def test_not_applicable_requires_explicit_supported_context(label):
    context = {
        "label": label,
        "confidence": 0.95,
        "source": "fixture_annotation",
        "evidence_type": "visual_annotation",
        "evidence": "visible body outline",
    }
    assert face_eye_evidence({"subject_context": context})["status"] == "not_applicable"
    # Measured eye regions take precedence over a conflicting context label.
    result = face_eye_evidence(
        {"subject_context": context, "subject_focus": {"eye_focus_score": 0.0}}
    )
    assert result["status"] == "observed" and result["value"] == 0.0


def test_missing_eye_evidence_never_turns_generic_low_sharpness_into_eye_failure():
    meta = {"detection": {"faces": []}}
    signals = _build_layered_signals(
        scores={"sharpness": 0, "subject": 0, "clarity": 0},
        meta=meta,
        scene="people",
        config={"portrait_face_eye": {"enabled": True}},
    )
    assert not any(s["signal_key"] == "portrait_face_eye_usability" for s in signals)
    assert meta["face_eye_evidence"]["status"] == "unknown"


def candidate(score=5):
    return {
        "score_total": score,
        "scene": "people",
        "decision": "review",
        "meta": {},
        "scores": {"sharpness": score},
    }


def test_refinement_budgets_attempts_and_retains_baseline_on_failure():
    original = [("a", candidate()), ("b", candidate()), ("c", candidate())]
    refine = Mock(side_effect=ValueError("fixture"))
    result = refine_group(original, config={"enabled": True, "max_candidates": 1}, refine=refine)
    refine.assert_called_once()
    assert result[0][1]["score_total"] == 5
    assert result[0][1]["meta"]["refinement"]["status"] == "failed"
    assert result[1][1]["meta"]["refinement"]["status"] == "budget_exhausted"
    assert result[0][1]["meta"]["refinement"]["before"]["scores"] == {"sharpness": 5}
    assert original[0][1]["meta"] == {}
    assert refine_group(result, config={"enabled": True}, refine=refine) == result
    refine.assert_called_once()  # no recursive or repeated attempt


def test_refinement_time_budget_stops_new_work_and_records_overrun():
    clock_values = iter([0, 0, 7, 7, 7])
    refine = Mock(return_value=candidate(6))
    result = refine_group(
        [("a", candidate()), ("b", candidate())],
        config={"enabled": True, "max_seconds": 5},
        refine=refine,
        clock=lambda: next(clock_values),
    )
    assert refine.call_count == 1
    assert result[0][1]["meta"]["refinement"]["budget_overrun"] is True
    assert result[1][1]["meta"]["refinement"]["status"] == "budget_exhausted"
    assert result[0][1]["meta"]["refinement"]["review_required"] is True


def test_refinement_disabled_or_unambiguous_does_not_decode():
    refine = Mock()
    rows = [("a", {**candidate(8), "scene": "city"}), ("b", {**candidate(2), "scene": "city"})]
    assert refine_group(rows, config={}, refine=refine) == rows
    assert refine_group(rows, config={"enabled": True}, refine=refine) == rows
    refine.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_candidates", 9),
        ("max_seconds", float("nan")),
        ("score_gap", -1),
        ("focus_max_size", 8192),
    ],
)
def test_refinement_config_has_hard_bounds(field, value, capsys):
    cfg = normalize_config(
        {"scorers": {}, "focus_integrity": {"selective_refinement": {field: value}}}
    )
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert f"selective_refinement.{field}" in capsys.readouterr().out


@pytest.mark.parametrize("larger", [True, False])
def test_runtime_refines_using_bounded_raw_preview_before_group_selection(monkeypatch, larger):
    from material_agent.app import review_runtime

    config = normalize_config(
        {
            "focus_integrity": {"selective_refinement": {"enabled": True, "max_candidates": 1}},
            "grouping": {"enabled": True},
        }
    )
    monkeypatch.setattr(review_runtime, "make_client", lambda _: object())
    monkeypatch.setattr(review_runtime, "make_fast_screening_port", lambda _: None)
    decoder = Mock(
        return_value=SimpleNamespace(focus_gray=np.zeros((24, 24) if larger else (8, 8)))
    )
    monkeypatch.setattr(review_runtime, "decode_raw", decoder)

    async def compute(*args, **kwargs):
        return ScoreBundle(
            scores={"sharpness": 1.0},
            total=1.0,
            boosted=False,
            meta={},
            scene="people",
            scene_raw="",
            instructions="",
            decision="reject",
            decision_reasons=["blur"],
        )

    monkeypatch.setattr(review_runtime, "compute_scores", compute)
    executor = review_runtime.build_review_job_executor(
        repository=Mock(), config=config, state=Mock(), progress=Mock(), dry_run=True
    )
    original = candidate()
    original["meta"]["focus_preview_size"] = [16, 16]
    rows = executor.review_job.finalize_group([("a", original)], group_id="g")
    assert decoder.call_args.args[1]["prefer_embedded"] is False
    assert decoder.call_args.args[1]["focus_max_size"] == 3072
    assert rows[0][1]["decision"] == "keep"  # coverage still applies to refined quality
    assert rows[0][1]["score_total"] == (1.0 if larger else 5.0)
    assert rows[0][1]["meta"]["quality_assessment"]["decision"] == (
        "reject" if larger else "review"
    )
    assert rows[0][1]["meta"]["refinement"]["status"] == (
        "completed" if larger else "no_resolution_gain"
    )


def test_no_resolution_gain_retains_original_quality():
    from material_agent.domain.evidence_refinement import NoRefinementGain

    original = candidate(7)
    refined = refine_group(
        [("a", original)], config={"enabled": True}, refine=Mock(side_effect=NoRefinementGain())
    )[0][1]
    assert refined["score_total"] == 7
    assert refined["meta"]["refinement"]["status"] == "no_resolution_gain"
    assert refined["meta"]["refinement"]["review_required"] is True


def test_invalid_refined_evidence_rolls_back_entire_candidate():
    original = candidate(7)
    invalid = {**candidate(1), "meta": {"face_eye_evidence": {"invalid": True}}}
    result = refine_group(
        [("a", original)], config={"enabled": True}, refine=Mock(return_value=invalid)
    )[0][1]
    assert result["meta"]["refinement"]["status"] == "failed"
    assert result["score_total"] == 7
    assert result["scores"] == original["scores"]
    assert "refinement" not in invalid["meta"]
