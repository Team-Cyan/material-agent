from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image
import threading
from .inference_contract import (
    ModelDeclaration,
    AssetSnapshot,
    asset_identity,
    execution_record,
    result_record,
    preprocessing_spec,
    serialized,
)
from .openvino_session import OpenVinoSession

from .openvino_embedding import (
    _cache_identity,
    _portable_path,
)


class NimaRuntimePort(Protocol):
    execution_devices: list[str]
    execution_device_readback_error: str | None
    requested_device: str
    compiled_device: str
    fallback_device: str
    fallback_used: bool
    fallback_reason: str | None

    def score_many(self, images: list[Image.Image]) -> list[tuple[float, list[float]]]: ...


class OpenVinoNimaAestheticAdapter:
    """NIMA MobileNet aesthetic scorer executed by OpenVINO."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        runtime: NimaRuntimePort | None = None,
    ):
        self.config = config or {}
        self.model_path = str(Path(str(self.config.get("model_path", ""))).expanduser())
        self.device = str(self.config.get("device", "AUTO:GPU,CPU"))
        self.fallback_device = str(self.config.get("fallback_device", "CPU")).strip()
        self.compiled_cache_dir = str(
            Path(
                str(self.config.get("compiled_cache_dir", "~/.material-agent/openvino-cache"))
            ).expanduser()
        )
        self.performance_hint = (
            str(self.config.get("performance_hint", "THROUGHPUT")).strip().upper()
        )
        self.batch_size = max(1, int(self.config.get("batch_size", 1)))
        self.max_in_flight = max(1, int(self.config.get("max_in_flight", 8)))
        self.infer_requests = self.config.get("infer_requests", "auto")
        self.model_digest = _file_digest(Path(self.model_path))
        self._runtime = runtime
        self._execution_lock = threading.RLock()
        self._asset_snapshot = AssetSnapshot(self.model_path, None)
        self._asset_state = self._asset_snapshot.current()

    async def score_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return (await self.score_images([jpeg_bytes]))[0]

    async def score_images(self, jpeg_images: list[bytes]) -> list[dict[str, Any]]:
        if not jpeg_images:
            return []
        results = []
        for start in range(0, len(jpeg_images), 32):
            results.extend(
                await asyncio.to_thread(self._score_many_sync, jpeg_images[start : start + 32])
            )
        return results

    @serialized
    def _score_many_sync(self, jpeg_images: list[bytes]) -> list[dict[str, Any]]:
        current_assets = self._asset_snapshot.current()
        if current_assets != self._asset_state:
            self._runtime = None
            self._asset_state = current_assets
            self.model_digest = _file_digest(Path(self.model_path))
        runtime = self._runtime
        if runtime is None:
            if not self.model_path:
                raise RuntimeError("OpenVINO NIMA requires local.aesthetic.model_path")
            runtime = _OpenVinoNimaRuntime(
                model_path=self.model_path,
                model_name=self.config.get("model_name", "nima-aesthetic-mobilenet"),
                model_version=self.config.get("model_version", "litert-community-15308061"),
                device=self.device,
                fallback_device=self.fallback_device,
                compiled_cache_dir=self.compiled_cache_dir,
                performance_hint=self.performance_hint,
                batch_size=self.batch_size,
                max_in_flight=self.max_in_flight,
                infer_requests=self.infer_requests,
            )
            self._runtime = runtime
        decode_started = time.perf_counter()
        images = [Image.open(BytesIO(payload)).convert("RGB") for payload in jpeg_images]
        image_decode_seconds = time.perf_counter() - decode_started
        predictions = runtime.score_many(images)
        if len(predictions) != len(images):
            raise RuntimeError("OpenVINO NIMA returned an unexpected result count")

        requested_device = str(getattr(runtime, "requested_device", self.device))
        compiled_device = str(getattr(runtime, "compiled_device", requested_device))
        fallback_device = str(getattr(runtime, "fallback_device", self.fallback_device))
        fallback_used = bool(getattr(runtime, "fallback_used", False))
        fallback_reason = getattr(runtime, "fallback_reason", None)
        timing = {
            "image_decode_seconds": round(image_decode_seconds, 6),
            **dict(getattr(runtime, "last_run_timing", {}) or {}),
        }
        common = {
            "model_name": str(self.config.get("model_name", "nima-aesthetic-mobilenet")),
            "model_version": str(self.config.get("model_version", "litert-community-15308061")),
            "runtime": "openvino",
            "device": self.device,
            "requested_device": requested_device,
            "compiled_device": compiled_device,
            "fallback_device": fallback_device,
            "fallback_used": fallback_used,
            "fallback_reason": str(fallback_reason) if fallback_reason else None,
            "execution_devices": list(runtime.execution_devices),
            "execution_device_readback": (
                "unknown" if getattr(runtime, "execution_device_readback_error", None) else "actual"
            ),
            "compiled_cache_dir": _portable_path(self.compiled_cache_dir),
            "model_digest": self.model_digest,
            "openvino_version": getattr(runtime, "openvino_version", "unknown"),
            "performance_hint": getattr(runtime, "performance_hint", self.performance_hint),
            "batch_size_requested": self.batch_size,
            "batch_size_actual": int(getattr(runtime, "batch_size", self.batch_size)),
            "infer_requests": int(getattr(runtime, "infer_requests", 1)),
            "optimal_infer_requests": getattr(runtime, "optimal_infer_requests", None),
            "timing": timing,
            "inference_run_id": uuid.uuid4().hex,
            "execution": execution_record(runtime),
            "compile_event_id": getattr(runtime, "compile_event_id", None),
            "cache_identity": getattr(runtime, "compiled_cache_identity", None)
            or _cache_identity(
                self.model_digest,
                requested_device,
                getattr(runtime, "openvino_version", "unknown"),
                fallback_device=fallback_device,
                compiled_device=compiled_device,
            ),
        }
        readback_error = getattr(runtime, "execution_device_readback_error", None)
        if readback_error:
            common["execution_device_readback_error"] = str(readback_error)
        return [
            {
                **common,
                "result_cache": result_record(content, self.config, common["execution"]),
                "score": round(float(score), 6),
                "distribution": [round(float(value), 8) for value in distribution],
            }
            for content, (score, distribution) in zip(jpeg_images, predictions, strict=True)
        ]


class _OpenVinoNimaRuntime(OpenVinoSession):
    def __init__(
        self,
        *,
        model_path,
        device,
        fallback_device,
        compiled_cache_dir,
        performance_hint,
        batch_size,
        max_in_flight,
        infer_requests,
        model_name="nima-aesthetic-mobilenet",
        model_version="litert-community-15308061",
    ):
        declaration = ModelDeclaration.create(
            model_name,
            model_version,
            asset_identity(model_path),
            preprocessing_spec("aesthetic"),
            "nima-distribution-expectation-v1",
        )
        super().__init__(
            model_path=model_path,
            declaration=declaration,
            device=device,
            fallback_device=fallback_device,
            compiled_cache_dir=compiled_cache_dir,
            performance_hint=performance_hint,
            batch_size=batch_size,
            max_in_flight=max_in_flight,
            infer_requests=infer_requests,
        )

    def score_many(self, images):
        return self.run(images, self._preprocess, self._normalize)

    def _normalize(self, arrays):
        output = arrays[0]
        matrix = output.reshape(output.shape[0], -1)
        if matrix.shape[1] != 10:
            raise RuntimeError("OpenVINO NIMA requires ten rating buckets")
        results = []
        weights = self.np.arange(1.0, 11.0, dtype=self.np.float32)
        for row in matrix:
            distribution = row.astype(self.np.float32, copy=False)
            total = float(distribution.sum())
            if total <= 0 or self.np.any(distribution < 0):
                raise RuntimeError("OpenVINO NIMA returned an invalid distribution")
            distribution = distribution / total
            results.append((float(distribution @ weights), distribution.tolist()))
        return results

    def _preprocess(self, image):
        spec = self.declaration.record()["preprocessing"]
        resized = image.convert(spec["color"]).resize(tuple(spec["resize"]), spec["resample"])
        array = self.np.asarray(resized, dtype=self.np.float32)
        return self.np.expand_dims(array / spec["divisor"] + spec["offset"], axis=0)


def _file_digest(path: Path) -> str:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
