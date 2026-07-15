from __future__ import annotations

from typing import Any


def calibrate_aesthetic_score(
    raw_score: float,
    *,
    scene: str,
    detection: dict | None,
    config: dict | None,
) -> dict[str, Any]:
    """Apply a versioned, label-backed affine calibration to a NIMA score.

    Exact detected-object profiles take precedence over scene and default
    profiles. Object-profile adjustments are confidence blended so uncertain
    detections cannot fully rewrite the aesthetic score.
    """

    calibration = config if isinstance(config, dict) else {}
    raw = _clamp(float(raw_score))
    policy_version = str(calibration.get("policy_version", "target-affine-v1"))
    minimum_label_count = int(calibration.get("minimum_label_count", 20))
    pivot = float(calibration.get("pivot", 5.5))
    profiles = calibration.get("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}

    primary = detection.get("primary_subject") if isinstance(detection, dict) else None
    target = str(primary.get("label", "")).strip() if isinstance(primary, dict) else ""
    confidence = (
        _unit_interval(float(primary.get("confidence", 0.0)))
        if isinstance(primary, dict)
        else 0.0
    )
    profile_candidates = [
        key for key in (target, scene, "default") if key and isinstance(profiles.get(key), dict)
    ]
    profile_key = next(
        (
            key
            for key in profile_candidates
            if int(profiles[key].get("label_count", 0)) >= minimum_label_count
        ),
        profile_candidates[0] if profile_candidates else None,
    )
    provenance: dict[str, Any] = {
        "policy_version": policy_version,
        "raw_score": round(raw, 4),
        "effective_score": round(raw, 4),
        "scene": scene,
        "target": target or None,
        "target_confidence": round(confidence, 4) if target else None,
        "profile": profile_key,
        "applied": False,
    }
    if not bool(calibration.get("enabled", False)):
        provenance["reason"] = "disabled"
        return provenance
    if profile_key is None:
        provenance["reason"] = "no_profile"
        return provenance

    profile = profiles[profile_key]
    scale = float(profile.get("scale", 1.0))
    offset = float(profile.get("offset", 0.0))
    label_count = int(profile.get("label_count", 0))
    provenance.update(
        {
            "scale": scale,
            "offset": offset,
            "pivot": pivot,
            "label_count": label_count,
            "minimum_label_count": minimum_label_count,
        }
    )
    if label_count < minimum_label_count:
        provenance["reason"] = "insufficient_labels"
        return provenance

    calibrated = _clamp(pivot + scale * (raw - pivot) + offset)
    blend = confidence if profile_key == target and target else 1.0
    effective = _clamp(raw + blend * (calibrated - raw))
    provenance["blend"] = round(blend, 4)
    provenance["effective_score"] = round(effective, 4)
    if abs(effective - raw) < 1e-9:
        provenance["reason"] = "identity_profile"
        return provenance
    provenance["applied"] = True
    provenance["reason"] = "calibrated"
    return provenance


def calibrate_signals_for_rescore(
    signals: list[dict], *, scene: str, config: dict | None
) -> list[dict]:
    """Rebuild effective NIMA signal from persisted raw score for rescoring.

    Detection metadata is not stored in the signal table, so rescoring safely
    uses the scene/default profile. A fresh full run can use exact object labels.
    """

    raw_signal = next(
        (
            signal
            for signal in signals
            if signal.get("stage") == "aesthetic"
            and signal.get("signal_key") == "overall_aesthetic_raw"
        ),
        None,
    )
    if raw_signal is None:
        return signals
    calibration = calibrate_aesthetic_score(
        float(raw_signal["value"]), scene=scene, detection=None, config=config
    )
    rebuilt = [
        signal
        for signal in signals
        if not (
            signal.get("stage") == "aesthetic"
            and signal.get("signal_key") == "overall_aesthetic"
        )
    ]
    rebuilt.append(
        {
            **raw_signal,
            "signal_key": "overall_aesthetic",
            "value": calibration["effective_score"],
            "source": "target_calibration" if calibration["applied"] else "learned_model",
            "model_version": (
                calibration["policy_version"]
                if calibration["applied"]
                else raw_signal.get("model_version")
            ),
        }
    )
    return rebuilt


def _clamp(value: float) -> float:
    return max(1.0, min(10.0, value))


def _unit_interval(value: float) -> float:
    return max(0.0, min(1.0, value))
