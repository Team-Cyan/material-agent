from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


class EmbeddingRuntime(Protocol):
    def embed(self, image: Image.Image) -> list[float]: ...


class DinoV2EmbeddingAdapter:
    """Lazy DINOv2 image embedding adapter for grouping experiments."""

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: EmbeddingRuntime | None = None):
        self.config = config or {}
        self.model_name = str(self.config.get("model_name", "facebook/dinov2-small"))
        self.device = str(self.config.get("device", "cpu"))
        self.cache_dir = self.config.get("cache_dir")
        self._runtime = runtime

    async def embed_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._embed_sync, jpeg_bytes)

    def _embed_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is None:
            runtime = _TransformersDinoRuntime(
                model_name=self.model_name,
                device=self.device,
                cache_dir=self.cache_dir,
            )
            self._runtime = runtime
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        vector = runtime.embed(image)
        if not vector:
            raise RuntimeError("DINOv2 runtime returned an empty embedding")
        return {
            "vector": [float(value) for value in vector],
            "dimensions": len(vector),
            "model_name": self.model_name,
            "model_version": "transformers",
            "runtime": "transformers",
            "device": self.device,
        }


class _TransformersDinoRuntime:
    def __init__(self, *, model_name: str, device: str, cache_dir: str | None):
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModel
        except ImportError as error:
            raise RuntimeError(
                "DINOv2 embedding requires the local-models optional dependencies"
            ) from error
        kwargs: dict[str, Any] = {"local_files_only": False}
        if cache_dir:
            kwargs["cache_dir"] = str(Path(cache_dir).expanduser())
        self.processor = AutoImageProcessor.from_pretrained(model_name, **kwargs)
        self.model = AutoModel.from_pretrained(model_name, **kwargs).to(device).eval()
        self.device = device
        self.torch = torch

    def embed(self, image: Image.Image) -> list[float]:
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self.torch.inference_mode():
            outputs = self.model(**inputs)
            vector = outputs.pooler_output
            vector = vector / vector.norm(dim=-1, keepdim=True)
        return [float(value) for value in vector[0].detach().cpu().tolist()]
