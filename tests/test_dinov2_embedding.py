import asyncio
from io import BytesIO

import pytest
from PIL import Image

from material_agent.adapters.models.dinov2_embedding import DinoV2EmbeddingAdapter
from material_agent.clients.local import AsyncLocalClient


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (80, 100, 120)).save(output, format="JPEG")
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
            "device": "cpu",
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
        "device": "cpu",
    }
    assert result["_runtime"] == "cpu+fixture-embedding:cpu"


class _EmptyEmbeddingRuntime:
    def embed(self, image):
        return []


def test_dinov2_adapter_rejects_empty_vector():
    adapter = DinoV2EmbeddingAdapter(runtime=_EmptyEmbeddingRuntime())

    with pytest.raises(RuntimeError, match="empty embedding"):
        asyncio.run(adapter.embed_image(_jpeg_bytes()))
