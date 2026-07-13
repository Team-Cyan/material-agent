from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..adapters.models.openvino_embedding import (
    _digest_model_bundle_assets,
    _model_bundle_assets,
)


_NON_SEMANTIC_EMBEDDING_SETTINGS = {
    "compiled_cache_dir",
    "enabled",
    "enforce_available",
    "result_cache_size",
}


def build_local_embedding_cache_key(config: dict[str, Any]) -> str:
    """Build a content-addressed identity for persisted local embeddings."""

    local = config.get("local", {})
    embedding = local.get("embedding", {}) if isinstance(local, dict) else {}
    if not isinstance(embedding, dict):
        embedding = {}
    settings = {
        key: value
        for key, value in embedding.items()
        if key not in _NON_SEMANTIC_EMBEDDING_SETTINGS
    }
    inference = config.get("inference", {})
    if "cache_dir" not in settings and isinstance(inference, dict):
        settings["cache_dir"] = inference.get("model_cache_dir")
    if "fallback_device" not in settings and isinstance(inference, dict):
        settings["fallback_device"] = inference.get("fallback_device", "CPU")

    runtime = str(embedding.get("runtime", "transformers")).strip().lower()
    payload: dict[str, Any] = {
        "schema_version": "material-agent.embedding-cache.v2",
        "preprocessing_revision": "raw-preview-to-adapter-v2",
        "runtime": runtime,
        "settings": settings,
        "preview": config.get("preview", {}),
    }
    if runtime == "openvino":
        model_value = str(embedding.get("model_path", "")).strip()
        processor_value = str(embedding.get("processor_path", "")).strip()
        model_path = Path(model_value).expanduser() if model_value else None
        processor_path = Path(processor_value).expanduser() if processor_value else None
        if model_path is None or not model_path.is_file():
            payload["bundle_state"] = "model_missing"
        elif processor_path is None or not processor_path.exists():
            payload["bundle_state"] = "processor_missing"
        else:
            assets = _model_bundle_assets(model_path, processor_path)
            payload["bundle_state"] = "available"
            payload["bundle_assets"] = [name for name, _ in assets]
            payload["bundle_digest"] = _digest_model_bundle_assets(assets)

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"embedding-cache-v2:{hashlib.sha256(encoded).hexdigest()}"
