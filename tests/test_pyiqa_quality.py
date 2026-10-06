import asyncio
from io import BytesIO
import json
import sys

import numpy as np

import pytest
from PIL import Image

from material_agent.adapters.models.pyiqa_quality import PyIqaQualityAdapter
from material_agent.clients.local import AsyncLocalClient


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (100, 120, 140)).save(output, format="JPEG")
    return output.getvalue()


class _FakeQualityRuntime:
    def __init__(self, scores):
        self.scores = scores

    def score(self, image, metric_names):
        assert image.mode == "RGB"
        assert metric_names == list(self.scores)
        return self.scores


def _config():
    return {
        "device": "cpu",
        "policy_version": "fixture-v1",
        "metrics": {
            "lower": {
                "enabled": True,
                "role": "reject_prior",
                "lower_better": True,
                "raw_min": 0.0,
                "raw_max": 100.0,
                "weight": 1.0,
            },
            "higher": {
                "enabled": True,
                "role": "aesthetic",
                "lower_better": False,
                "raw_min": 0.0,
                "raw_max": 1.0,
                "weight": 1.0,
            },
        },
    }


def test_quality_adapter_normalizes_direction_and_aggregates():
    adapter = PyIqaQualityAdapter(
        _config(), runtime=_FakeQualityRuntime({"lower": 20.0, "higher": 0.6})
    )

    result = asyncio.run(adapter.score_quality(_jpeg_bytes()))

    assert result["signals"]["lower"]["normalized_score"] == 8.0
    assert result["signals"]["higher"]["normalized_score"] == 6.0
    assert result["aggregate_score"] == 7.0
    assert result["aggregates"] == {"reject_prior": 8.0, "aesthetic": 6.0}
    assert result["policy_version"] == "fixture-v1"


def test_quality_adapter_clamps_scores_outside_declared_range():
    adapter = PyIqaQualityAdapter(
        _config(), runtime=_FakeQualityRuntime({"lower": -10.0, "higher": 3.0})
    )

    result = asyncio.run(adapter.score_quality(_jpeg_bytes()))

    assert result["signals"]["lower"]["normalized_score"] == 10.0
    assert result["signals"]["higher"]["normalized_score"] == 10.0


def test_quality_adapter_rejects_invalid_range():
    config = _config()
    config["metrics"]["lower"]["raw_max"] = 0.0

    with pytest.raises(ValueError, match="raw_max must exceed"):
        PyIqaQualityAdapter(config)


class _FakeQualityAdapter:
    async def score_quality(self, jpeg_bytes):
        return {
            "aggregate_score": 8.0,
            "signals": {"brisque": {"raw_score": 20.0, "normalized_score": 8.0}},
            "runtime": "fixture-quality",
            "device": "cpu",
            "model_names": ["brisque"],
            "policy_version": "fixture-v1",
        }


def test_local_client_adds_quality_provenance_without_changing_dimensions():
    client = AsyncLocalClient({"quality": {"enabled": True}})
    client._quality = _FakeQualityAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["_quality"]["status"] == "model"
    assert result["_quality"]["aggregate_score"] == 8.0
    assert result["_model_stack"] == ["brisque"]
    assert result["_scoring_mode"] == "hybrid"
    assert result["_runtime"] == "cpu+fixture-quality:cpu"
    assert result["clarity"] != 8.0


class _BrokenQualityAdapter:
    async def score_quality(self, jpeg_bytes):
        raise RuntimeError("quality weights missing")


def test_local_client_quality_failure_is_explicit_fallback():
    client = AsyncLocalClient({"quality": {"enabled": True, "enforce_available": False}})
    client._quality = _BrokenQualityAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["_quality"].pop("execution")["status"] == "unavailable"
    assert result["_quality"] == {
        "status": "fallback",
        "error": "quality weights missing",
    }


