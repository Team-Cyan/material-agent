from __future__ import annotations

from io import BytesIO
import hashlib

import numpy as np
from PIL import Image

from ..utils.constants import VISION_DIMS


class AsyncLocalClient:
    """Local, non-generative fallback used by the NAS-first material-agent path."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.output_language = self.config.get("output_language", "zh")
        self.max_concurrent = self.config.get("max_concurrent", 1)
        self.inference = self.config.get("inference", {})
        self.runtime = self.inference.get("runtime", "cpu")
        self.semantic_config = self.config.get("semantic", {})
        self.quality_config = self.config.get("quality", {})
        self.embedding_config = self.config.get("embedding", {})
        self.face_config = self.config.get("face", {})
        self._semantic = None
        self._quality = None
        self._embedding = None
        self._face = None
        self._embedding_result_cache: dict[str, dict] = {}

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        rgb = np.asarray(image, dtype=np.float32) / 255.0
        gray = rgb.mean(axis=2)

        brightness = float(gray.mean())
        contrast = float(gray.std())
        saturation = float((rgb.max(axis=2) - rgb.min(axis=2)).mean())
        high_clip = float((gray > 0.97).mean())
        low_clip = float((gray < 0.03).mean())
        gy, gx = np.gradient(gray)
        edge_energy = float(np.sqrt(gx * gx + gy * gy).mean())

        lighting = _clamp10(8.0 - abs(brightness - 0.48) * 12.0 - (high_clip + low_clip) * 15.0)
        color = _clamp10(4.5 + saturation * 8.0)
        clarity = _clamp10(3.5 + edge_energy * 45.0 + contrast * 8.0)
        composition = _clamp10(5.8 + min(contrast, 0.25) * 6.0)
        subject = _clamp10((clarity * 0.45) + (lighting * 0.35) + 1.0)
        depth = _clamp10(4.5 + contrast * 10.0)
        mood = _clamp10((lighting + color + depth) / 3.0)

        scores = {
            "subject": subject,
            "composition": composition,
            "lighting": lighting,
            "color": color,
            "clarity": clarity,
            "depth": depth,
            "mood": mood,
        }
        result = {
            "scene": "other",
            "scene_raw": "local heuristic" if self.output_language == "en" else "本地启发式",
            "_scoring_mode": "heuristic",
            "_runtime": "cpu",
            "_runtime_components": ["cpu"],
            "_configured_runtime": self.runtime,
            **{dim: round(scores.get(dim, 5.0), 2) for dim in VISION_DIMS},
        }
        if self.semantic_config.get("enabled", False):
            try:
                semantic = await self._semantic_classifier().classify_image(jpeg_bytes)
            except Exception as error:
                if self.semantic_config.get("enforce_available", False):
                    raise
                result["_semantic"] = {
                    "status": "fallback",
                    "error": str(error),
                }
            else:
                result["scene"] = semantic["scene"]
                result["scene_raw"] = semantic["scene_raw"]
                result["_scoring_mode"] = "hybrid"
                result["_runtime_components"].append(
                    f"{semantic['runtime']}:{semantic['device']}"
                )
                result["_runtime"] = "+".join(result["_runtime_components"])
                result["_model_stack"] = [semantic["model_name"]]
                result["_semantic"] = {"status": "model", **semantic}
        if self.quality_config.get("enabled", False):
            try:
                quality = await self._quality_scorer().score_quality(jpeg_bytes)
            except Exception as error:
                if self.quality_config.get("enforce_available", False):
                    raise
                result["_quality"] = {"status": "fallback", "error": str(error)}
            else:
                result["_scoring_mode"] = "hybrid"
                result["_quality"] = {"status": "model", **quality}
                model_stack = list(result.get("_model_stack", []))
                model_stack.extend(quality["model_names"])
                result["_model_stack"] = model_stack
                result["_runtime_components"].append(
                    f"{quality['runtime']}:{quality['device']}"
                )
                result["_runtime"] = "+".join(result["_runtime_components"])
        if self.embedding_config.get("enabled", False):
            try:
                embedding = await self.embed_image(jpeg_bytes)
            except Exception as error:
                if self.embedding_config.get("enforce_available", False):
                    raise
                result["_embedding"] = {"status": "fallback", "error": str(error)}
            else:
                vector = embedding.pop("vector")
                result["_embedding"] = {"status": "model", **embedding}
                result["_embedding_vector"] = vector
                result["_scoring_mode"] = "hybrid"
                model_stack = list(result.get("_model_stack", []))
                model_stack.append(embedding["model_name"])
                result["_model_stack"] = model_stack
                result["_runtime_components"].append(
                    f"{embedding['runtime']}:{embedding['device']}"
                )
                result["_runtime"] = "+".join(result["_runtime_components"])
        if self.face_config.get("enabled", False):
            try:
                face = await self._face_scorer().detect_faces(jpeg_bytes)
            except Exception as error:
                if self.face_config.get("enforce_available", False):
                    raise
                result["_face"] = {"status": "fallback", "error": str(error)}
            else:
                result["_face"] = {"status": "model", **face}
                result["_scoring_mode"] = "hybrid"
                model_stack = list(result.get("_model_stack", []))
                model_stack.append(face["model_name"])
                result["_model_stack"] = model_stack
                result["_runtime_components"].append(f"{face['runtime']}:{face['device']}")
                result["_runtime"] = "+".join(result["_runtime_components"])
        return result

    async def embed_image(self, jpeg_bytes: bytes) -> dict:
        cache_key = hashlib.sha256(jpeg_bytes).hexdigest()
        cached = self._embedding_result_cache.get(cache_key)
        if cached is not None:
            return {**cached, "vector": list(cached["vector"])}
        embedding = await self._embedding_scorer().embed_image(jpeg_bytes)
        self._embedding_result_cache[cache_key] = {
            **embedding,
            "vector": list(embedding["vector"]),
        }
        return embedding

    async def score_image_fast(self, jpeg_bytes: bytes) -> dict[str, float]:
        full = await self.score_image(jpeg_bytes)
        clarity = float(full.get("clarity", 5.0)) / 10.0
        lighting = float(full.get("lighting", 5.0)) / 10.0
        composition = float(full.get("composition", 5.0)) / 10.0
        usable = (clarity + lighting + composition) / 3.0
        return {
            "technical_ok": _clamp01((clarity + lighting) / 2.0),
            "subject_clear": _clamp01(clarity),
            "composition_ok": _clamp01(composition),
            "usable_for_selection": _clamp01(usable),
        }

    async def generate_group_commentary(self, group_data: str) -> str:
        raise RuntimeError("local backend does not generate model commentary")

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        raise RuntimeError("local backend does not generate model commentary")

    def _semantic_classifier(self):
        if self._semantic is None:
            from ..adapters.models.openclip_semantic import OpenClipSemanticAdapter

            semantic_config = {
                **self.semantic_config,
                "cache_dir": self.semantic_config.get(
                    "cache_dir", self.inference.get("model_cache_dir")
                ),
            }
            self._semantic = OpenClipSemanticAdapter(semantic_config)
        return self._semantic

    def _quality_scorer(self):
        if self._quality is None:
            from ..adapters.models.pyiqa_quality import PyIqaQualityAdapter

            self._quality = PyIqaQualityAdapter(self.quality_config)
        return self._quality

    def _embedding_scorer(self):
        if self._embedding is None:
            embedding_config = {
                **self.embedding_config,
                "cache_dir": self.embedding_config.get(
                    "cache_dir", self.inference.get("model_cache_dir")
                ),
            }
            if embedding_config.get("runtime", "transformers") == "openvino":
                from ..adapters.models.openvino_embedding import OpenVinoEmbeddingAdapter

                self._embedding = OpenVinoEmbeddingAdapter(embedding_config)
            else:
                from ..adapters.models.dinov2_embedding import DinoV2EmbeddingAdapter

                self._embedding = DinoV2EmbeddingAdapter(embedding_config)
        return self._embedding

    def _face_scorer(self):
        if self._face is None:
            from ..adapters.models.mediapipe_face import MediaPipeFaceAdapter

            self._face = MediaPipeFaceAdapter(self.face_config)
        return self._face


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp10(value: float) -> float:
    return max(0.0, min(10.0, float(value)))
