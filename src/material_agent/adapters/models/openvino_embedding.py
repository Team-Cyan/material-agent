from __future__ import annotations

import asyncio
import hashlib
import json
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
        self.processor_path = str(
            Path(str(self.config.get("processor_path", ""))).expanduser()
        )
        self.device = str(self.config.get("device", "AUTO:GPU,CPU"))
        self.fallback_device = str(self.config.get("fallback_device", "CPU")).strip()
        self.compiled_cache_dir = str(
            Path(
                str(
                    self.config.get(
                        "compiled_cache_dir", "~/.material-agent/openvino-cache"
                    )
                )
            ).expanduser()
        )
        bundle_assets = _model_bundle_assets(
            Path(self.model_path),
            Path(self.processor_path),
        )
        self.bundle_assets = [name for name, _ in bundle_assets]
        self.model_digest = _digest_model_bundle_assets(bundle_assets)
        self._runtime = runtime

    async def embed_image(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._embed_sync, jpeg_bytes)

    def _embed_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
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
            )
            self._runtime = runtime
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        vector = runtime.embed(image)
        if not vector:
            raise RuntimeError("OpenVINO runtime returned an empty embedding")
        requested_device = str(getattr(runtime, "requested_device", self.device))
        compiled_device = str(getattr(runtime, "compiled_device", requested_device))
        fallback_device = str(
            getattr(runtime, "fallback_device", self.fallback_device)
        )
        fallback_used = bool(getattr(runtime, "fallback_used", False))
        fallback_reason = getattr(runtime, "fallback_reason", None)
        result = {
            "vector": [float(value) for value in vector],
            "dimensions": len(vector),
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
                "unknown"
                if getattr(runtime, "execution_device_readback_error", None)
                else "actual"
            ),
            "compiled_cache_dir": _portable_path(self.compiled_cache_dir),
            "model_digest": self.model_digest,
            "bundle_assets": list(self.bundle_assets),
            "openvino_version": getattr(runtime, "openvino_version", "unknown"),
            "cache_identity": _cache_identity(
                self.model_digest,
                requested_device,
                getattr(runtime, "openvino_version", "unknown"),
                fallback_device=fallback_device,
                compiled_device=compiled_device,
            ),
        }
        if getattr(runtime, "execution_device_readback_error", None):
            result["execution_device_readback_error"] = str(
                runtime.execution_device_readback_error
            )
        return result


class _OpenVinoRuntime:
    def __init__(
        self,
        *,
        model_path: str,
        processor_path: str,
        device: str,
        fallback_device: str,
        compiled_cache_dir: str,
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
        model = self.core.read_model(str(model_file))
        self.requested_device = device
        self.compiled_device = device
        self.fallback_device = fallback_device
        self.fallback_used = False
        self.fallback_reason = None
        compile_config = {"CACHE_DIR": str(cache_dir)}
        try:
            self.compiled = self.core.compile_model(model, device, compile_config)
        except RuntimeError as error:
            available_devices = [str(value) for value in self.core.available_devices]
            if not _should_compile_fallback(
                requested_device=device,
                fallback_device=fallback_device,
                available_devices=available_devices,
                error=error,
            ):
                raise
            self.fallback_used = True
            self.fallback_reason = f"{type(error).__name__}: {error}"
            self.compiled_device = fallback_device
            self.compiled = self.core.compile_model(model, fallback_device, compile_config)
        (
            self.execution_devices,
            self.execution_device_readback_error,
        ) = _read_execution_devices(self.compiled)

    def embed(self, image: Image.Image) -> list[float]:
        pixel_values = self.processor(image)
        input_name = self.compiled.input(0).get_any_name()
        outputs = self.compiled({input_name: pixel_values})
        arrays = [self.np.asarray(value) for value in outputs.values()]
        if not arrays:
            return []
        output = max(arrays, key=lambda value: value.ndim)
        vector = output[:, 0, :] if output.ndim == 3 else output.reshape(output.shape[0], -1)
        vector = vector[0].astype(self.np.float32, copy=False)
        norm = float(self.np.linalg.norm(vector))
        if norm > 0:
            vector = vector / norm
        return [float(value) for value in vector.tolist()]


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
                raise RuntimeError("OpenVINO preprocessor mean/std must contain three non-zero values")
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
                raise ValueError(
                    f"ONNX external data file does not exist: {external_path}"
                )
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
        and not any(
            device == candidate or device.startswith(f"{candidate}.")
            for device in visible
        )
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
