import asyncio
from io import BytesIO

import pytest
from PIL import Image

from material_agent.adapters.models.dinov2_embedding import DinoV2EmbeddingAdapter
from material_agent.clients.local import AsyncLocalClient


def _jpeg_bytes(color=(80, 100, 120)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color).save(output, format="JPEG")
    return output.getvalue()


class _FakeEmbeddingRuntime:
    def embed(self, image):
        assert image.mode == "RGB"
        return [0.1, 0.2, 0.3]


def test_dinov2_adapter_returns_vector_with_provenance():
    adapter = DinoV2EmbeddingAdapter(
        {"model_name": "fixture-dino", "device": "cpu"},
        runtime=_FakeEmbeddingRuntime(),
    )

    result = asyncio.run(adapter.embed_image(_jpeg_bytes()))

    assert result["vector"] == [0.1, 0.2, 0.3]
    assert result["dimensions"] == 3
    assert result["model_name"] == "fixture-dino"


class _FakeEmbeddingAdapter:
    async def embed_image(self, jpeg_bytes):
        return {
            "vector": [0.1, 0.2],
            "dimensions": 2,
            "model_name": "fixture-dino",
            "model_version": "fixture-v1",
            "runtime": "fixture-embedding",
            "device": "GPU",
            "execution_devices": ["GPU.0"],
        }


def test_local_client_keeps_embedding_vector_out_of_embedding_metadata():
    client = AsyncLocalClient({"embedding": {"enabled": True}})
    client._embedding = _FakeEmbeddingAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["_embedding_vector"] == [0.1, 0.2]
    assert result["_embedding"] == {
        "status": "model",
        "dimensions": 2,
        "model_name": "fixture-dino",
        "model_version": "fixture-v1",
        "runtime": "fixture-embedding",
        "device": "GPU",
        "execution_devices": ["GPU.0"],
    }
    assert result["_runtime"] == "cpu+fixture-embedding:GPU.0"


class _CountingEmbeddingAdapter:
    def __init__(self):
        self.calls = 0

    async def embed_image(self, jpeg_bytes):
        self.calls += 1
        return {
            "vector": [float(self.calls), 0.5],
            "dimensions": 2,
            "model_name": "fixture-dino",
            "model_version": "fixture-v1",
            "runtime": "fixture-embedding",
            "device": "cpu",
        }


def test_local_embedding_result_cache_is_lru_bounded_and_clearable():
    client = AsyncLocalClient(
        {"embedding": {"enabled": True, "result_cache_size": 2}}
    )
    adapter = _CountingEmbeddingAdapter()
    client._embedding = adapter
    first = _jpeg_bytes((10, 20, 30))
    second = _jpeg_bytes((40, 50, 60))
    third = _jpeg_bytes((70, 80, 90))

    async def exercise_cache():
        await client.embed_image(first)
        await client.embed_image(second)
        await client.embed_image(first)
        await client.embed_image(third)
        await client.embed_image(second)

    asyncio.run(exercise_cache())

    assert adapter.calls == 4
    assert len(client._embedding_result_cache) == 2
    client.clear_embedding_result_cache()
    assert client._embedding_result_cache == {}

    asyncio.run(client.embed_image(first))
    assert adapter.calls == 5


def test_openvino_embedding_inherits_inference_fallback_device(monkeypatch):
    import material_agent.adapters.models.openvino_embedding as openvino_embedding

    captured = {}
    sentinel = object()

    def build_adapter(config):
        captured.update(config)
        return sentinel

    monkeypatch.setattr(openvino_embedding, "OpenVinoEmbeddingAdapter", build_adapter)
    client = AsyncLocalClient(
        {
            "inference": {"fallback_device": "CPU"},
            "embedding": {"runtime": "openvino"},
        }
    )

    assert client._embedding_scorer() is sentinel
    assert captured["fallback_device"] == "CPU"


class _EmptyEmbeddingRuntime:
    def embed(self, image):
        return []


def test_dinov2_adapter_rejects_empty_vector():
    adapter = DinoV2EmbeddingAdapter(runtime=_EmptyEmbeddingRuntime())

    with pytest.raises(RuntimeError, match="empty embedding"):
        asyncio.run(adapter.embed_image(_jpeg_bytes()))
