from __future__ import annotations

from dataclasses import dataclass
import math

from ..utils.constants import AESTHETIC_DIMS


@dataclass
class LayeredSummary:
    total_score: float
    star_rating: int
    decision: str
    decision_reasons: list[str]
    screening_prior: float | None
    visible_breakdown: dict[str, float]
    policy_version: str = "layered-v1"


def signals_to_map(signals: list[dict]) -> dict[tuple[str, str], float]:
    mapped: dict[tuple[str, str], float] = {}
    for signal in signals:
        value = signal.get("value")
        if value is None:
            continue
        mapped[(signal["stage"], signal["signal_key"])] = round(float(value), 2)
    return mapped


def summarize_signals(signals: list[dict], *, scene: str, config: dict) -> LayeredSummary:
    signal_map = signals_to_map(signals)
    scene_profiles = config.get("scene_profiles", {})
    decision_policy = config.get("decision_policy", {})
    screening_policy = config.get("screening_policy", {})

    technical_quality = _coalesce(
        signal_map.get(("technical", "technical_quality")),
        _average(
            [
                signal_map.get(("technical", "exposure_control")),
                signal_map.get(("technical", "focus_integrity")),
                signal_map.get(("technical", "motion_blur")),
                signal_map.get(("technical", "noise_cleanliness")),
                signal_map.get(("technical", "portrait_face_eye_usability")),
            ]
        ),
    )
    subject_focus = _coalesce(
        signal_map.get(("aggregate", "subject_focus")),
        _average(
            [
                signal_map.get(("technical", "focus_integrity")),
                signal_map.get(("technical", "portrait_face_eye_usability")),
            ]
        ),
        technical_quality,
    )
    screening_prior = _coalesce(
        signal_map.get(("screening", "screening_prior")),
        signal_map.get(("aggregate", "screening_prior")),
        technical_quality,
    )
    aesthetic_weights = (
        scene_profiles.get(scene, {}).get("aesthetic_weights")
        or scene_profiles.get("default", {}).get("aesthetic_weights")
        or {dim: 1.0 / len(AESTHETIC_DIMS) for dim in AESTHETIC_DIMS}
    )
    aesthetic_scores = {dim: signal_map.get(("aesthetic", dim), 0.0) for dim in AESTHETIC_DIMS}
    available_aesthetic_dims = [
        dim
        for dim in AESTHETIC_DIMS
        if signal_map.get(("aesthetic", dim)) is not None and aesthetic_weights.get(dim, 0.0) > 0
    ]
    learned_aesthetic = signal_map.get(("aesthetic", "overall_aesthetic"))
    if learned_aesthetic is not None:
        aesthetic_total = round(float(learned_aesthetic), 2)
    elif available_aesthetic_dims:
        available_weight_sum = sum(
            aesthetic_weights.get(dim, 0.0) for dim in available_aesthetic_dims
        )
        aesthetic_total = round(
            sum(
                aesthetic_scores[dim] * aesthetic_weights.get(dim, 0.0)
                for dim in available_aesthetic_dims
            )
            / available_weight_sum,
            2,
        )
    else:
        aesthetic_total = 0.0

    screening_weight = float(screening_policy.get("weight", 0.10) or 0.0)
    base_score = round(
        technical_quality * 0.25
        + subject_focus * 0.15
        + aesthetic_total * (0.60 - screening_weight)
        + screening_prior * screening_weight,
        2,
    )
    weakness_penalty = _compute_weakness_penalty(
        technical_quality=technical_quality,
        subject_focus=subject_focus,
        aesthetic_scores=aesthetic_scores,
        available_aesthetic_dims=(
            [] if learned_aesthetic is not None else available_aesthetic_dims
        ),
    )
    total_score = round(max(0.0, min(10.0, base_score - weakness_penalty)), 2)

    reasons: list[str] = []
    hard_reject = decision_policy.get("hard_reject", {})
    if technical_quality < float(hard_reject.get("technical_quality_below", 1.5)):
        reasons.append("technical_quality_below_threshold")
    if subject_focus < float(hard_reject.get("subject_focus_below", 1.5)):
        reasons.append("subject_focus_below_threshold")

    if reasons:
        decision = "reject"
    else:
        keep_threshold = float(decision_policy.get("keep_threshold", 7.5))
        review_threshold = float(decision_policy.get("review_threshold", 5.5))
        if total_score >= keep_threshold:
            decision = "keep"
        elif total_score >= review_threshold:
            decision = "review"
        else:
            decision = "reject"
        portrait_usability = signal_map.get(("technical", "portrait_face_eye_usability"))
        if portrait_usability is not None and portrait_usability < 4.5 and decision == "keep":
            decision = "review"
            reasons.append("portrait_face_eye_needs_review")

    visible_breakdown = {
        "technical_quality": technical_quality,
        "subject_focus": subject_focus,
        "aesthetic_model_score": aesthetic_total,
        "composition": aesthetic_scores["composition"],
        "lighting": aesthetic_scores["lighting"],
        "color": aesthetic_scores["color"],
        "space_depth": aesthetic_scores["depth_separation"],
        "mood_story": aesthetic_scores["mood_story"],
        "subject_moment": aesthetic_scores["subject_moment"],
    }
    return LayeredSummary(
        total_score=total_score,
        star_rating=int(total_score / 2 + 0.5),
        decision=decision,
        decision_reasons=reasons,
        screening_prior=screening_prior,
        visible_breakdown=visible_breakdown,
    )


