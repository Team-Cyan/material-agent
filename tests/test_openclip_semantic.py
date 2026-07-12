import asyncio
from io import BytesIO

import pytest
from PIL import Image

from material_agent.adapters.models.openclip_semantic import (
    DEFAULT_SCENE_PROMPTS,
    OpenClipSemanticAdapter,
)
from material_agent.clients.local import AsyncLocalClient


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (120, 80, 40)).save(output, format="JPEG")
    return output.getvalue()


def test_default_scene_prompts_include_live_concerts():
    assert "concert" in DEFAULT_SCENE_PROMPTS
    assert "instrument" in DEFAULT_SCENE_PROMPTS["concert"]


class _FakeRuntime:
    def __init__(self, probabilities):
        self.probabilities = probabilities
        self.prompts = None

    def classify(self, image, prompts):
        assert image.mode == "RGB"
        self.prompts = prompts
        return self.probabilities


def test_semantic_adapter_maps_confident_scene():
    runtime = _FakeRuntime([0.8, 0.1, 0.1])
    adapter = OpenClipSemanticAdapter(
        {
            "model_name": "fixture-model",
            "pretrained": "fixture-v1",
            "min_confidence": 0.3,
            "prompts": {
                "people": "a portrait",
                "screenshot": "a screenshot",
                "other": "another photograph",
            },
        },
        runtime=runtime,
    )

    result = asyncio.run(adapter.classify_image(_jpeg_bytes()))

    assert result["scene"] == "people"
    assert result["scene_raw"] == "people"
    assert result["confidence"] == 0.8
    assert result["non_photo"] is False
    assert result["model_name"] == "fixture-model"


def test_semantic_adapter_maps_screenshot_to_other_with_non_photo_marker():
    adapter = OpenClipSemanticAdapter(
        {"prompts": {"people": "portrait", "screenshot": "screenshot", "other": "other"}},
        runtime=_FakeRuntime([0.1, 0.85, 0.05]),
    )

    result = asyncio.run(adapter.classify_image(_jpeg_bytes()))

    assert result["scene"] == "other"
    assert result["scene_raw"] == "screenshot"
    assert result["non_photo"] is True


def test_semantic_adapter_uses_other_below_confidence_threshold():
    adapter = OpenClipSemanticAdapter(
        {
            "min_confidence": 0.7,
            "prompts": {"people": "portrait", "other": "other"},
        },
        runtime=_FakeRuntime([0.6, 0.4]),
    )

    result = asyncio.run(adapter.classify_image(_jpeg_bytes()))

    assert result["scene"] == "other"
    assert result["scene_raw"] == "people"


def test_semantic_adapter_rejects_probability_shape_mismatch():
    adapter = OpenClipSemanticAdapter(
        {"prompts": {"people": "portrait", "other": "other"}},
        runtime=_FakeRuntime([1.0]),
    )

    with pytest.raises(RuntimeError, match="probability count"):
        asyncio.run(adapter.classify_image(_jpeg_bytes()))


class _FakeSemanticAdapter:
    async def classify_image(self, jpeg_bytes):
        assert jpeg_bytes
        return {
            "scene": "people",
            "scene_raw": "people",
            "confidence": 0.9,
            "non_photo": False,
            "model_name": "fixture-model",
            "model_version": "fixture-v1",
            "runtime": "fixture",
            "device": "cpu",
            "probabilities": {"people": 0.9, "other": 0.1},
        }


def test_local_client_composes_semantic_prediction_with_heuristic_scores():
    client = AsyncLocalClient({"semantic": {"enabled": True}})
    client._semantic = _FakeSemanticAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["scene"] == "people"
    assert result["_scoring_mode"] == "hybrid"
    assert result["_runtime"] == "cpu+fixture:cpu"
    assert result["_configured_runtime"] == "cpu"
    assert result["_model_stack"] == ["fixture-model"]
    assert result["_semantic"]["status"] == "model"


class _BrokenSemanticAdapter:
    async def classify_image(self, jpeg_bytes):
        raise RuntimeError("weights missing")


def test_local_client_records_semantic_fallback_without_fabricating_scene():
    client = AsyncLocalClient({"semantic": {"enabled": True, "enforce_available": False}})
    client._semantic = _BrokenSemanticAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["scene"] == "other"
    assert result["_scoring_mode"] == "heuristic"
    assert result["_semantic"] == {"status": "fallback", "error": "weights missing"}


def test_local_client_enforces_semantic_availability_when_requested():
    client = AsyncLocalClient({"semantic": {"enabled": True, "enforce_available": True}})
    client._semantic = _BrokenSemanticAdapter()

    with pytest.raises(RuntimeError, match="weights missing"):
        asyncio.run(client.score_image(_jpeg_bytes()))
