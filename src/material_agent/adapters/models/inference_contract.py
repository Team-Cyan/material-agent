"""Versioned execution facts, independent of model score semantics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from functools import wraps
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import threading

REVISION = "local-inference-v1"


def identity(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def runtime_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def asset_identity(model_path, processor_path=None):
    # Lazy import keeps declaration import independent of OpenVINO and ONNX.
    from .openvino_embedding import _model_bundle_assets, _digest_model_bundle_assets

    path = Path(model_path)
    if not path.is_file():
        return {"state": "missing", "digest": None}
    try:
        assets = (
            _model_bundle_assets(path, Path(processor_path) if processor_path else None)
            if path.suffix.lower() == ".onnx"
            else [("model/" + path.name, path)]
        )
        if path.suffix.lower() == ".xml":
            companion = path.with_suffix(".bin")
            if not companion.is_file():
                return {"state": "missing_companion", "digest": None}
            assets.append(("weights/" + companion.name, companion))
        return {"state": "available", "digest": _digest_model_bundle_assets(assets)}
    except Exception as error:
        return {"state": "unreadable", "digest": None, "error_type": type(error).__name__}


@dataclass(frozen=True)
class ModelDeclaration:
    name: str
    revision: str
    assets_json: str
    preprocessing_json: str
    output_revision: str
    runtime: str = "openvino"

    @classmethod
    def create(cls, name, revision, assets, preprocessing, output_revision):
        return cls(
            name,
            revision,
            json.dumps(assets, sort_keys=True),
            json.dumps(preprocessing, sort_keys=True),
            output_revision,
        )

    def record(self):
        value = asdict(self)
        value["assets"] = json.loads(value.pop("assets_json"))
        value["preprocessing"] = json.loads(value.pop("preprocessing_json"))
        return value

    @property
    def key(self):
        return identity({"schema": REVISION, **self.record()})


def serialized(method):
    """Protect lazy setup, request buffers and last-run provenance together."""

    @wraps(method)
    def call(self, *args, **kwargs):
        with self._execution_lock:
            return method(self, *args, **kwargs)

    return call


def execution_record(runtime, declaration=None):
    record = getattr(runtime, "execution_record", None)
    if callable(record):
        return record()
    return {
        "schema": REVISION,
        "status": "success",
        "lifecycle": "model_specific",
        "model": declaration.record() if declaration else None,
        "missing_evidence": ["shared_session", "compiled_cache_readback"],
    }


def fallback_record(error, block):
    # Do not persist exception text that can include private paths or provider diagnostics.
    return {
        "schema": REVISION,
        "status": "unavailable",
        "lifecycle": "model_specific",
        "block": block,
        "reason": type(error).__name__,
        "fallback": {"kind": "application_heuristic"},
        "missing_evidence": ["successful_model_execution"],
    }


class ResultCache:
    """A bounded LRU with copies on both sides; no failure entries."""

    def __init__(self, entries):
        from collections import OrderedDict

        self.entries = max(0, int(entries))
        self.values = OrderedDict()
        self.lock = threading.RLock()

    def clear(self):
        with self.lock:
            self.values.clear()

    def get(self, key):
        with self.lock:
            value = self.values.get(key)
            if value is not None:
                self.values.move_to_end(key)
                return deepcopy(value)
        return None

    def put(self, key, value):
        with self.lock:
            if self.entries:
                self.values[key] = deepcopy(value)
                self.values.move_to_end(key)
                while len(self.values) > self.entries:
                    self.values.popitem(last=False)


def optional_execution(runtime, config, *, assets=None):
    return {
        "schema": REVISION,
        "status": "success",
        "lifecycle": "model_specific",
        "runtime": runtime,
        "runtime_version": runtime_version(runtime),
        "model_revision": config.get("model_revision", config.get("cache_revision", "unknown")),
        "assets": assets or {"state": "unknown", "digest": None},
        "preprocessing_revision": config.get("cache_revision", "package_owned_unknown"),
        "execution_devices": ["unknown"],
        "batch": {"actual": 1, "strategy": "single"},
        "missing_evidence": ["compiled_cache", "stage_timing", "device_readback"],
    }


def bounded_reason(error):
    import re

    message = str(error)
    message = re.sub(r"(?:/[A-Za-z0-9_.~ -]+){2,}", "[path]", message)
    return message[:256]


class AssetSnapshot:
    """Rehash on metadata or membership change, including external data and processors."""

    def __init__(self, model_path, processor_path=None):
        self.model_path = str(model_path)
        self.processor_path = str(processor_path) if processor_path else None
        self.paths = [Path(model_path)]
        self.signature = None
        self.value = None

    def _signature(self):
        paths = list(self.paths)
        processor = Path(self.processor_path) if self.processor_path else None
        if processor:
            paths.extend(sorted(processor.glob("*.json")) if processor.is_dir() else [processor])
        result = []
        for path in paths:
            try:
                stat = path.stat()
                result.append(
                    (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                )
            except OSError:
                result.append((str(path), "missing"))
        return tuple(result)

    def current(self):
        signature = self._signature()
        if signature != self.signature or self.value is None or self.value["state"] != "available":
            # Missing external members may appear without changing the graph file.
            self.value = asset_identity(self.model_path, self.processor_path)
            if self.value["state"] == "available":
                from .openvino_embedding import _model_bundle_assets

                path = Path(self.model_path)
                if path.suffix.lower() == ".onnx":
                    self.paths = [
                        p
                        for _, p in _model_bundle_assets(
                            path, Path(self.processor_path) if self.processor_path else None
                        )
                    ]
                elif path.suffix.lower() == ".xml":
                    self.paths = [path, path.with_suffix(".bin")]
            self.signature = self._signature()
        return deepcopy(self.value)


def preprocessing_spec(kind, config=None):
    config = config or {}
    if kind == "aesthetic":
        return {
            "revision": "nima-preview-v1",
            "color": "RGB",
            "dtype": "float32",
            "layout": "NHWC",
            "shape": [1, 224, 224, 3],
            "resize": [224, 224],
            "resample": 2,
            "divisor": 127.5,
            "offset": -1.0,
            "roi": "whole_preview",
        }
    if kind == "detection":
        size = int(config.get("input_size", 320))
        return {
            "revision": "ssd-preview-v1",
            "color": "RGB",
            "dtype": "uint8",
            "layout": "NHWC",
            "shape": [1, size, size, 3],
            "resize": [size, size],
            "resample": 3,
            "normalization": "none",
            "roi": "whole_preview",
        }
    if kind == "embedding" and config.get("runtime") == "openvino":
        path = Path(config.get("processor_path", ""))
        path = path / "preprocessor_config.json" if path.is_dir() else path
        payload = json.loads(path.read_text()) if path.is_file() else None
        return {
            "revision": "numpy-processor-v1",
            "color": "RGB",
            "dtype": "float32",
            "roi": "whole_preview",
            "processor": payload,
        }
    return {"revision": "package-owned-v1", "runtime": config.get("runtime", "transformers")}


def result_record(content, config, execution, *, extra=None):
    """Identity for direct adapter results; client may replace bypass with hit/miss."""
    return {
        "identity": identity(
            {
                "schema": REVISION,
                "content": hashlib.sha256(content).hexdigest(),
                "model": execution.get("model"),
                "config": config,
                "runtime_version": execution.get("runtime_version", "unknown"),
                "extra": extra,
            }
        ),
        "status": "bypass",
    }
