from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np


def fit_aesthetic_calibration(
    payload: dict,
    *,
    minimum_label_count: int = 20,
    minimum_raw_span: float = 1.0,
    pivot: float = 5.5,
    policy_version: str = "target-affine-v1",
) -> tuple[dict, dict]:
    """Fit per-target affine profiles from human 1-10 or 1-5 ratings."""

    if not 2 <= minimum_label_count <= 100000:
        raise ValueError("minimum_label_count must be between 2 and 100000")
    if not math.isfinite(minimum_raw_span) or not 0.1 <= minimum_raw_span <= 9.0:
        raise ValueError("minimum_raw_span must be between 0.1 and 9")
    if not math.isfinite(pivot) or not 1.0 <= pivot <= 10.0:
        raise ValueError("pivot must be between 1 and 10")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise ValueError("policy_version must be a non-empty string")
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Calibration labels must contain an 'items' list")
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for index, item in enumerate(payload["items"]):
        if not isinstance(item, dict):
            raise ValueError(f"Calibration item {index} must be a mapping")
        target = str(item.get("target", "")).strip()
        if not target:
            raise ValueError(f"Calibration item {index} requires target")
        raw = _finite_score(item.get("raw_score"), f"item {index} raw_score")
        if item.get("human_score") is not None:
            human = _finite_score(item["human_score"], f"item {index} human_score")
        elif item.get("human_rating") is not None:
            rating = float(item["human_rating"])
            if not math.isfinite(rating) or not 1.0 <= rating <= 5.0:
                raise ValueError(f"item {index} human_rating must be between 1 and 5")
            human = rating * 2.0
        else:
            raise ValueError(f"Calibration item {index} requires human_score or human_rating")
        grouped[target].append((raw, human))

    profiles: dict[str, dict[str, Any]] = {}
    target_reports: dict[str, dict[str, Any]] = {}
    for target, pairs in sorted(grouped.items()):
        count = len(pairs)
        raw = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
        human = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
        report: dict[str, Any] = {
            "label_count": count,
            "rmse_before": _rmse(raw, human),
            "status": "insufficient_labels",
            "raw_span": round(float(np.max(raw) - np.min(raw)), 6),
        }
        if count >= minimum_label_count and report["raw_span"] < minimum_raw_span:
            report["status"] = "insufficient_raw_span"
        elif count >= minimum_label_count:
            design = np.column_stack((raw - pivot, np.ones(count, dtype=np.float64)))
            scale, offset = np.linalg.lstsq(design, human - pivot, rcond=None)[0]
            scale = float(np.clip(scale, 0.5, 1.5))
            offset = float(np.clip(offset, -2.0, 2.0))
            predicted = np.clip(pivot + scale * (raw - pivot) + offset, 1.0, 10.0)
            rmse_after = _rmse(predicted, human)
            report.update(
                {
                    "status": (
                        "fitted" if rmse_after + 1e-9 < report["rmse_before"] else "no_improvement"
                    ),
                    "scale": round(scale, 6),
                    "offset": round(offset, 6),
                    "rmse_after": rmse_after,
                }
            )
            if report["status"] == "fitted":
                profiles[target] = {
                    "scale": round(scale, 6),
                    "offset": round(offset, 6),
                    "label_count": count,
                }
        target_reports[target] = report

    config = {
        "enabled": True,
        "policy_version": policy_version,
        "minimum_label_count": minimum_label_count,
        "minimum_raw_span": minimum_raw_span,
        "pivot": pivot,
        "profiles": profiles,
    }
    report = {
        "policy_version": policy_version,
        "minimum_label_count": minimum_label_count,
        "total_labels": sum(len(pairs) for pairs in grouped.values()),
        "fitted_profiles": len(profiles),
        "targets": target_reports,
    }
    return config, report


def _finite_score(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(number) or not 1.0 <= number <= 10.0:
        raise ValueError(f"{label} must be between 1 and 10")
    return number


def _rmse(predicted: np.ndarray, expected: np.ndarray) -> float:
    return round(float(np.sqrt(np.mean(np.square(predicted - expected)))), 6)