@pytest.mark.parametrize(
    "invalid",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        True,
        False,
        "0.6",
        None,
        complex(0.6, 0),
        np.bool_(True),
        np.array([0.6]),
        10**1000,
    ],
)
def test_quality_adapter_rejects_invalid_raw_evidence_before_assembly(invalid):
    adapter = PyIqaQualityAdapter(
        _config(), runtime=_FakeQualityRuntime({"lower": 20.0, "higher": invalid})
    )
    with pytest.raises(RuntimeError, match="finite real scores"):
        asyncio.run(adapter.score_quality(_jpeg_bytes()))


@pytest.mark.parametrize("scalar", [np.float32(0.6), np.float64(0.6), np.int32(1), np.int64(1)])
def test_quality_adapter_accepts_numpy_real_scalars_and_json_is_finite(scalar):
    adapter = PyIqaQualityAdapter(
        _config(), runtime=_FakeQualityRuntime({"lower": np.int64(20), "higher": scalar})
    )
    result = asyncio.run(adapter.score_quality(_jpeg_bytes()))
    assert result["signals"]["higher"]["normalized_score"] == round(float(scalar) * 10, 6)
    assert isinstance(result["signals"]["higher"]["raw_score"], float)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field", ["raw_min", "raw_max", "weight"])
@pytest.mark.parametrize(
    "invalid",
    [float("nan"), float("inf"), -float("inf"), True, np.bool_(False), "1", None, 10**1000],
)
def test_quality_config_rejects_invalid_numeric_fields(field, invalid):
    config = _config()
    config["metrics"]["lower"][field] = invalid
    with pytest.raises(ValueError, match="finite real"):
        PyIqaQualityAdapter(config)


def test_quality_config_rejects_overflowing_range_width():
    config = _config()
    config["metrics"]["lower"].update(raw_min=-sys.float_info.max, raw_max=sys.float_info.max)
    with pytest.raises(ValueError, match="finite width"):
        PyIqaQualityAdapter(config)


def test_quality_config_rejects_negative_weight_and_all_enabled_zero_weights():
    config = _config()
    config["metrics"]["higher"]["weight"] = -1
    with pytest.raises(ValueError, match="non-negative"):
        PyIqaQualityAdapter(config)
    config["metrics"]["higher"]["weight"] = 0
    config["metrics"]["lower"]["weight"] = 0
    config["metrics"]["disabled_positive"] = {"enabled": False, "weight": 1}
    with pytest.raises(ValueError, match="positive weight"):
        PyIqaQualityAdapter(config)


def test_quality_zero_weight_role_retains_signals_and_omits_role_aggregate():
    config = _config()
    config["metrics"]["lower"]["weight"] = 0
    adapter = PyIqaQualityAdapter(
        config, runtime=_FakeQualityRuntime({"lower": 20.0, "higher": 0.6})
    )
    result = asyncio.run(adapter.score_quality(_jpeg_bytes()))
    assert result["aggregate_score"] == 6.0
    assert result["aggregates"] == {"aesthetic": 6.0}
    assert result["signals"]["lower"]["normalized_score"] == 8.0


@pytest.mark.parametrize(
    "scores",
    [
        {"lower": -sys.float_info.max, "higher": sys.float_info.max},
        {"lower": sys.float_info.max, "higher": -sys.float_info.max},
    ],
)
def test_finite_extreme_outliers_still_clamp_without_intermediate_overflow(scores):
    config = _config()
    config["metrics"]["lower"].update(raw_min=-1e308, raw_max=-1e308 + 1e292)
    adapter = PyIqaQualityAdapter(config, runtime=_FakeQualityRuntime(scores))
    result = asyncio.run(adapter.score_quality(_jpeg_bytes()))
    expected = 10.0 if scores["lower"] < 0 else 0.0
    assert result["signals"]["lower"]["normalized_score"] == expected
    assert result["signals"]["higher"]["normalized_score"] == expected
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("scores", [{"lower": 0.0, "higher": 1.0}, {"lower": 100.0, "higher": 0.0}])
def test_quality_aggregate_product_or_weight_sum_overflow_fails(scores):
    config = _config()
    for spec in config["metrics"].values():
        spec["weight"] = 1e308
    adapter = PyIqaQualityAdapter(config, runtime=_FakeQualityRuntime(scores))
    with pytest.raises(RuntimeError, match="arithmetic must remain finite"):
        asyncio.run(adapter.score_quality(_jpeg_bytes()))


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, "0.6"])
@pytest.mark.parametrize("enforce_available", [False, True])
def test_client_invalid_quality_runtime_is_unavailable_without_accepted_signal(
    invalid, enforce_available
):
    client = AsyncLocalClient(
        {"quality": {"enabled": True, "enforce_available": enforce_available}}
    )
    client._quality = PyIqaQualityAdapter(
        _config(), runtime=_FakeQualityRuntime({"lower": 20.0, "higher": invalid})
    )
    if enforce_available:
        with pytest.raises(RuntimeError, match="finite real scores"):
            asyncio.run(client.score_image(_jpeg_bytes()))
    else:
        result = asyncio.run(client.score_image(_jpeg_bytes()))
        assert result["_quality"]["status"] == "fallback"
        assert result["_quality"]["execution"]["status"] == "unavailable"
        assert "signals" not in result["_quality"]
        assert "aggregate_score" not in result["_quality"]
        assert "aggregates" not in result["_quality"]
        assert not set(result.get("_model_stack", [])) & {"lower", "higher"}
        assert result["_scoring_mode"] == "heuristic"
        json.dumps(result, allow_nan=False)


