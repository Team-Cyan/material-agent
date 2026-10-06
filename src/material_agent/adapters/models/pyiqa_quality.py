from __future__ import annotations

import asyncio
from io import BytesIO
import math
from numbers import Real
from typing import Any, Protocol

from PIL import Image
from .inference_contract import optional_execution


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

    def __init__(
        self, config: dict[str, Any] | None = None, *, runtime: QualityRuntime | None = None
    ):
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
        if not any(float(spec.get("weight", 1.0)) > 0 for spec in self.metrics.values()):
            raise ValueError("local.quality.metrics must enable at least one positive weight")
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
        if not isinstance(raw_scores, dict):
            raise RuntimeError("quality runtime must return a score mapping")
        validated_scores = {}
        for name in self.metrics:
            if name not in raw_scores:
                raise RuntimeError("quality runtime did not return every configured metric")
            validated_scores[name] = _finite_real(
                raw_scores[name], "quality runtime must return finite real scores", RuntimeError
            )
        signals: dict[str, dict[str, Any]] = {}
        weighted_total = 0.0
        weight_sum = 0.0
        role_totals: dict[str, float] = {}
        role_weights: dict[str, float] = {}
        for name, spec in self.metrics.items():
            raw_score = validated_scores[name]
            normalized = _normalize_score(raw_score, spec)
            weight = float(spec.get("weight", 1.0))
            contribution = _finite_real(
                normalized * weight, "quality aggregate arithmetic must remain finite", RuntimeError
            )
            weighted_total = _finite_real(
                weighted_total + contribution,
                "quality aggregate arithmetic must remain finite",
                RuntimeError,
            )
            weight_sum = _finite_real(
                weight_sum + weight, "quality aggregate arithmetic must remain finite", RuntimeError
            )
            role = str(spec.get("role", "quality"))
            role_totals[role] = _finite_real(
                role_totals.get(role, 0.0) + contribution,
                "quality aggregate arithmetic must remain finite",
                RuntimeError,
            )
            role_weights[role] = _finite_real(
                role_weights.get(role, 0.0) + weight,
                "quality aggregate arithmetic must remain finite",
                RuntimeError,
            )
            signals[name] = {
                "raw_score": round(raw_score, 6),
                "normalized_score": round(normalized, 6),
                "lower_better": bool(spec["lower_better"]),
                "raw_min": float(spec["raw_min"]),
                "raw_max": float(spec["raw_max"]),
                "weight": weight,
                "role": role,
            }
        if weight_sum <= 0:
            raise RuntimeError("quality aggregate requires a positive total weight")
        aggregate = _finite_real(
            weighted_total / weight_sum,
            "quality aggregate arithmetic must remain finite",
            RuntimeError,
        )
        aggregates = {
            role: round(
                _finite_real(
                    role_totals[role] / role_weights[role],
                    "quality aggregate arithmetic must remain finite",
                    RuntimeError,
                ),
                6,
            )
            for role in role_totals
            if role_weights[role] > 0
        }
        return {
            "aggregate_score": round(aggregate, 6),
            "execution": optional_execution("pyiqa", self.config),
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
                results[name] = _finite_real(
                    value.item() if hasattr(value, "item") else value,
                    "quality runtime must return finite real scores",
                    RuntimeError,
                )
        return results


def _finite_real(value: Any, message: str, error_type: type[Exception] = ValueError) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise error_type(message)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise error_type(message) from error
    if not math.isfinite(number):
        raise error_type(message)
    return number


def _validate_metric_spec(name: str, spec: dict[str, Any]) -> None:
    role = spec.get("role", "quality")
    if not isinstance(role, str) or role not in {"reject_prior", "quality", "aesthetic"}:
        raise ValueError("local.quality metric role must be reject_prior, quality, or aesthetic")
    lower = _finite_real(spec.get("raw_min"), "local.quality metric raw_min must be finite real")
    upper = _finite_real(spec.get("raw_max"), "local.quality metric raw_max must be finite real")
    if upper <= lower or not math.isfinite(upper - lower):
        raise ValueError("local.quality metric raw_max must exceed raw_min with finite width")
    if not isinstance(spec.get("lower_better"), bool):
        raise ValueError("local.quality metric lower_better must be a boolean")
    weight = _finite_real(
        spec.get("weight", 1.0), "local.quality metric weight must be finite real"
    )
    if weight < 0:
        raise ValueError("local.quality metric weight must be non-negative")


def _normalize_score(raw_score: float, spec: dict[str, Any]) -> float:
    raw_score = _finite_real(
        raw_score, "quality runtime must return finite real scores", RuntimeError
    )
    lower = float(spec["raw_min"])
    upper = float(spec["raw_max"])
    # Clip finite outliers before subtraction to avoid overflowing raw_score - lower.
    if raw_score <= lower:
        ratio = 0.0
    elif raw_score >= upper:
        ratio = 1.0
    else:
        ratio = (raw_score - lower) / (upper - lower)
    if bool(spec["lower_better"]):
        ratio = 1.0 - ratio
    return _finite_real(ratio * 10.0, "quality normalization must remain finite", RuntimeError)
