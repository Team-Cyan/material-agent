import numpy as np

from material_agent.app.aesthetic_calibration_service import fit_aesthetic_calibration
from material_agent.domain.aesthetic_calibration import (
    calibrate_aesthetic_score,
    calibrate_signals_for_rescore,
)


def _config(**profiles):
    return {
        "enabled": True,
        "policy_version": "portrait-v1",
        "minimum_label_count": 3,
        "pivot": 5.5,
        "profiles": profiles,
    }


def test_exact_target_profile_precedes_scene_and_blends_detection_confidence():
    result = calibrate_aesthetic_score(
        6.0,
        scene="people",
        detection={"primary_subject": {"label": "person", "confidence": 0.8}},
        config=_config(
            person={"scale": 1.0, "offset": 2.0, "label_count": 10},
            people={"scale": 1.0, "offset": -2.0, "label_count": 10},
        ),
    )
    assert result["profile"] == "person"
    assert result["blend"] == 0.8
    assert result["effective_score"] == 7.6
    assert result["applied"] is True


def test_scene_profile_is_used_without_detection():
    result = calibrate_aesthetic_score(
        6.0,
        scene="animals",
        detection=None,
        config=_config(animals={"scale": 1.0, "offset": 1.25, "label_count": 3}),
    )
    assert result["profile"] == "animals"
    assert result["blend"] == 1.0
    assert result["effective_score"] == 7.25


def test_undertrained_exact_profile_falls_back_to_trained_scene_profile():
    result = calibrate_aesthetic_score(
        6.0,
        scene="people",
        detection={"primary_subject": {"label": "person", "confidence": 0.9}},
        config=_config(
            person={"scale": 1.0, "offset": 2.0, "label_count": 2},
            people={"scale": 1.0, "offset": 1.0, "label_count": 3},
        ),
    )
    assert result["profile"] == "people"
    assert result["blend"] == 1.0
    assert result["effective_score"] == 7.0


def test_low_confidence_target_cannot_select_exact_profile():
    result = calibrate_aesthetic_score(
        6.0,
        scene="people",
        detection={"primary_subject": {"label": "tv", "confidence": 0.4}},
        config={
            **_config(
                tv={"scale": 1.0, "offset": -2.0, "label_count": 10},
                people={"scale": 1.0, "offset": 1.0, "label_count": 10},
            ),
            "minimum_target_confidence": 0.6,
        },
    )
    assert result["target"] == "tv"
    assert result["profile"] == "people"
    assert result["effective_score"] == 7.0


def test_insufficient_labels_are_an_explicit_noop():
    result = calibrate_aesthetic_score(
        6.0,
        scene="people",
        detection={"primary_subject": {"label": "person", "confidence": 0.99}},
        config=_config(person={"scale": 1.5, "offset": 2.0, "label_count": 2}),
    )
    assert result["reason"] == "insufficient_labels"
    assert result["effective_score"] == 6.0
    assert result["applied"] is False


def test_fit_recovers_target_affine_profile_and_reports_insufficient_groups():
    raw = np.linspace(3.0, 8.5, 8)
    items = [
        {
            "target": "person",
            "raw_score": value,
            "human_score": 5.5 + 1.2 * (value - 5.5) + 0.4,
        }
        for value in raw
    ]
    items.append({"target": "dog", "raw_score": 6.0, "human_score": 7.0})
    config, report = fit_aesthetic_calibration(
        {"items": items}, minimum_label_count=4, policy_version="fitted-v1"
    )
    assert config["profiles"]["person"] == {
        "scale": 1.2,
        "offset": 0.4,
        "label_count": 8,
    }
    assert "dog" not in config["profiles"]
    assert report["targets"]["person"]["rmse_after"] == 0.0
    assert report["targets"]["dog"]["status"] == "insufficient_labels"


def test_fit_rejects_profile_without_raw_score_variation():
    items = [
        {"target": "person", "raw_score": 6.0, "human_score": score}
        for score in (4.0, 5.0, 7.0, 8.0)
    ]
    config, report = fit_aesthetic_calibration(
        {"items": items}, minimum_label_count=4, minimum_raw_span=1.0
    )
    assert config["profiles"] == {}
    assert report["targets"]["person"]["status"] == "insufficient_raw_span"


def test_fit_omits_identity_profile_when_raw_score_already_matches_human_score():
    items = [
        {"target": "person", "raw_score": score, "human_score": score}
        for score in (3.0, 5.0, 7.0, 9.0)
    ]
    config, report = fit_aesthetic_calibration({"items": items}, minimum_label_count=4)
    assert config["profiles"] == {}
    assert report["targets"]["person"]["status"] == "no_improvement"


def test_rescore_rebuilds_effective_signal_from_raw_using_scene_profile():
    signals = [
        {
            "stage": "aesthetic",
            "signal_key": "overall_aesthetic_raw",
            "value": 6.0,
            "confidence": 1.0,
            "source": "learned_model",
            "model_name": "nima",
            "model_version": "raw-v1",
        },
        {
            "stage": "aesthetic",
            "signal_key": "overall_aesthetic",
            "value": 6.0,
            "confidence": 1.0,
            "source": "learned_model",
        },
    ]
    rebuilt = calibrate_signals_for_rescore(
        signals,
        scene="people",
        config=_config(people={"scale": 1.0, "offset": 1.0, "label_count": 3}),
    )
    effective = next(signal for signal in rebuilt if signal["signal_key"] == "overall_aesthetic")
    assert effective["value"] == 7.0
    assert effective["source"] == "target_calibration"
    assert effective["model_version"] == "portrait-v1"
