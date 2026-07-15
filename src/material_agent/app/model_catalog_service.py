from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    role: str
    adapter: str
    name: str
    version: str
    filename: str
    url: str
    sha256: str
    license: str
    bundled_path: str | None = None


DEFAULT_MODEL_CATALOG = (
    ModelSpec(
        model_id="nima-mobilenet-ava-fp16",
        role="aesthetic",
        adapter="openvino-nima",
        name="nima-aesthetic-mobilenet",
        version="litert-community-15308061",
        filename="nima_aesthetic_fp16.tflite",
        url=(
            "https://huggingface.co/litert-community/NIMA-LiteRT/resolve/"
            "15308061b353e9ef1de4c9d33b8f0fab0a7e350e/nima_aesthetic_fp16.tflite"
        ),
        sha256="a5051a0fcced735682735e3e0fd58ee54c83ed664282a003f52235b3dbcb9320",
        license="Apache-2.0",
        bundled_path="/opt/material-agent/models/nima/nima_aesthetic_fp16.tflite",
    ),
    ModelSpec(
        model_id="ssd-mobilenet-v1-coco-opset12",
        role="detection",
        adapter="openvino-ssd-coco",
        name="ssd-mobilenet-v1-12",
        version="onnxmodelzoo-opset12",
        filename="ssd_mobilenet_v1_12.onnx",
        url=(
            "https://huggingface.co/onnxmodelzoo/ssd_mobilenet_v1_12/resolve/"
            "019281f3fcb151a90e491f3b2f0273f9f31bd6be/ssd_mobilenet_v1_12.onnx"
        ),
        sha256="b8fba5e404077d4048d27fcd1667e85e27e192eb9bf51e696c46a3acd7d21058",
        license="Apache-2.0",
        bundled_path="/opt/material-agent/models/detection/ssd_mobilenet_v1_12.onnx",
    ),
    ModelSpec(
        model_id="yunet-face-int8-2023mar",
        role="face_detection",
        adapter="opencv-yunet",
        name="opencv-yunet-int8",
        version="2023mar-int8",
        filename="face_detection_yunet_2023mar_int8.onnx",
        url=(
            "https://huggingface.co/opencv/face_detection_yunet/resolve/"
            "3cc26e7f1014a5ee5d74a42acee58bafc9d0a310/"
            "face_detection_yunet_2023mar_int8.onnx"
        ),
        sha256="321aa5a6afabf7ecc46a3d06bfab2b579dc96eb5c3be7edd365fa04502ad9294",
        license="Apache-2.0",
        bundled_path=(
            "/opt/material-agent/models/detection/face_detection_yunet_2023mar_int8.onnx"
        ),
    ),
)


