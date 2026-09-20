from __future__ import annotations

from io import BytesIO
import hashlib
import time

import numpy as np
from PIL import Image

from ..utils.constants import VISION_DIMS
from ..adapters.models.inference_contract import (
    REVISION,
    ResultCache,
    AssetSnapshot,
    bounded_reason,
    fallback_record,
    identity,
    preprocessing_spec,
    runtime_version,
)


class AsyncLocalClient:
    """Local, non-generative fallback used by the NAS-first material-agent path."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.output_language = self.config.get("output_language", "zh")
        self.inference = self.config.get("inference", {})
        self.runtime = self.inference.get("runtime", "cpu")
        self.semantic_config = self.config.get("semantic", {})
        self.quality_config = self.config.get("quality", {})
        self.aesthetic_config = self.config.get("aesthetic", {})
        self.detection_config = self.config.get("detection", {})
        self.embedding_config = self.config.get("embedding", {})
        self.face_config = self.config.get("face", {})
        self._semantic = None
        self._quality = None
        self._aesthetic = None
        self._detection = None
        self._embedding = None
        self._face = None
        self.embedding_result_cache_size = int(self.embedding_config.get("result_cache_size", 256))
        self._embedding_cache = ResultCache(self.embedding_result_cache_size)
        self._embedding_result_cache = self._embedding_cache.values
        self.aesthetic_result_cache_size = int(self.aesthetic_config.get("result_cache_size", 256))
        self._aesthetic_cache = ResultCache(self.aesthetic_result_cache_size)
        self._aesthetic_result_cache = self._aesthetic_cache.values
        self._result_identities = {}
        self._asset_snapshots = {}
        # Package installations are fixed for a client lifetime, including absence.
        # Recreate the client after changing the environment; assets/config still
        # invalidate result identities on each lookup. Keep heuristic startup lazy.
        self._runtime_versions = None

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        heuristic_started = time.perf_counter()
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
        result["_timing"] = {
            "local_heuristic_seconds": round(time.perf_counter() - heuristic_started, 6)
        }
        if self.detection_config.get("enabled", False):
            try:
                detection = await self._object_detector().detect_objects(jpeg_bytes)
            except Exception as error:
                if self.detection_config.get("enforce_available", False):
                    raise
                result["_detection"] = {
                    "status": "fallback",
                    "error": bounded_reason(error),
                    "execution": fallback_record(error, "detection"),
                }
            else:
                result["_detection"] = {"status": "model", **detection}
                if detection.get("scene") and detection["scene"] != "other":
                    result["scene"] = detection["scene"]
                    result["scene_raw"] = f"object:{detection['scene']}"
                result["_scoring_mode"] = "hybrid"
                result["_model_stack"] = [detection["model_name"]]
                result["_runtime_components"].append(_model_runtime_component(detection))
                result["_runtime"] = "+".join(result["_runtime_components"])
        if self.semantic_config.get("enabled", False):
            try:
                semantic = await self._semantic_classifier().classify_image(jpeg_bytes)
            except Exception as error:
                if self.semantic_config.get("enforce_available", False):
                    raise
                result["_semantic"] = {
                    "status": "fallback",
                    "error": bounded_reason(error),
                    "execution": fallback_record(error, "semantic"),
                }
            else:
                result["scene"] = semantic["scene"]
                result["scene_raw"] = semantic["scene_raw"]
                result["_scoring_mode"] = "hybrid"
                result["_runtime_components"].append(f"{semantic['runtime']}:{semantic['device']}")
                result["_runtime"] = "+".join(result["_runtime_components"])
                model_stack = list(result.get("_model_stack", []))
                model_stack.append(semantic["model_name"])
                result["_model_stack"] = model_stack
                result["_semantic"] = {"status": "model", **semantic}
        if self.quality_config.get("enabled", False):
            try:
                quality = await self._quality_scorer().score_quality(jpeg_bytes)
            except Exception as error:
                if self.quality_config.get("enforce_available", False):
                    raise
                result["_quality"] = {
                    "status": "fallback",
                    "error": bounded_reason(error),
                    "execution": fallback_record(error, "quality"),
                }
            else:
                result["_scoring_mode"] = "hybrid"
                result["_quality"] = {"status": "model", **quality}
                model_stack = list(result.get("_model_stack", []))
                model_stack.extend(quality["model_names"])
                result["_model_stack"] = model_stack
                result["_runtime_components"].append(f"{quality['runtime']}:{quality['device']}")
                result["_runtime"] = "+".join(result["_runtime_components"])
        if self.aesthetic_config.get("enabled", False):
            try:
                aesthetic = await self.score_aesthetic(jpeg_bytes)
            except Exception as error:
                if self.aesthetic_config.get("enforce_available", False):
                    raise
                result["_aesthetic"] = {
                    "status": "fallback",
                    "error": bounded_reason(error),
                    "execution": fallback_record(error, "aesthetic"),
                }
            else:
                result["_aesthetic"] = {"status": "model", **aesthetic}
                result["aesthetic_score"] = round(float(aesthetic["score"]), 2)
                result["_scoring_mode"] = "hybrid"
                model_stack = list(result.get("_model_stack", []))
                model_stack.append(aesthetic["model_name"])
                result["_model_stack"] = model_stack
                result["_runtime_components"].append(_model_runtime_component(aesthetic))
                result["_runtime"] = "+".join(result["_runtime_components"])
        if self.embedding_config.get("enabled", False):
            try:
                embedding = await self.embed_image(jpeg_bytes)
            except Exception as error:
                if self.embedding_config.get("enforce_available", False):
                    raise
                result["_embedding"] = {
                    "status": "fallback",
                    "error": bounded_reason(error),
                    "execution": fallback_record(error, "embedding"),
                }
            else:
                vector = embedding.pop("vector")
                result["_embedding"] = {"status": "model", **embedding}
                result["_embedding_vector"] = vector
                result["_scoring_mode"] = "hybrid"
                model_stack = list(result.get("_model_stack", []))
                model_stack.append(embedding["model_name"])
                result["_model_stack"] = model_stack
                result["_runtime_components"].append(_embedding_runtime_component(embedding))
                result["_runtime"] = "+".join(result["_runtime_components"])
        if self.face_config.get("enabled", False):
            try:
                face = await self._face_scorer().detect_faces(jpeg_bytes)
            except Exception as error:
                if self.face_config.get("enforce_available", False):
                    raise
                result["_face"] = {
                    "status": "fallback",
                    "error": bounded_reason(error),
                    "execution": fallback_record(error, "face"),
                }
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
        return (await self.embed_images([jpeg_bytes]))[0]

    async def embed_images(self, jpeg_images: list[bytes]) -> list[dict]:
        return await self._cached_model_results("embedding", jpeg_images)

    async def score_aesthetic(self, jpeg_bytes: bytes) -> dict:
        return (await self.score_aesthetics([jpeg_bytes]))[0]

    async def score_aesthetics(self, jpeg_images: list[bytes]) -> list[dict]:
        return await self._cached_model_results("aesthetic", jpeg_images)

    async def _cached_model_results(self, kind, payloads):
        if not payloads:
            return []
        config = getattr(self, kind + "_config")
        cache = getattr(self, "_" + kind + "_cache")
        asset_paths = (str(config.get("model_path", "")), config.get("processor_path"))
        snapshot = self._asset_snapshots.get(kind)
        if snapshot is None or (snapshot.model_path, snapshot.processor_path) != asset_paths:
            snapshot = self._asset_snapshots[kind] = AssetSnapshot(*asset_paths)
        assets = snapshot.current()
        if self._runtime_versions is None:
            self._runtime_versions = {
                name: runtime_version(name)
                for name in ("openvino", "numpy", "Pillow", "torch", "transformers")
            }
        key = identity(
            {
                "schema": REVISION,
                "kind": kind,
                "config": config,
                "inference": self.inference,
                "assets": assets,
                "preprocessing": preprocessing_spec(kind, config),
                "versions": self._runtime_versions,
            }
        )
        previous = self._result_identities.get(kind)
        if previous is not None and previous != key:
            cache.clear()
            setattr(self, "_" + kind, None)
        self._result_identities[kind] = key
        result = [None] * len(payloads)
        missing = {}
        cacheable = assets["state"] == "available" or config.get("runtime") == "transformers"
        # Custom adapters must declare a revision before enabling cache reuse.
        scorer = getattr(self, "_" + kind)
        custom_revision = getattr(scorer, "result_cache_revision", None)
        if custom_revision:
            key = identity({"base": key, "custom_revision": custom_revision})
            cacheable = True
        for index, payload in enumerate(payloads):
            content_key = identity({"model": key, "content": hashlib.sha256(payload).hexdigest()})
            cached = cache.get(content_key) if cacheable else None
            if cached is not None:
                cached["result_cache"] = {"identity": content_key, "status": "hit"}
                result[index] = cached
            else:
                missing.setdefault(content_key, (payload, []))[1].append(index)
        keys = list(missing)
        for start in range(0, len(keys), 32):
            chunk = keys[start : start + 32]
            inputs = [missing[k][0] for k in chunk]
            scorer = getattr(self, "_" + kind + "_scorer")()
            if kind == "embedding":
                predictions = (
                    await scorer.embed_images(inputs)
                    if hasattr(scorer, "embed_images")
                    else [await scorer.embed_image(p) for p in inputs]
                )
            else:
                predictions = await scorer.score_images(inputs)
            if len(predictions) != len(inputs):
                raise RuntimeError(kind + " adapter returned an unexpected result count")
            from copy import deepcopy

            for content_key, prediction in zip(chunk, predictions, strict=True):
                stored = deepcopy(prediction)
                stored["result_cache"] = {
                    "identity": content_key,
                    "status": "miss" if cacheable else "bypass",
                }
                if cacheable:
                    cache.put(content_key, stored)
                for index in missing[content_key][1]:
                    result[index] = deepcopy(stored)
        if any(row is None for row in result):
            raise RuntimeError("model cache failed to resolve every input")
        return result

    def clear_embedding_result_cache(self) -> None:
        self._embedding_cache.clear()

    def clear_aesthetic_result_cache(self) -> None:
        self._aesthetic_cache.clear()

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

    def _object_detector(self):
        if self._detection is None:
            from ..adapters.models.openvino_ssd_detection import (
                OpenVinoSsdObjectDetectorAdapter,
            )

            detection_config = {
                **self.detection_config,
                "fallback_device": self.detection_config.get(
                    "fallback_device", self.inference.get("fallback_device", "CPU")
                ),
            }
            self._detection = OpenVinoSsdObjectDetectorAdapter(detection_config)
        return self._detection

    def _aesthetic_scorer(self):
        if self._aesthetic is None:
            from ..adapters.models.openvino_nima_aesthetic import OpenVinoNimaAestheticAdapter

            aesthetic_config = {
                **self.aesthetic_config,
                "fallback_device": self.aesthetic_config.get(
                    "fallback_device", self.inference.get("fallback_device", "CPU")
                ),
            }
            self._aesthetic = OpenVinoNimaAestheticAdapter(aesthetic_config)
        return self._aesthetic

    def _embedding_scorer(self):
        if self._embedding is None:
            embedding_config = {
                **self.embedding_config,
                "cache_dir": self.embedding_config.get(
                    "cache_dir", self.inference.get("model_cache_dir")
                ),
                "fallback_device": self.embedding_config.get(
                    "fallback_device", self.inference.get("fallback_device", "CPU")
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


def _model_runtime_component(model_result: dict) -> str:
    runtime = str(model_result.get("runtime", "unknown"))
    execution_devices = model_result.get("execution_devices")
    if isinstance(execution_devices, list):
        actual = [str(device) for device in execution_devices if str(device).strip()]
        device = ",".join(actual) if actual else "unknown"
    else:
        device = str(model_result.get("device", "unknown"))
    return f"{runtime}:{device}"


def _embedding_runtime_component(embedding: dict) -> str:
    return _model_runtime_component(embedding)