def test_client_aggregate_overflow_is_unavailable_and_serializable():
    config = _config()
    for spec in config["metrics"].values():
        spec["weight"] = 1e308
    client = AsyncLocalClient({"quality": {"enabled": True, "enforce_available": False}})
    client._quality = PyIqaQualityAdapter(
        config, runtime=_FakeQualityRuntime({"lower": 0.0, "higher": 1.0})
    )
    result = asyncio.run(client.score_image(_jpeg_bytes()))
    assert result["_quality"]["execution"]["status"] == "unavailable"
    assert "signals" not in result["_quality"] and "aggregate_score" not in result["_quality"]
    json.dumps(result, allow_nan=False)


def test_quality_config_accepts_numpy_finite_bounds_and_weights():
    config = _config()
    for spec in config["metrics"].values():
        for field in ("raw_min", "raw_max", "weight"):
            spec[field] = np.float64(spec[field])
    adapter = PyIqaQualityAdapter(
        config, runtime=_FakeQualityRuntime({"lower": 20.0, "higher": 0.6})
    )
    result = asyncio.run(adapter.score_quality(_jpeg_bytes()))
    assert result["aggregate_score"] == 7.0
    assert result["aggregates"] == {"reject_prior": 8.0, "aesthetic": 6.0}
    json.dumps(result, allow_nan=False)


def test_quality_aggregate_sum_overflow_fails_even_with_finite_products_and_weights():
    config = _config()
    for spec in config["metrics"].values():
        spec["weight"] = 1e307
    adapter = PyIqaQualityAdapter(
        config, runtime=_FakeQualityRuntime({"lower": 0.0, "higher": 1.0})
    )
    with pytest.raises(RuntimeError, match="arithmetic must remain finite"):
        asyncio.run(adapter.score_quality(_jpeg_bytes()))


@pytest.mark.parametrize("invalid", [True, np.bool_(False), "0.6", float("nan"), float("inf")])
def test_native_runtime_does_not_coerce_invalid_scalar_items_to_valid_floats(invalid):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from material_agent.adapters.models.pyiqa_quality import _PyIqaRuntime

    class Tensor:
        def permute(self, *axes):
            return self

        def unsqueeze(self, axis):
            return self

        def to(self, device):
            return self

    runtime = _PyIqaRuntime.__new__(_PyIqaRuntime)
    runtime.np = np
    runtime.torch = SimpleNamespace(from_numpy=lambda array: Tensor(), inference_mode=nullcontext)
    runtime.device = "cpu"
    runtime._metrics = {"higher": lambda tensor: SimpleNamespace(item=lambda: invalid)}
    runtime.pyiqa = SimpleNamespace(
        create_metric=lambda *args, **kwargs: pytest.fail("no model loading")
    )
    with pytest.raises(RuntimeError, match="finite real scores"):
        runtime.score(Image.new("RGB", (2, 2)), ["higher"])