def group_best_candidate_review_enabled(config: dict) -> bool:
    grouping = config.get("grouping", {})
    return bool(
        grouping.get("enabled", False)
        and grouping.get("best_candidate_review", {}).get("enabled", True)
    )


def apply_group_best_candidate_review(
    results: list[tuple[str, dict]], *, enabled: bool = True
) -> list[tuple[str, dict]]:
    """Separate quality from selection; preserve one readable candidate per group.

    The historical function/config name remains a compatibility alias. A coverage
    choice is now an explicit keep, without changing scores or defect evidence.
    Only scored payloads participate: decode failures must remain errors.
    """
    updated = []
    eligible = []
    for file_path, payload in results:
        meta = dict(payload.get("meta") or {})
        quality = meta.get("quality_assessment")
        if not isinstance(quality, dict) or quality.get("version") != 1:
            quality = {
                "version": 1,
                "decision": payload.get("decision"),
                "reasons": list(payload.get("decision_reasons") or []),
            }
        try:
            score = float(payload.get("score_total", payload.get("total_score")))
        except TypeError, ValueError:
            score = float("nan")
        if (
            payload.get("status") in {"error", "failed"}
            or quality.get("decision") not in {"keep", "review", "reject"}
            or not math.isfinite(score)
        ):
            updated.append((file_path, payload))
            continue
        meta["quality_assessment"] = quality
        meta["selection"] = {
            "version": 1,
            "decision": quality["decision"],
            "role": "quality_policy",
            "reasons": list(quality["reasons"]),
        }
        result = {
            **payload,
            "meta": meta,
            "decision": quality["decision"],
            "decision_reasons": list(quality["reasons"]),
        }
        updated.append((file_path, result))
        eligible.append((score, file_path, result))
    if enabled and eligible and not any(p[2]["decision"] == "keep" for p in eligible):
        # Stable path tie-break makes replay/input ordering irrelevant.
        _, _, best = min(eligible, key=lambda p: (-p[0], p[1]))
        best["decision"] = "keep"
        best["decision_reasons"] = [*best["decision_reasons"], "group_coverage_fallback"]
        best["meta"]["selection"] = {
            "version": 1,
            "decision": "keep",
            "role": "group_coverage",
            "reasons": ["group_coverage_fallback"],
        }
    return updated


def _average(values: list[float | None]) -> float | None:
    known = [float(value) for value in values if value is not None]
    if not known:
        return None
    return round(sum(known) / len(known), 2)


def _coalesce(*values: float | None) -> float:
    for value in values:
        if value is not None:
            return round(float(value), 2)
    return 0.0


def _compute_weakness_penalty(
    *,
    technical_quality: float,
    subject_focus: float,
    aesthetic_scores: dict[str, float],
    available_aesthetic_dims: list[str],
) -> float:
    penalty = 0.0
    ranked_aesthetic = sorted(
        float(aesthetic_scores[dim])
        for dim in available_aesthetic_dims
        if float(aesthetic_scores[dim]) > 0.0
    )
    if ranked_aesthetic:
        penalty += max(0.0, 6.5 - ranked_aesthetic[0]) * 0.18
    if len(ranked_aesthetic) >= 2:
        penalty += max(0.0, 5.5 - ranked_aesthetic[1]) * 0.08
    penalty += max(0.0, 6.0 - technical_quality) * 0.12
    penalty += max(0.0, 6.0 - subject_focus) * 0.10
    return round(penalty, 2)
