from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


DEFAULT_SCENE_PROMPTS = {
    "people": "a photograph of a person or people",
    "concert": "a live music concert photograph of a performer playing an instrument on stage",
    "sports": "a sports or fast action photograph",
    "landscape": "a landscape or outdoor nature photograph",
    "cityscape": "a city street or urban architecture photograph",
    "indoor": "an indoor room or interior photograph",
    "food": "a food or drink photograph",
    "animal": "an animal or pet photograph",
    "screenshot": "a software screenshot, document, diagram, or non-photographic interface",
    "other": "an ordinary photograph not described by the other categories",
}


class SemanticRuntime(Protocol):
    def classify(self, image: Image.Image, prompts: list[str]) -> list[float]: ...


class OpenClipSemanticAdapter:
    """Optional zero-shot scene classifier with lazy OpenCLIP model loading."""

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: SemanticRuntime | None = None):
        self.config = config or {}
        self.model_name = str(self.config.get("model_name", "MobileCLIP2-S0"))
        self.pretrained = str(self.config.get("pretrained", "dfndr2b"))
        self.device = str(self.config.get("device", "cpu"))
        self.min_confidence = float(self.config.get("min_confidence", 0.30))
        raw_prompts = self.config.get("prompts", DEFAULT_SCENE_PROMPTS)
        if not isinstance(raw_prompts, dict) or not raw_prompts:
            raise ValueError("local.semantic.prompts must be a non-empty mapping")
        self.prompts = {str(label): str(prompt) for label, prompt in raw_prompts.items()}
        self._runtime = runtime

    async def classify_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._classify_sync, jpeg_bytes)

    def _classify_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is None:
            runtime = _OpenClipRuntime(
                model_name=self.model_name,
                pretrained=self.pretrained,
                device=self.device,
                cache_dir=self.config.get("cache_dir"),
            )
            self._runtime = runtime
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        labels = list(self.prompts)
        probabilities = runtime.classify(image, [self.prompts[label] for label in labels])
        if len(probabilities) != len(labels):
            raise RuntimeError("semantic runtime returned a probability count that does not match prompts")
        ranked = sorted(zip(labels, probabilities, strict=True), key=lambda row: row[1], reverse=True)
        raw_label, confidence = ranked[0]
        scene = "other" if raw_label == "screenshot" or confidence < self.min_confidence else raw_label
        return {
            "scene": scene,
            "scene_raw": raw_label,
            "confidence": round(float(confidence), 6),
            "non_photo": raw_label == "screenshot",
            "model_name": self.model_name,
            "model_version": self.pretrained,
            "runtime": "open_clip",
            "device": self.device,
            "probabilities": {label: round(float(value), 6) for label, value in ranked},
        }


class _OpenClipRuntime:
    def __init__(
        self,
        *,
        model_name: str,
        pretrained: str,
        device: str,
        cache_dir: str | None,
    ):
        try:
            import open_clip
            import torch
        except ImportError as error:
            raise RuntimeError(
                "OpenCLIP semantic scoring requires the local-models optional dependencies"
            ) from error

        kwargs: dict[str, Any] = {"device": device}
        if cache_dir:
            kwargs["cache_dir"] = str(Path(cache_dir).expanduser())
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=pretrained,
            **kwargs,
        )
        model.eval()
        self.model = model
        self.preprocess = preprocess
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.device = device
        self.torch = torch

    def classify(self, image: Image.Image, prompts: list[str]) -> list[float]:
        image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        text_tensor = self.tokenizer(prompts).to(self.device)
        with self.torch.inference_mode():
            image_features = self.model.encode_image(image_tensor)
            text_features = self.model.encode_text(text_tensor)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            probabilities = (100.0 * image_features @ text_features.T).softmax(dim=-1)[0]
        return [float(value) for value in probabilities.detach().cpu().tolist()]
