import asyncio
from io import BytesIO

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

    assert result["_quality"] == {
        "status": "fallback",
        "error": "quality weights missing",
    }