class ModelCatalogService:
    """Checksum-pinned model installation and active-role selection."""

    def __init__(
        self,
        registry_dir: str | Path,
        *,
        catalog: tuple[ModelSpec, ...] = DEFAULT_MODEL_CATALOG,
    ) -> None:
        self.registry_dir = Path(registry_dir).expanduser().resolve()
        self.models_dir = self.registry_dir / "installed"
        self.selection_path = self.registry_dir / "selections.json"
        self.catalog = {entry.model_id: entry for entry in catalog}
        self._lock = threading.RLock()

    def list_models(self) -> list[dict[str, Any]]:
        selections = self.selections()
        return [self._model_status(spec, selections) for spec in self.catalog.values()]

    def selections(self) -> dict[str, str]:
        with self._lock:
            if not self.selection_path.exists():
                return {}
            payload = json.loads(self.selection_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                raise ValueError(f"invalid model selections file: {self.selection_path}")
            values = payload.get("selections", {})
            if not isinstance(values, dict):
                raise ValueError(f"invalid model selections mapping: {self.selection_path}")
            return {str(role): str(model_id) for role, model_id in values.items()}

    def install(self, model_id: str) -> dict[str, Any]:
        spec = self._spec(model_id)
        destination = self._managed_path(spec)
        with self._lock:
            self._ensure_registry()
            if destination.is_file() and _sha256(destination) == spec.sha256:
                return self._model_status(spec, self.selections())
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{spec.filename}.", suffix=".partial", dir=destination.parent
            )
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                digest = hashlib.sha256()
                with httpx.stream("GET", spec.url, follow_redirects=True, timeout=120.0) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_bytes():
                            digest.update(chunk)
                            output.write(chunk)
                if digest.hexdigest() != spec.sha256:
                    raise ValueError(
                        f"checksum mismatch for {model_id}: expected {spec.sha256}, "
                        f"got {digest.hexdigest()}"
                    )
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
            return self._model_status(spec, self.selections())

    def select(self, model_id: str) -> dict[str, Any]:
        spec = self._spec(model_id)
        status = self._model_status(spec, self.selections())
        if not status["installed"]:
            raise ValueError(f"model is not installed: {model_id}")
        with self._lock:
            selections = self.selections()
            selections[spec.role] = model_id
            self._write_selections(selections)
        return self._model_status(spec, selections)

    def delete(self, model_id: str, *, force: bool = False) -> dict[str, Any]:
        spec = self._spec(model_id)
        destination = self._managed_path(spec)
        with self._lock:
            selections = self.selections()
            if selections.get(spec.role) == model_id and not force:
                raise ValueError(f"model is selected for role {spec.role}; use force to delete")
            removed = destination.is_file()
            if removed:
                destination.unlink()
                parent = destination.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            if force and selections.get(spec.role) == model_id:
                selections.pop(spec.role, None)
                self._write_selections(selections)
            status = self._model_status(spec, selections)
            status["removed"] = removed
            status["bundled_preserved"] = bool(status["bundled"])
            return status

    def resolve_selection(self, role: str) -> dict[str, Any] | None:
        model_id = self.selections().get(role)
        if not model_id:
            return None
        spec = self._spec(model_id)
        status = self._model_status(spec, self.selections())
        if not status["installed"]:
            raise ValueError(f"selected model is unavailable: {model_id}")
        return status

    def _model_status(self, spec: ModelSpec, selections: dict[str, str]) -> dict[str, Any]:
        managed_path = self._managed_path(spec)
        bundled_path = Path(spec.bundled_path) if spec.bundled_path else None
        managed = managed_path.is_file() and _sha256(managed_path) == spec.sha256
        bundled = bool(
            bundled_path
            and bundled_path.is_file()
            and _sha256(bundled_path) == spec.sha256
        )
        resolved_path = managed_path if managed else bundled_path if bundled else None
        return {
            **asdict(spec),
            "installed": bool(managed or bundled),
            "managed": managed,
            "bundled": bundled,
            "selected": selections.get(spec.role) == spec.model_id,
            "resolved_path": str(resolved_path) if resolved_path else None,
            "managed_path": str(managed_path),
        }

    def _managed_path(self, spec: ModelSpec) -> Path:
        model_dir = self.models_dir / spec.model_id
        if model_dir.is_symlink():
            raise ValueError(f"managed model directory must not be a symbolic link: {model_dir}")
        return model_dir / spec.filename

    def _spec(self, model_id: str) -> ModelSpec:
        try:
            return self.catalog[model_id]
        except KeyError as error:
            raise ValueError(f"unknown model id: {model_id}") from error

    def _ensure_registry(self) -> None:
        if self.registry_dir.is_symlink():
            raise ValueError(f"model registry must not be a symbolic link: {self.registry_dir}")
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        if self.models_dir.is_symlink():
            raise ValueError(f"installed model directory must not be a symbolic link: {self.models_dir}")

    def _write_selections(self, selections: dict[str, str]) -> None:
        self._ensure_registry()
        payload = {"schema_version": 1, "selections": dict(sorted(selections.items()))}
        fd, temporary_name = tempfile.mkstemp(
            prefix=".selections.", suffix=".json.tmp", dir=self.registry_dir
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(json.dumps(payload, indent=2) + "\n")
            os.replace(temporary, self.selection_path)
        finally:
            temporary.unlink(missing_ok=True)


def apply_model_selections(config: dict[str, Any]) -> dict[str, Any]:
    management = config.get("model_management", {})
    if not isinstance(management, dict) or not bool(management.get("selection_enabled", False)):
        return config
    registry_dir = _expand_runtime_path(
        str(management.get("registry_dir", "~/.material-agent/models"))
    )
    catalog_path = management.get("catalog_path")
    catalog = load_model_catalog(catalog_path) if catalog_path else DEFAULT_MODEL_CATALOG
    service = ModelCatalogService(registry_dir, catalog=catalog)
    mappings = {
        "aesthetic": ("aesthetic", "model_path"),
        "detection": ("detection", "model_path"),
        "face_detection": ("detection", "face_model_path"),
    }
    local = config.setdefault("local", {})
    for role, (block_name, path_key) in mappings.items():
        selected = service.resolve_selection(role)
        if selected is None:
            continue
        block = local.setdefault(block_name, {})
        expected_adapter = {
            "aesthetic": "openvino-nima",
            "detection": "openvino-ssd-coco",
            "face_detection": "opencv-yunet",
        }[role]
        if selected["adapter"] != expected_adapter:
            raise ValueError(
                f"selected {role} model uses unsupported adapter: {selected['adapter']}"
            )
        block[path_key] = selected["resolved_path"]
        if role != "face_detection":
            block["model_name"] = selected["name"]
            block["model_version"] = selected["version"]
            block["model_id"] = selected["model_id"]
    return config


def _expand_runtime_path(value: str) -> Path:
    work_dir = os.environ.get("MATERIAL_AGENT_WORK_DIR", "")
    value = value.replace("${MATERIAL_AGENT_WORK_DIR}", work_dir)
    return Path(value).expanduser()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model_catalog(path: str | Path) -> tuple[ModelSpec, ...]:
    catalog_path = Path(path).expanduser().resolve()
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("model catalog schema_version must be 1")
    raw_models = payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError("model catalog must contain a non-empty models list")
    catalog = []
    seen = set()
    for index, raw in enumerate(raw_models):
        if not isinstance(raw, dict):
            raise ValueError(f"models[{index}] must be a mapping")
        try:
            spec = ModelSpec(**raw)
        except TypeError as error:
            raise ValueError(f"invalid models[{index}]: {error}") from error
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", spec.model_id):
            raise ValueError(f"invalid model_id: {spec.model_id!r}")
        if spec.model_id in seen:
            raise ValueError(f"duplicate model_id: {spec.model_id}")
        if spec.role not in {"aesthetic", "detection", "face_detection"}:
            raise ValueError(f"unsupported model role: {spec.role}")
        expected_adapter = {
            "aesthetic": "openvino-nima",
            "detection": "openvino-ssd-coco",
            "face_detection": "opencv-yunet",
        }[spec.role]
        if spec.adapter != expected_adapter:
            raise ValueError(f"unsupported adapter {spec.adapter!r} for role {spec.role}")
        if not spec.url.startswith("https://"):
            raise ValueError(f"model URL must use HTTPS: {spec.url}")
        if not re.fullmatch(r"[0-9a-f]{64}", spec.sha256):
            raise ValueError(f"invalid SHA-256 for {spec.model_id}")
        if Path(spec.filename).name != spec.filename:
            raise ValueError(f"model filename must not contain a path: {spec.filename!r}")
        seen.add(spec.model_id)
        catalog.append(spec)
    return tuple(catalog)
