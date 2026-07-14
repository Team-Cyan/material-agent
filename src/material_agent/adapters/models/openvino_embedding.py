from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from PIL import Image


class OpenVinoRuntimePort(Protocol):
    execution_devices: list[str]
    execution_device_readback_error: str | None
    requested_device: str
    compiled_device: str
    fallback_device: str
    fallback_used: bool
    fallback_reason: str | None

    def embed(self, image: Image.Image) -> list[float]: ...


class OpenVinoEmbeddingAdapter:
    """Native OpenVINO ONNX embedding adapter with compiled-model caching."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        runtime: OpenVinoRuntimePort | None = None,
    ):
        self.config = config or {}
        self.model_path = str(Path(str(self.config.get("model_path", ""))).expanduser())
        self.processor_path = str(Path(str(self.config.get("processor_path", ""))).expanduser())
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
        self.allow_batch_fallback = bool(self.config.get("allow_batch_fallback", True))
        bundle_assets = _model_bundle_assets(
            Path(self.model_path),
            Path(self.processor_path),
        )
        self.bundle_assets = [name for name, _ in bundle_assets]
        self.model_digest = _digest_model_bundle_assets(bundle_assets)
        self._runtime = runtime

    async def embed_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return (await self.embed_images([jpeg_bytes]))[0]

    async def embed_images(self, jpeg_images: list[bytes]) -> list[dict[str, Any]]:
        if not jpeg_images:
            return []
        return await asyncio.to_thread(self._embed_many_sync, jpeg_images)

    def _embed_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return self._embed_many_sync([jpeg_bytes])[0]

    def _embed_many_sync(self, jpeg_images: list[bytes]) -> list[dict[str, Any]]:
        runtime = self._runtime
        if runtime is None:
            if not self.model_path:
                raise RuntimeError("OpenVINO embedding requires local.embedding.model_path")
            if not self.processor_path:
                raise RuntimeError("OpenVINO embedding requires local.embedding.processor_path")
            runtime = _OpenVinoRuntime(
                model_path=self.model_path,
                processor_path=self.processor_path,
                device=self.device,
                fallback_device=self.fallback_device,
                compiled_cache_dir=self.compiled_cache_dir,
                performance_hint=self.performance_hint,
                batch_size=self.batch_size,
                max_in_flight=self.max_in_flight,
                infer_requests=self.infer_requests,
                allow_batch_fallback=self.allow_batch_fallback,
            )
            self._runtime = runtime
        decode_started = time.perf_counter()
        images = [Image.open(BytesIO(jpeg_bytes)).convert("RGB") for jpeg_bytes in jpeg_images]
        image_decode_seconds = time.perf_counter() - decode_started
        if hasattr(runtime, "embed_many"):
            vectors = runtime.embed_many(images)
        else:
            vectors = [runtime.embed(image) for image in images]
        if len(vectors) != len(images) or any(not vector for vector in vectors):
            raise RuntimeError("OpenVINO runtime returned an empty embedding")
        requested_device = str(getattr(runtime, "requested_device", self.device))
        compiled_device = str(getattr(runtime, "compiled_device", requested_device))
        fallback_device = str(getattr(runtime, "fallback_device", self.fallback_device))
        fallback_used = bool(getattr(runtime, "fallback_used", False))
        fallback_reason = getattr(runtime, "fallback_reason", None)
        runtime_timing = dict(getattr(runtime, "last_run_timing", {}) or {})
        timing = {
            "image_decode_seconds": round(image_decode_seconds, 6),
            **runtime_timing,
        }
        common = {
            "model_name": Path(self.model_path).name or "fixture-openvino-model",
            "model_version": "onnx-openvino",
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
            "bundle_assets": list(self.bundle_assets),
            "openvino_version": getattr(runtime, "openvino_version", "unknown"),
            "performance_hint": getattr(runtime, "performance_hint", self.performance_hint),
            "batch_size_requested": self.batch_size,
            "batch_size_actual": int(getattr(runtime, "batch_size", 1)),
            "batch_fallback_used": bool(getattr(runtime, "batch_fallback_used", False)),
            "batch_fallback_reason": getattr(runtime, "batch_fallback_reason", None),
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
        if getattr(runtime, "execution_device_readback_error", None):
            common["execution_device_readback_error"] = str(runtime.execution_device_readback_error)
        return [
            {
                **common,
                "vector": [float(value) for value in vector],
                "dimensions": len(vector),
            }
            for vector in vectors
        ]


class _OpenVinoRuntime:
    def __init__(
        self,
        *,
        model_path: str,
        processor_path: str,
        device: str,
        fallback_device: str,
        compiled_cache_dir: str,
        performance_hint: str = "THROUGHPUT",
        batch_size: int = 1,
        max_in_flight: int = 8,
        infer_requests: str | int = "auto",
        allow_batch_fallback: bool = True,
    ):
        model_file = Path(model_path)
        if not model_file.is_file():
            raise RuntimeError(f"OpenVINO model does not exist: {model_file}")
        processor_dir = Path(processor_path)
        if not processor_dir.exists():
            raise RuntimeError(f"OpenVINO processor path does not exist: {processor_dir}")
        try:
            import numpy as np
            import openvino as ov
        except ImportError as error:
            raise RuntimeError(
                "OpenVINO embedding requires the intel-openvino dependencies"
            ) from error
        cache_dir = Path(compiled_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.np = np
        self.openvino_version = str(getattr(ov, "__version__", "unknown"))
        self.processor = _NumpyImageProcessor(processor_dir, np)
        self.core = ov.Core()
        self.ov = ov
        self.requested_device = device
        self.compiled_device = device
        self.fallback_device = fallback_device
        self.fallback_used = False
        self.fallback_reason = None
        self.performance_hint = performance_hint
        self.batch_size_requested = max(1, int(batch_size))
        self.batch_size = self.batch_size_requested
        self.batch_fallback_used = False
        self.batch_fallback_reason = None
        compile_config = {
            "CACHE_DIR": str(cache_dir),
            "PERFORMANCE_HINT": performance_hint,
        }
        compile_started = time.perf_counter()
        try:
            self.compiled = self._compile_model(model_file, device, compile_config, self.batch_size)
        except RuntimeError as error:
            available_devices = [str(value) for value in self.core.available_devices]
            if _should_compile_fallback(
                requested_device=device,
                fallback_device=fallback_device,
                available_devices=available_devices,
                error=error,
            ):
                self.fallback_used = True
                self.fallback_reason = f"{type(error).__name__}: {error}"
                self.compiled_device = fallback_device
                try:
                    self.compiled = self._compile_model(
                        model_file, fallback_device, compile_config, self.batch_size
                    )
                except RuntimeError as fallback_error:
                    if self.batch_size <= 1 or not allow_batch_fallback:
                        raise
                    self._record_batch_fallback(fallback_error)
                    self.compiled = self._compile_model(
                        model_file, fallback_device, compile_config, 1
                    )
            elif self.batch_size > 1 and allow_batch_fallback:
                self._record_batch_fallback(error)
                self.compiled = self._compile_model(model_file, device, compile_config, 1)
            else:
                raise
        self.compile_seconds = time.perf_counter() - compile_started
        (
            self.execution_devices,
            self.execution_device_readback_error,
        ) = _read_execution_devices(self.compiled)
        self.optimal_infer_requests, self.optimal_infer_requests_error = (
            _read_optimal_infer_requests(self.compiled)
        )
        self.infer_requests = _resolve_infer_requests(
            infer_requests,
            optimal=self.optimal_infer_requests,
            maximum=max_in_flight,
        )

    def _compile_model(self, model_file: Path, device: str, config: dict, batch_size: int):
        model = self.core.read_model(str(model_file))
        if batch_size > 1:
            input_port = model.input(0)
            input_shape = list(input_port.get_shape())
            if not input_shape:
                raise RuntimeError("OpenVINO embedding model input has no batch dimension")
            input_shape[0] = batch_size
            model.reshape({input_port.get_any_name(): input_shape})
        return self.core.compile_model(model, device, config)

    def _record_batch_fallback(self, error: RuntimeError) -> None:
        self.batch_fallback_used = True
        self.batch_fallback_reason = f"{type(error).__name__}: {error}"
        self.batch_size = 1

    def embed(self, image: Image.Image) -> list[float]:
        return self.embed_many([image])[0]

    def embed_many(self, images: list[Image.Image]) -> list[list[float]]:
        if not images:
            self.last_run_timing = {}
            return []
        preprocess_started = time.perf_counter()
        tensors = [self.processor(image) for image in images]
        preprocess_seconds = time.perf_counter() - preprocess_started
        input_name = self.compiled.input(0).get_any_name()
        batches = []
        for start in range(0, len(tensors), self.batch_size):
            members = tensors[start : start + self.batch_size]
            valid_count = len(members)
            while len(members) < self.batch_size:
                members.append(members[-1])
            batches.append((start, valid_count, self.np.concatenate(members, axis=0)))

        output_batches: dict[int, tuple[int, Any]] = {}
        queue = self.ov.AsyncInferQueue(self.compiled, self.infer_requests)

        def _complete(request, userdata):
            start, valid_count = userdata
            arrays = [self.np.array(output.data, copy=True) for output in request.output_tensors]
            output_batches[start] = (
                valid_count,
                max(arrays, key=lambda value: value.ndim),
            )

        queue.set_callback(_complete)
        inference_started = time.perf_counter()
        for start, valid_count, batch in batches:
            queue.start_async({input_name: batch}, userdata=(start, valid_count))
        queue.wait_all()
        inference_seconds = time.perf_counter() - inference_started

        postprocess_started = time.perf_counter()
        vectors: list[list[float]] = []
        for start, _, _ in batches:
            valid_count, output = output_batches[start]
            matrix = output[:, 0, :] if output.ndim == 3 else output.reshape(output.shape[0], -1)
            for vector in matrix[:valid_count]:
                vector = vector.astype(self.np.float32, copy=False)
                norm = float(self.np.linalg.norm(vector))
                if norm > 0:
                    vector = vector / norm
                vectors.append([float(value) for value in vector.tolist()])
        postprocess_seconds = time.perf_counter() - postprocess_started
        self.last_run_timing = {
            "compile_seconds": round(self.compile_seconds, 6),
            "preprocess_seconds": round(preprocess_seconds, 6),
            "inference_seconds": round(inference_seconds, 6),
            "postprocess_seconds": round(postprocess_seconds, 6),
            "batch_count": len(batches),
            "image_count": len(images),
        }
        return vectors


class _NumpyImageProcessor:
    def __init__(self, processor_path: Path, np_module):
        config_path = (
            processor_path / "preprocessor_config.json"
            if processor_path.is_dir()
            else processor_path
        )
        if not config_path.is_file():
            raise RuntimeError(f"OpenVINO preprocessor config does not exist: {config_path}")
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("OpenVINO preprocessor config must be a JSON object")
        self.config = payload
        self.np = np_module

    def __call__(self, image: Image.Image):
        image = image.convert("RGB")
        if self.config.get("do_resize", True):
            height, width = _processor_size(self.config.get("size"))
            resample = Image.Resampling(int(self.config.get("resample", Image.Resampling.BILINEAR)))
            image = image.resize((width, height), resample=resample)
        if self.config.get("do_center_crop", False):
            crop_height, crop_width = _processor_size(self.config.get("crop_size"))
            left = max(0, (image.width - crop_width) // 2)
            top = max(0, (image.height - crop_height) // 2)
            image = image.crop((left, top, left + crop_width, top + crop_height))

        array = self.np.asarray(image, dtype=self.np.float32)
        if self.config.get("do_rescale", True):
            array = array * float(self.config.get("rescale_factor", 1.0 / 255.0))
        if self.config.get("do_normalize", True):
            mean = self.np.asarray(
                self.config.get("image_mean", [0.485, 0.456, 0.406]),
                dtype=self.np.float32,
            )
            std = self.np.asarray(
                self.config.get("image_std", [0.229, 0.224, 0.225]),
                dtype=self.np.float32,
            )
            if mean.shape != (3,) or std.shape != (3,) or self.np.any(std == 0):
                raise RuntimeError(
                    "OpenVINO preprocessor mean/std must contain three non-zero values"
                )
            array = (array - mean) / std
        data_format = str(self.config.get("data_format", "channels_first"))
        if data_format == "channels_first":
            array = self.np.transpose(array, (2, 0, 1))
        elif data_format != "channels_last":
            raise RuntimeError(f"unsupported OpenVINO preprocessor data_format: {data_format!r}")
        return self.np.expand_dims(array, axis=0).astype(self.np.float32, copy=False)


def _processor_size(raw_size) -> tuple[int, int]:
    if isinstance(raw_size, int) and raw_size > 0:
        return raw_size, raw_size
    if isinstance(raw_size, dict):
        height = raw_size.get("height")
        width = raw_size.get("width")
        if isinstance(height, int) and height > 0 and isinstance(width, int) and width > 0:
            return height, width
    raise RuntimeError(
        "OpenVINO preprocessor size must be a positive integer or contain height and width"
    )


def _model_bundle_digest(
    model_path: Path,
    processor_path: Path | None = None,
) -> str:
    return _digest_model_bundle_assets(_model_bundle_assets(model_path, processor_path))


def _digest_model_bundle_assets(assets: list[tuple[str, Path]]) -> str:
    digest = hashlib.sha256()
    for name, path in assets:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _model_bundle_assets(
    model_path: Path,
    processor_path: Path | None = None,
) -> list[tuple[str, Path]]:
    assets: dict[str, Path] = {}
    excluded: set[Path] = set()
    if model_path.is_file():
        assets[f"model/{model_path.name}"] = model_path
        excluded.add(model_path.resolve())
        for relative_path in _onnx_external_data_locations(model_path):
            external_path = model_path.parent / relative_path
            if not external_path.is_file():
                raise ValueError(f"ONNX external data file does not exist: {external_path}")
            assets[f"external/{relative_path.as_posix()}"] = external_path
            excluded.add(external_path.resolve())

    if processor_path is not None and processor_path.is_file():
        if processor_path.resolve() not in excluded:
            assets[f"processor/{processor_path.name}"] = processor_path
    elif processor_path is not None and processor_path.is_dir():
        for path in sorted(processor_path.glob("*.json")):
            if path.name == "bundle.json":
                continue
            if path.resolve() in excluded:
                continue
            relative_path = path.relative_to(processor_path)
            assets[f"processor/{relative_path.as_posix()}"] = path
    return sorted(assets.items())


def _onnx_external_data_locations(model_path: Path) -> list[Path]:
    try:
        import onnx
    except ImportError as error:
        raise RuntimeError(
            "OpenVINO model bundle inspection requires the intel-openvino dependencies"
        ) from error

    model = onnx.load_model(str(model_path), load_external_data=False)
    locations: set[Path] = set()
    for tensor in _iter_onnx_model_tensors(model):
        external_data = getattr(tensor, "external_data", ())
        if not external_data:
            continue
        values = {str(entry.key): str(entry.value) for entry in external_data}
        location = values.get("location", "")
        if not location:
            raise ValueError(f"ONNX tensor {tensor.name!r} has external data without a location")
        locations.add(_safe_external_data_path(location))
    return sorted(locations, key=lambda path: path.as_posix())


def _iter_onnx_model_tensors(model):
    yield from _iter_onnx_graph_tensors(model.graph)
    for training_info in getattr(model, "training_info", ()):
        yield from _iter_onnx_graph_tensors(training_info.initialization)
        yield from _iter_onnx_graph_tensors(training_info.algorithm)
    for function in getattr(model, "functions", ()):
        yield from _iter_onnx_node_tensors(function.node)


def _iter_onnx_graph_tensors(graph):
    yield from graph.initializer
    for sparse in graph.sparse_initializer:
        yield sparse.values
        yield sparse.indices
    yield from _iter_onnx_node_tensors(graph.node)


def _iter_onnx_node_tensors(nodes):
    for node in nodes:
        for attribute in node.attribute:
            if attribute.HasField("t"):
                yield attribute.t
            yield from attribute.tensors
            if attribute.HasField("sparse_tensor"):
                yield attribute.sparse_tensor.values
                yield attribute.sparse_tensor.indices
            for sparse in attribute.sparse_tensors:
                yield sparse.values
                yield sparse.indices
            if attribute.HasField("g"):
                yield from _iter_onnx_graph_tensors(attribute.g)
            for graph in attribute.graphs:
                yield from _iter_onnx_graph_tensors(graph)


def _safe_external_data_path(location: str) -> Path:
    normalized = location.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.parts[0].endswith(":")
    ):
        raise ValueError(f"unsafe ONNX external data location: {location!r}")
    return Path(*relative.parts)


def _cache_identity(
    model_digest: str,
    device: str,
    openvino_version: str,
    *,
    fallback_device: str = "",
    compiled_device: str = "",
) -> str:
    payload = (
        f"{model_digest}|{device}|{fallback_device}|{compiled_device}|{openvino_version}"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _should_compile_fallback(
    *,
    requested_device: str,
    fallback_device: str,
    available_devices: list[str],
    error: RuntimeError,
) -> bool:
    fallback = fallback_device.strip()
    if not fallback or fallback.upper() == requested_device.strip().upper():
        return False
    if _request_has_unavailable_device(requested_device, available_devices):
        return True
    message = str(error).lower()
    unavailable_markers = (
        "not registered in the openvino runtime",
        "no available devices",
        "no supported devices",
        "device is not available",
        "no opencl device",
    )
    return any(marker in message for marker in unavailable_markers)


def _request_has_unavailable_device(requested: str, available: list[str]) -> bool:
    request = requested.strip().upper()
    if not request or request in {"AUTO", "MULTI", "HETERO"}:
        return False
    candidates = (
        [candidate.strip() for candidate in request.split(":", 1)[1].split(",")]
        if ":" in request
        else [request]
    )
    visible = [str(device).strip().upper() for device in available]
    return any(
        candidate
        and not any(device == candidate or device.startswith(f"{candidate}.") for device in visible)
        for candidate in candidates
    )


def _read_execution_devices(compiled) -> tuple[list[str], str | None]:
    try:
        devices = [str(value) for value in compiled.get_property("EXECUTION_DEVICES")]
        if not devices:
            return ["unknown"], "EXECUTION_DEVICES returned no devices"
        return devices, None
    except Exception as error:
        return ["unknown"], f"{type(error).__name__}: {error}"


def _read_optimal_infer_requests(compiled) -> tuple[int | None, str | None]:
    try:
        value = int(compiled.get_property("OPTIMAL_NUMBER_OF_INFER_REQUESTS"))
    except (RuntimeError, TypeError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"
    if value < 1:
        return None, "OPTIMAL_NUMBER_OF_INFER_REQUESTS returned a value below 1"
    return value, None


def _resolve_infer_requests(
    requested: str | int,
    *,
    optimal: int | None,
    maximum: int,
) -> int:
    cap = max(1, int(maximum))
    if isinstance(requested, int) and not isinstance(requested, bool):
        return min(cap, max(1, requested))
    if str(requested).strip().lower() != "auto":
        raise RuntimeError("OpenVINO infer_requests must be 'auto' or a positive integer")
    return min(cap, optimal or 1)


def _portable_path(value: str) -> str:
    path = Path(value).expanduser()
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        pass
    try:
        return str(Path("~") / path.relative_to(Path.home()))
    except ValueError:
        return str(path)
