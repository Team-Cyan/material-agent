from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from ...utils.constants import DINOV2_MODEL_NAME, DINOV2_MODEL_REVISION


class EmbeddingRuntime(Protocol):
    def embed(self, image: Image.Image) -> list[float]: ...


class DinoV2EmbeddingAdapter:
    """Lazy DINOv2 image embedding adapter for grouping experiments."""

    def __init__(
        self, config: dict[str, Any] | None = None, *, runtime: EmbeddingRuntime | None = None
    ):
        self.config = config or {}
        self.model_name = str(self.config.get("model_name", DINOV2_MODEL_NAME))
        configured_revision = str(self.config.get("model_revision", "")).strip()
        self.model_revision = configured_revision or (
            DINOV2_MODEL_REVISION if self.model_name == DINOV2_MODEL_NAME else ""
        )
        self.device = str(self.config.get("device", "cpu"))
        self.cache_dir = self.config.get("cache_dir")
        self._runtime = runtime

    async def embed_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._embed_sync, jpeg_bytes)

    def _embed_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is None:
            if not self.model_revision:
                raise RuntimeError(
                    "Remote DINOv2 loading requires local.embedding.model_revision "
                    "to pin an immutable model revision"
                )
            runtime = _TransformersDinoRuntime(
                model_name=self.model_name,
                model_revision=self.model_revision,
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
            "model_version": self.model_revision or "runtime-injected",
            "runtime": "transformers",
            "device": self.device,
        }


class _TransformersDinoRuntime:
    def __init__(
        self,
        *,
        model_name: str,
        model_revision: str,
        device: str,
        cache_dir: str | None,
    ):
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
        self.processor = AutoImageProcessor.from_pretrained(
            model_name,
            revision=model_revision,
            **kwargs,
        )
        self.model = (
            AutoModel.from_pretrained(
                model_name,
                revision=model_revision,
                use_safetensors=True,
                **kwargs,
            )
            .to(device)
            .eval()
        )
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
