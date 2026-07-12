from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


class OpenVinoRuntimePort(Protocol):
    execution_devices: list[str]

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
        self.compiled_cache_dir = str(
            Path(
                str(
                    self.config.get(
                        "compiled_cache_dir", "~/.material-agent/openvino-cache"
                    )
                )
            ).expanduser()
        )
        self.model_digest = _model_bundle_digest(Path(self.model_path))
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
                compiled_cache_dir=self.compiled_cache_dir,
            )
            self._runtime = runtime
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        vector = runtime.embed(image)
        if not vector:
            raise RuntimeError("OpenVINO runtime returned an empty embedding")
        return {
            "vector": [float(value) for value in vector],
            "dimensions": len(vector),
            "model_name": Path(self.model_path).name or "fixture-openvino-model",
            "model_version": "onnx-openvino",
            "runtime": "openvino",
            "device": self.device,
            "execution_devices": list(runtime.execution_devices),
            "compiled_cache_dir": _portable_path(self.compiled_cache_dir),
            "model_digest": self.model_digest,
            "openvino_version": getattr(runtime, "openvino_version", "unknown"),
            "cache_identity": _cache_identity(
                self.model_digest,
                self.device,
                getattr(runtime, "openvino_version", "unknown"),
            ),
        }


class _OpenVinoRuntime:
    def __init__(
        self,
        *,
        model_path: str,
        processor_path: str,
        device: str,
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
            from transformers import AutoImageProcessor
        except ImportError as error:
            raise RuntimeError(
                "OpenVINO embedding requires intel-openvino and local-models dependencies"
            ) from error
        cache_dir = Path(compiled_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.np = np
        self.openvino_version = str(getattr(ov, "__version__", "unknown"))
        self.processor = AutoImageProcessor.from_pretrained(
            str(processor_dir), local_files_only=True
        )
        self.core = ov.Core()
        model = self.core.read_model(str(model_file))
        self.compiled = self.core.compile_model(
            model,
            device,
            {"CACHE_DIR": str(cache_dir)},
        )
        try:
            self.execution_devices = [
                str(value) for value in self.compiled.get_property("EXECUTION_DEVICES")
            ]
        except RuntimeError:
            self.execution_devices = [device]

    def embed(self, image: Image.Image) -> list[float]:
        inputs = self.processor(images=image, return_tensors="np")
        input_name = self.compiled.input(0).get_any_name()
        outputs = self.compiled({input_name: inputs["pixel_values"]})
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


def _model_bundle_digest(model_path: Path) -> str:
    digest = hashlib.sha256()
    candidates = [model_path, model_path.with_name(f"{model_path.name}_data")]
    for path in candidates:
        if not path.is_file():
            continue
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _cache_identity(model_digest: str, device: str, openvino_version: str) -> str:
    payload = f"{model_digest}|{device}|{openvino_version}".encode()
    return hashlib.sha256(payload).hexdigest()


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
