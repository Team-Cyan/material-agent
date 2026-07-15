from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from .openvino_embedding import (
    _cache_identity,
    _portable_path,
    _read_execution_devices,
    _read_optimal_infer_requests,
    _resolve_infer_requests,
    _should_compile_fallback,
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

    async def score_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return (await self.score_images([jpeg_bytes]))[0]

    async def score_images(self, jpeg_images: list[bytes]) -> list[dict[str, Any]]:
        if not jpeg_images:
            return []
        return await asyncio.to_thread(self._score_many_sync, jpeg_images)

    def _score_many_sync(self, jpeg_images: list[bytes]) -> list[dict[str, Any]]:
        runtime = self._runtime
        if runtime is None:
            if not self.model_path:
                raise RuntimeError("OpenVINO NIMA requires local.aesthetic.model_path")
            runtime = _OpenVinoNimaRuntime(
                model_path=self.model_path,
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
            "cache_identity": _cache_identity(
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
                "score": round(float(score), 6),
                "distribution": [round(float(value), 8) for value in distribution],
            }
            for score, distribution in predictions
        ]


class _OpenVinoNimaRuntime:
    def __init__(
        self,
        *,
        model_path: str,
        device: str,
        fallback_device: str,
        compiled_cache_dir: str,
        performance_hint: str,
        batch_size: int,
        max_in_flight: int,
        infer_requests: str | int,
    ):
        model_file = Path(model_path)
        if not model_file.is_file():
            raise RuntimeError(f"OpenVINO NIMA model does not exist: {model_file}")
        try:
            import numpy as np
            import openvino as ov
        except ImportError as error:
            raise RuntimeError("OpenVINO NIMA requires the intel-openvino dependencies") from error
        cache_dir = Path(compiled_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.np = np
        self.ov = ov
        self.core = ov.Core()
        self.openvino_version = str(getattr(ov, "__version__", "unknown"))
        self.requested_device = device
        self.compiled_device = device
        self.fallback_device = fallback_device
        self.fallback_used = False
        self.fallback_reason = None
        self.performance_hint = performance_hint
        self.batch_size = max(1, int(batch_size))
        compile_config = {"CACHE_DIR": str(cache_dir), "PERFORMANCE_HINT": performance_hint}
        compile_started = time.perf_counter()
        model = self.core.read_model(str(model_file))
        input_port = model.input(0)
        shape = list(input_port.get_partial_shape())
        shape[0] = self.batch_size
        model.reshape({input_port.get_any_name(): shape})
        try:
            self.compiled = self.core.compile_model(model, device, compile_config)
        except RuntimeError as error:
            available = [str(value) for value in self.core.available_devices]
            if not _should_compile_fallback(
                requested_device=device,
                fallback_device=fallback_device,
                available_devices=available,
                error=error,
            ):
                raise
            self.fallback_used = True
            self.fallback_reason = f"{type(error).__name__}: {error}"
            self.compiled_device = fallback_device
            self.compiled = self.core.compile_model(model, fallback_device, compile_config)
        self.compile_seconds = time.perf_counter() - compile_started
        self.execution_devices, self.execution_device_readback_error = _read_execution_devices(
            self.compiled
        )
        self.optimal_infer_requests, _ = _read_optimal_infer_requests(self.compiled)
        self.infer_requests = _resolve_infer_requests(
            infer_requests,
            optimal=self.optimal_infer_requests,
            maximum=max_in_flight,
        )

    def score_many(self, images: list[Image.Image]) -> list[tuple[float, list[float]]]:
        if not images:
            self.last_run_timing = {}
            return []
        preprocess_started = time.perf_counter()
        tensors = [self._preprocess(image) for image in images]
        preprocess_seconds = time.perf_counter() - preprocess_started
        batches = []
        for start in range(0, len(tensors), self.batch_size):
            members = tensors[start : start + self.batch_size]
            valid_count = len(members)
            while len(members) < self.batch_size:
                members.append(members[-1])
            batches.append((start, valid_count, self.np.concatenate(members, axis=0)))
        output_batches: dict[int, tuple[int, Any]] = {}
        queue = self.ov.AsyncInferQueue(self.compiled, self.infer_requests)

        def complete(request, userdata):
            start, valid_count = userdata
            output_batches[start] = (
                valid_count,
                self.np.array(request.get_output_tensor(0).data, copy=True),
            )

        queue.set_callback(complete)
        inference_started = time.perf_counter()
        input_name = self.compiled.input(0).get_any_name()
        for start, valid_count, batch in batches:
            queue.start_async({input_name: batch}, userdata=(start, valid_count))
        queue.wait_all()
        inference_seconds = time.perf_counter() - inference_started

        postprocess_started = time.perf_counter()
        results: list[tuple[float, list[float]]] = []
        weights = self.np.arange(1.0, 11.0, dtype=self.np.float32)
        for start, _, _ in batches:
            valid_count, output = output_batches[start]
            matrix = output.reshape(output.shape[0], -1)
            for row in matrix[:valid_count]:
                distribution = row.astype(self.np.float32, copy=False)
                total = float(distribution.sum())
                if total <= 0:
                    raise RuntimeError("OpenVINO NIMA returned an invalid distribution")
                distribution = distribution / total
                results.append((float(distribution @ weights), distribution.tolist()))
        postprocess_seconds = time.perf_counter() - postprocess_started
        self.last_run_timing = {
            "compile_seconds": round(self.compile_seconds, 6),
            "preprocess_seconds": round(preprocess_seconds, 6),
            "inference_seconds": round(inference_seconds, 6),
            "postprocess_seconds": round(postprocess_seconds, 6),
            "batch_count": len(batches),
            "image_count": len(images),
        }
        return results

    def _preprocess(self, image: Image.Image):
        resized = image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
        array = self.np.asarray(resized, dtype=self.np.float32)
        array = array / 127.5 - 1.0
        return self.np.expand_dims(array, axis=0)


def _file_digest(path: Path) -> str:
    if not path.is_file():
        return hashlib.sha256(str(path).encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
