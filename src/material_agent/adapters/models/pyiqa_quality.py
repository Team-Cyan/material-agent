from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any, Protocol

from PIL import Image


DEFAULT_QUALITY_METRICS = {
    "brisque": {
        "enabled": True,
        "role": "reject_prior",
        "lower_better": True,
        "raw_min": 0.0,
        "raw_max": 100.0,
        "weight": 0.5,
    },
    "niqe": {
        "enabled": True,
        "role": "reject_prior",
        "lower_better": True,
        "raw_min": 0.0,
        "raw_max": 10.0,
        "weight": 0.5,
    },
}


class QualityRuntime(Protocol):
    def score(self, image: Image.Image, metric_names: list[str]) -> dict[str, float]: ...


class PyIqaQualityAdapter:
    """Run configured no-reference IQA metrics with explicit normalization."""

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: QualityRuntime | None = None):
        self.config = config or {}
        raw_metrics = self.config.get("metrics", DEFAULT_QUALITY_METRICS)
        if not isinstance(raw_metrics, dict) or not raw_metrics:
            raise ValueError("local.quality.metrics must be a non-empty mapping")
        self.metrics = {
            str(name): dict(spec)
            for name, spec in raw_metrics.items()
            if isinstance(spec, dict) and spec.get("enabled", True)
        }
        if not self.metrics:
            raise ValueError("local.quality.metrics must enable at least one metric")
        for name, spec in self.metrics.items():
            _validate_metric_spec(name, spec)
        self.device = str(self.config.get("device", "cpu"))
        self._runtime = runtime

    async def score_quality(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._score_sync, jpeg_bytes)

    def _score_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is None:
            runtime = _PyIqaRuntime(device=self.device)
            self._runtime = runtime
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        raw_scores = runtime.score(image, list(self.metrics))
        signals: dict[str, dict[str, Any]] = {}
        weighted_total = 0.0
        weight_sum = 0.0
        role_totals: dict[str, float] = {}
        role_weights: dict[str, float] = {}
        for name, spec in self.metrics.items():
            if name not in raw_scores:
                raise RuntimeError(f"quality runtime did not return configured metric {name!r}")
            raw_score = float(raw_scores[name])
            normalized = _normalize_score(raw_score, spec)
            weight = float(spec.get("weight", 1.0))
            weighted_total += normalized * weight
            weight_sum += weight
            role = str(spec.get("role", "quality"))
            role_totals[role] = role_totals.get(role, 0.0) + normalized * weight
            role_weights[role] = role_weights.get(role, 0.0) + weight
            signals[name] = {
                "raw_score": round(raw_score, 6),
                "normalized_score": round(normalized, 6),
                "lower_better": bool(spec["lower_better"]),
                "raw_min": float(spec["raw_min"]),
                "raw_max": float(spec["raw_max"]),
                "weight": weight,
                "role": role,
            }
        aggregate = weighted_total / weight_sum if weight_sum > 0 else 0.0
        aggregates = {
            role: round(role_totals[role] / role_weights[role], 6)
            for role in role_totals
            if role_weights[role] > 0
        }
        return {
            "aggregate_score": round(aggregate, 6),
            "aggregates": aggregates,
            "signals": signals,
            "runtime": "pyiqa",
            "device": self.device,
            "model_names": list(self.metrics),
            "policy_version": str(self.config.get("policy_version", "quality-priors-v1")),
        }


class _PyIqaRuntime:
    def __init__(self, *, device: str):
        try:
            import numpy as np
            import pyiqa
            import torch
        except ImportError as error:
            raise RuntimeError(
                "PyIQA quality scoring requires the quality-models optional dependencies"
            ) from error
        self.np = np
        self.pyiqa = pyiqa
        self.torch = torch
        self.device = torch.device(device)
        self._metrics: dict[str, Any] = {}

    def score(self, image: Image.Image, metric_names: list[str]) -> dict[str, float]:
        array = self.np.asarray(image, dtype=self.np.float32) / 255.0
        tensor = self.torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).to(self.device)
        results: dict[str, float] = {}
        with self.torch.inference_mode():
            for name in metric_names:
                metric = self._metrics.get(name)
                if metric is None:
                    metric = self.pyiqa.create_metric(name, device=self.device)
                    self._metrics[name] = metric
                value = metric(tensor)
                results[name] = float(value.item() if hasattr(value, "item") else value)
        return results


def _validate_metric_spec(name: str, spec: dict[str, Any]) -> None:
    role = spec.get("role", "quality")
    if role not in {"reject_prior", "quality", "aesthetic"}:
        raise ValueError(
            f"local.quality.metrics.{name}.role must be reject_prior, quality, or aesthetic"
        )
    for key in ("raw_min", "raw_max"):
        if not isinstance(spec.get(key), int | float):
            raise ValueError(f"local.quality.metrics.{name}.{key} must be numeric")
    if float(spec["raw_max"]) <= float(spec["raw_min"]):
        raise ValueError(f"local.quality.metrics.{name}.raw_max must exceed raw_min")
    if not isinstance(spec.get("lower_better"), bool):
        raise ValueError(f"local.quality.metrics.{name}.lower_better must be a boolean")
    weight = spec.get("weight", 1.0)
    if not isinstance(weight, int | float) or float(weight) < 0:
        raise ValueError(f"local.quality.metrics.{name}.weight must be non-negative")


def _normalize_score(raw_score: float, spec: dict[str, Any]) -> float:
    lower = float(spec["raw_min"])
    upper = float(spec["raw_max"])
    ratio = max(0.0, min(1.0, (raw_score - lower) / (upper - lower)))
    if bool(spec["lower_better"]):
        ratio = 1.0 - ratio
    return ratio * 10.0
