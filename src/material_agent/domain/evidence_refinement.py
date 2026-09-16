"""Explicit applicability and a single bounded, auditable refinement pass."""

from __future__ import annotations

import math
import time


class NoRefinementGain(Exception):
    """The alternate decode cannot provide a larger focus observation."""


def face_eye_evidence(meta: dict) -> dict:
    focus = meta.get("subject_focus")
    focus = focus if isinstance(focus, dict) else {}
    value = focus.get("eye_focus_score")
    if isinstance(value, (int, float)) and math.isfinite(value):
        return {
            "version": 1,
            "status": "observed",
            "value": value,
            "source": "eye_roi",
            "reason": "measured_eye_region",
        }
    context = meta.get("subject_context")
    context = context if isinstance(context, dict) else {}
    confidence = context.get("confidence")
    if (
        context.get("label") in {"back_view", "silhouette"}
        and isinstance(confidence, (int, float))
        and math.isfinite(confidence)
        and 0.9 <= confidence <= 1.0
        and context.get("source")
        and context.get("evidence_type") in {"visual_annotation", "model_visual_context"}
        and context.get("evidence")
    ):
        return {
            "version": 1,
            "status": "not_applicable",
            "value": None,
            "source": context["source"],
            "reason": context["label"],
            "context": dict(context),
        }
    return {
        "version": 1,
        "status": "unknown",
        "value": None,
        "source": "unavailable",
        "reason": "no_reliable_eye_measurement_or_context",
    }


def refine_group(results: list[tuple[str, dict]], *, config: dict, refine, clock=time.monotonic):
    """Schedule at most one callback per candidate; elapsed budget stops new work.

    A running synchronous decode/inference is not forcibly cancelled. Callback
    time can exceed the scheduling budget and is recorded explicitly.
    """
    if not config.get("enabled", False) or not results:
        return results
    budget = int(config.get("max_candidates", 2))
    seconds = float(config.get("max_seconds", 5.0))
    gap = float(config.get("score_gap", 0.5))
    started = clock()
    ranked = sorted(results, key=lambda pair: (-float(pair[1].get("score_total", 0)), pair[0]))
    close = (
        len(ranked) > 1
        and abs(
            float(ranked[0][1].get("score_total", 0)) - float(ranked[1][1].get("score_total", 0))
        )
        <= gap
    )
    updates = {}
    attempts = 0
    for index, (path, payload) in enumerate(ranked):
        meta = payload.get("meta") or {}
        if meta.get("refinement"):
            continue
        reasons = []
        if close and index < 2:
            reasons.append("close_candidates")
        if meta.get("focus_review_required"):
            reasons.append("insufficient_focus_resolution")
        evidence = meta.get("face_eye_evidence") or face_eye_evidence(meta)
        if payload.get("scene") == "people" and evidence["status"] == "unknown":
            reasons.append("unknown_eye_evidence")
        if not reasons:
            continue
        record = {
            "version": 1,
            "triggers": reasons,
            "attempts": 0,
            "before": {
                "score_total": payload.get("score_total"),
                "decision": payload.get("decision"),
                "decision_reasons": payload.get("decision_reasons", []),
                "scores": payload.get("scores", {}),
                "signals": payload.get("signals", []),
                "subject_focus": meta.get("subject_focus"),
                "face_eye_evidence": evidence,
            },
        }
        result = dict(payload)
        if attempts >= budget or clock() - started >= seconds:
            record["status"] = "budget_exhausted"
            record["review_required"] = True
        else:
            attempts += 1
            record["attempts"] = 1
            try:
                candidate = refine(path, payload)
                value = float(candidate["score_total"])
                if not math.isfinite(value):
                    raise ValueError("non-finite refined score")
                after_meta = candidate.get("meta") or {}
                after = after_meta.get("face_eye_evidence") or face_eye_evidence(after_meta)
                record["review_required"] = (
                    payload.get("scene") == "people" and after["status"] == "unknown"
                )
                # Publish only after the whole candidate has passed validation.
                # A later metadata failure must retain the original score/evidence.
                result = dict(candidate)
                record["status"] = "completed"
            except NoRefinementGain:
                record.update(status="no_resolution_gain", review_required=True)
            except Exception as error:
                record.update(
                    status="failed", error_type=type(error).__name__, review_required=True
                )
        record["elapsed_seconds"] = round(clock() - started, 6)
        record["budget_overrun"] = record["elapsed_seconds"] > seconds
        result["meta"] = {**(result.get("meta") or {}), "refinement": record}
        updates[path] = result
    return [(path, updates.get(path, payload)) for path, payload in results]
