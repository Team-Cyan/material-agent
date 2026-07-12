"""Config validation and normalization."""

import copy
import sys

from .constants import AESTHETIC_DIMS


_OMLX_RUNTIME_DEFAULTS = {
    "required_version": ">=0.3.0",
    "require_structured_outputs": False,
    "require_xgrammar": False,
    "probe_on_run": True,
    "enforce_dedicated_instance": False,
}

_OMLX_REQUESTS_DEFAULTS = {
    "fast_vision_schema": "material_agent.fast_screening_signals",
    "vision_schema": "material_agent.full_score",
    "group_commentary_schema": "material_agent.group_commentary",
    "post_commentary_schema": "material_agent.post_commentary",
    "contract_mode": "response_format_json_schema",
    "prompt_preset": "qwen3",
    "model_profile_mode": "auto",
    "enable_thinking": False,
    "temperature": 0.0,
    "xtc_probability": 0.0,
}

_OMLX_ADMIN_DEFAULTS = {
    "base_url": "http://localhost:11435",
    "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
    "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
    "timeout": 120,
    "max_concurrent": 1,
    "model_dir_mode": "config_union",
    "instance_root": "~/.material-agent/omlx",
    "cache_enabled": True,
    "api_key": "",
    "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
    "vision_temperature": 0.0,
    "commentary_temperature": 0.0,
    "vision_retries": 2,
    "fast_vision_max_tokens": 96,
    "vision_max_tokens": 192,
    "commentary_max_tokens": 128,
    "group_commentary_max_tokens": 160,
    "post_commentary_max_tokens": 160,
    "vision_image_max_edge": 1024,
    "vision_jpeg_quality": 92,
}

_OMLX_REQUIRED_KEYS = ("base_url", "full_vision_model", "commentary_model", "timeout")
_OMLX_RUNTIME_BOOLEAN_FIELDS = (
    "require_structured_outputs",
    "require_xgrammar",
    "probe_on_run",
    "enforce_dedicated_instance",
)
_OMLX_REQUEST_BOOLEAN_FIELDS = ("enable_thinking",)
_OMLX_ADMIN_BOOLEAN_FIELDS = ("cache_enabled",)
_OMLX_CONTRACT_MODES = {"structured_outputs", "response_format_json_schema"}
_OMLX_MODEL_PROFILE_MODES = {"off", "auto"}


def _round_weight(value: float) -> float:
    return round(value, 4)


def _coerce_bool_like(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return value


def _is_valid_bool_like(value) -> bool:
    return isinstance(_coerce_bool_like(value), bool)


def _normalize_scene_profile_weights(weights: dict) -> dict[str, float]:
    mapped = {
        "subject_moment": float(weights.get("subject_moment", weights.get("subject", 0.0)) or 0.0),
        "composition": float(weights.get("composition", 0.0) or 0.0),
        "lighting": float(weights.get("lighting", 0.0) or 0.0),
        "color": float(weights.get("color", 0.0) or 0.0),
        "depth_separation": float(
            weights.get("depth_separation", weights.get("depth", 0.0)) or 0.0
        ),
        "mood_story": float(weights.get("mood_story", weights.get("mood", 0.0)) or 0.0),
    }
    weight_sum = sum(mapped.values())
    if weight_sum <= 0:
        return {dim: _round_weight(1.0 / len(AESTHETIC_DIMS)) for dim in AESTHETIC_DIMS}
    return {dim: _round_weight(mapped[dim] / weight_sum) for dim in AESTHETIC_DIMS}


def _build_scene_profiles(cfg: dict) -> dict:
    profiles = copy.deepcopy(cfg.get("scene_profiles", {}))
    if profiles:
        normalized: dict[str, dict] = {}
        for scene, profile in profiles.items():
            if isinstance(profile, dict) and "aesthetic_weights" in profile:
                weights = profile.get("aesthetic_weights", {})
            else:
                weights = profile if isinstance(profile, dict) else {}
            normalized[scene] = {"aesthetic_weights": _normalize_scene_profile_weights(weights)}
        return normalized

    scene_weights = cfg.get("scene_weights", {})
    normalized = {
        scene: {"aesthetic_weights": _normalize_scene_profile_weights(weights)}
        for scene, weights in scene_weights.items()
        if isinstance(weights, dict)
    }
    if "default" not in normalized:
        normalized["default"] = {
            "aesthetic_weights": _normalize_scene_profile_weights(
                {dim: 1.0 for dim in AESTHETIC_DIMS}
            )
        }
    return normalized


def _normalize_omlx_group(omlx: dict) -> dict:
    normalized = copy.deepcopy(omlx)

    runtime = copy.deepcopy(normalized.get("runtime", {}))
    for key, value in _OMLX_RUNTIME_DEFAULTS.items():
        if key not in runtime or runtime[key] is None:
            runtime[key] = copy.deepcopy(value)
    for key in _OMLX_RUNTIME_BOOLEAN_FIELDS:
        runtime[key] = _coerce_bool_like(runtime.get(key))

    requests = copy.deepcopy(normalized.get("requests", {}))
    for key, value in _OMLX_REQUESTS_DEFAULTS.items():
        if key not in requests or requests[key] is None:
            requests[key] = copy.deepcopy(value)
    if requests.get("fast_vision_schema") == "material_agent.fast_score":
        requests["fast_vision_schema"] = _OMLX_REQUESTS_DEFAULTS["fast_vision_schema"]
    requests["contract_mode"] = str(
        requests.get("contract_mode", _OMLX_REQUESTS_DEFAULTS["contract_mode"])
    ).lower()
    requests["prompt_preset"] = (
        str(requests.get("prompt_preset", "default")).strip().lower() or "default"
    )
    requests["model_profile_mode"] = (
        str(
            requests.get("model_profile_mode", _OMLX_REQUESTS_DEFAULTS["model_profile_mode"])
        ).strip().lower()
        or _OMLX_REQUESTS_DEFAULTS["model_profile_mode"]
    )
    for key in _OMLX_REQUEST_BOOLEAN_FIELDS:
        requests[key] = _coerce_bool_like(requests.get(key))

    admin = copy.deepcopy(normalized.get("admin", {}))
    # Precedence is explicit: grouped admin values win, then legacy flat keys,
    # then defaults for compatibility with older configs and current consumers.
    for key, value in _OMLX_ADMIN_DEFAULTS.items():
        if admin.get(key) is not None:
            continue
        if key in normalized and normalized[key] is not None:
            admin[key] = copy.deepcopy(normalized[key])
        else:
            admin[key] = copy.deepcopy(value)
    for key in _OMLX_ADMIN_BOOLEAN_FIELDS:
        admin[key] = _coerce_bool_like(admin.get(key))

    if admin.get("fast_vision_model") is None:
        admin["fast_vision_model"] = admin["full_vision_model"]

    normalized["runtime"] = runtime
    normalized["requests"] = requests
    normalized["admin"] = admin

    for key, value in admin.items():
        normalized[key] = copy.deepcopy(value)

    return normalized


def _raw_omlx_value(raw_omlx: dict, key: str):
    admin = raw_omlx.get("admin", {})
    if isinstance(admin, dict) and admin.get(key) is not None:
        return admin[key]
    if raw_omlx.get(key) is not None:
        return raw_omlx[key]
    return None


def sync_omlx_model_selection(
    config: dict,
    *,
    full_vision_model: str,
    commentary_model: str | None = None,
    fast_vision_model: str | None = None,
) -> dict:
    commentary = commentary_model or full_vision_model
    fast = fast_vision_model or full_vision_model

    omlx = config.setdefault("omlx", {})
    admin = omlx.setdefault("admin", {})
    values = {
        "fast_vision_model": fast,
        "full_vision_model": full_vision_model,
        "commentary_model": commentary,
    }
    for key, value in values.items():
        omlx[key] = value
        admin[key] = value
        config[key] = value
    return config


def normalize_config(cfg: dict) -> dict:
    normalized = copy.deepcopy(cfg)
    backend = normalized.get("backend") or normalized.get("vision_backend") or "local"
    normalized["backend"] = backend
    normalized.pop("vision_backend", None)
    normalized["log_level"] = (normalized.get("log_level") or "info").lower()
    normalized["output_language"] = (normalized.get("output_language") or "zh").lower()

    commentary_enabled = normalized.get("commentary_enabled")
    if commentary_enabled is None:
        legacy_values = [
            normalized.get("local", {}).get("commentary_enabled"),
            normalized.get("ollama", {}).get("commentary_enabled"),
            normalized.get("omlx", {}).get("commentary_enabled"),
        ]
        explicit_values = [value for value in legacy_values if value is not None]
        commentary_enabled = bool(explicit_values[-1]) if explicit_values else backend != "local"
    normalized["commentary_enabled"] = commentary_enabled
    legacy = normalized.setdefault("legacy", {})
    legacy["enabled"] = _coerce_bool_like(legacy.get("enabled", False))

    local = normalized.setdefault("local", {})
    local.setdefault("max_concurrent", 1)
    semantic = local.setdefault("semantic", {})
    semantic["enabled"] = _coerce_bool_like(semantic.get("enabled", False))
    semantic["enforce_available"] = _coerce_bool_like(
        semantic.get("enforce_available", False)
    )
    semantic.setdefault("model_name", "MobileCLIP2-S0")
    semantic.setdefault("pretrained", "dfndr2b")
    semantic.setdefault("device", "cpu")
    semantic.setdefault("min_confidence", 0.30)
    quality = local.setdefault("quality", {})
    quality["enabled"] = _coerce_bool_like(quality.get("enabled", False))
    quality["enforce_available"] = _coerce_bool_like(
        quality.get("enforce_available", False)
    )
    quality.setdefault("device", "cpu")
    quality.setdefault("policy_version", "quality-priors-v1")
    quality.setdefault(
        "metrics",
        {
            "brisque": {
                "enabled": True,
                "role": "reject_prior",
                "lower_better": True,
                "raw_min": 0.0,
                "raw_max": 100.0,
                "weight": 0.5,
            },
            "niqe": {
                "enabled": True,
                "role": "reject_prior",
                "lower_better": True,
                "raw_min": 0.0,
                "raw_max": 10.0,
                "weight": 0.5,
            },
            "musiq": {
                "enabled": False,
                "role": "quality",
                "lower_better": False,
                "raw_min": 0.0,
                "raw_max": 100.0,
                "weight": 1.0,
            },
            "nima": {
                "enabled": False,
                "role": "aesthetic",
                "lower_better": False,
                "raw_min": 0.0,
                "raw_max": 10.0,
                "weight": 0.5,
            },
            "clipiqa+": {
                "enabled": False,
                "role": "aesthetic",
                "lower_better": False,
                "raw_min": 0.0,
                "raw_max": 1.0,
                "weight": 0.5,
            },
        },
    )
    embedding = local.setdefault("embedding", {})
    embedding["enabled"] = _coerce_bool_like(embedding.get("enabled", False))
    embedding["enforce_available"] = _coerce_bool_like(
        embedding.get("enforce_available", False)
    )
    embedding.setdefault("runtime", "transformers")
    embedding.setdefault("model_name", "facebook/dinov2-small")
    embedding.setdefault("device", "cpu")
    embedding.setdefault("model_path", "")
    embedding.setdefault("processor_path", "")
    embedding.setdefault("compiled_cache_dir", "~/.material-agent/openvino-cache")
    face = local.setdefault("face", {})
    face["enabled"] = _coerce_bool_like(face.get("enabled", False))
    face["enforce_available"] = _coerce_bool_like(face.get("enforce_available", False))
    face.setdefault("model_asset_path", "~/.material-agent/models/face_landmarker.task")
    face.setdefault("num_faces", 5)
    face.setdefault("min_detection_confidence", 0.5)

    inference = normalized.setdefault("inference", {})
    inference.setdefault("runtime", "openvino")
    inference.setdefault("device", "AUTO:GPU,CPU")
    inference.setdefault("fallback_device", "CPU")
    inference.setdefault("model_cache_dir", "~/.material-agent/models")
    inference.setdefault("provider_tags", ["intel-openvino", "cpu"])
    inference["enforce_available"] = _coerce_bool_like(inference.get("enforce_available", False))

    preview = normalized.setdefault("preview", {})
    preview.setdefault("prefer_embedded", True)
    preview.setdefault("fallback_decode", "half_size")
    preview["prefer_embedded"] = _coerce_bool_like(preview.get("prefer_embedded", True))

    grouping = normalized.setdefault("grouping", {})
    embedding_similarity = grouping.setdefault("embedding_similarity", {})
    embedding_similarity["enabled"] = _coerce_bool_like(
        embedding_similarity.get("enabled", False)
    )
    embedding_similarity.setdefault("threshold", 0.85)

    screening = normalized.setdefault("screening", {})
    screening["backend"] = (screening.get("backend") or "musiq").lower()
    if screening["backend"] == "musiq":
        musiq = screening.setdefault("musiq", {})
        musiq.setdefault("metric", "musiq")
        musiq.setdefault("device", "cpu")
        musiq.setdefault("score_divisor", 10.0)
        musiq.setdefault("python_bin", "~/.material-agent/musiq-venv/bin/python")

    if "omlx" in normalized:
        omlx = normalized.setdefault("omlx", {})
        omlx.setdefault("fast_vision_model", omlx.get("full_vision_model"))
        omlx.setdefault("instance_root", "~/.material-agent/omlx")
        omlx.setdefault("model_dir_mode", "config_union")
        omlx.setdefault("cache_enabled", True)

    if "ollama" in normalized:
        normalized["ollama"].setdefault(
            "fast_vision_model",
            normalized["ollama"].get("vision_model"),
        )

    normalized["focus_integrity"] = copy.deepcopy(normalized.get("focus_integrity", {}))
    normalized["focus_integrity"].setdefault("enabled", True)
    normalized["focus_integrity"].setdefault("mode", "preview_proxy")
    normalized["focus_integrity"].setdefault("high_resolution_roi", False)
    normalized["focus_integrity"].setdefault("downscale_warning_ratio", 3.0)

    normalized["portrait_face_eye"] = copy.deepcopy(normalized.get("portrait_face_eye", {}))
    normalized["portrait_face_eye"].setdefault("enabled", False)
    normalized["portrait_face_eye"].setdefault("min_face_ratio", 0.08)
    normalized["portrait_face_eye"].setdefault("review_penalty", 0.8)

    normalized["decision_policy"] = copy.deepcopy(normalized.get("decision_policy", {}))
    normalized["decision_policy"].setdefault("keep_threshold", 7.5)
    normalized["decision_policy"].setdefault("review_threshold", 5.5)
    hard_reject = normalized["decision_policy"].setdefault("hard_reject", {})
    hard_reject.setdefault("technical_quality_below", 1.5)
    hard_reject.setdefault("subject_focus_below", 1.5)

    normalized["screening_policy"] = copy.deepcopy(normalized.get("screening_policy", {}))
    normalized["screening_policy"].setdefault("weight", 0.10)
    normalized["screening_policy"].setdefault("top1_review_fallback", True)

    normalized["review_pipeline"] = copy.deepcopy(normalized.get("review_pipeline", {}))
    normalized["review_pipeline"].setdefault("score_prefetch_window", 2)

    normalized["xmp"] = copy.deepcopy(normalized.get("xmp", {}))
    normalized["xmp"].setdefault("write_mode", "sidecar")
    normalized["xmp"].setdefault("compatibility_profile", "adobe")
    normalized["xmp"].setdefault("machine_tag_target", "identifier")

    if "omlx" in normalized:
        normalized["omlx"] = _normalize_omlx_group(normalized.get("omlx", {}))
    normalized["scene_profiles"] = _build_scene_profiles(normalized)
    return normalized


def validate_config(cfg: dict) -> None:
    raw_scene_profiles = copy.deepcopy(cfg.get("scene_profiles", {}))
    raw_omlx = copy.deepcopy(cfg.get("omlx", {}))
    cfg = normalize_config(cfg)
    errors = []

    for key in ("scorers", "grouping", "preview", "scoring"):
        if key not in cfg:
            errors.append(f"Missing required config key: '{key}'")

    backend = cfg.get("backend", "local")
    if backend not in {"local", "ollama", "omlx"}:
        errors.append(f"backend must be one of ['local', 'ollama', 'omlx'], got: {backend!r}")
    if backend in {"ollama", "omlx"} and not cfg.get("legacy", {}).get("enabled", False):
        errors.append(
            f"backend {backend!r} is quarantined; set legacy.enabled: true for explicit compatibility use"
        )
    if cfg.get("log_level") not in {"info", "debug"}:
        errors.append(f"log_level must be 'info' or 'debug', got: {cfg.get('log_level')!r}")
    if cfg.get("output_language") not in {"zh", "en"}:
        errors.append(f"output_language must be 'zh' or 'en', got: {cfg.get('output_language')!r}")
    preview = cfg.get("preview", {})
    if "prefer_embedded" in preview and not _is_valid_bool_like(preview.get("prefer_embedded")):
        errors.append(
            "preview.prefer_embedded must be a boolean, "
            f"got: {preview.get('prefer_embedded')!r}"
        )
    if preview.get("fallback_decode", "half_size") not in {"half_size"}:
        errors.append(
            "preview.fallback_decode must be 'half_size', "
            f"got: {preview.get('fallback_decode')!r}"
        )
    review_pipeline = cfg.get("review_pipeline", {})
    score_prefetch_window = review_pipeline.get("score_prefetch_window", 2)
    if not isinstance(score_prefetch_window, int) or score_prefetch_window < 1:
        errors.append(
            "review_pipeline.score_prefetch_window must be an integer >= 1, "
            f"got: {score_prefetch_window!r}"
        )
    grouping = cfg.get("grouping", {})
    embedding_similarity = grouping.get("embedding_similarity", {})
    if not _is_valid_bool_like(embedding_similarity.get("enabled", False)):
        errors.append(
            "grouping.embedding_similarity.enabled must be a boolean, "
            f"got: {embedding_similarity.get('enabled')!r}"
        )
    embedding_threshold = embedding_similarity.get("threshold", 0.85)
    if not isinstance(embedding_threshold, int | float) or not -1.0 <= float(
        embedding_threshold
    ) <= 1.0:
        errors.append(
            "grouping.embedding_similarity.threshold must be between -1 and 1, "
            f"got: {embedding_threshold!r}"
        )
    if embedding_similarity.get("enabled", False) and not cfg.get("local", {}).get(
        "embedding", {}
    ).get("enabled", False):
        errors.append(
            "grouping.embedding_similarity requires local.embedding.enabled: true"
        )
    xmp = cfg.get("xmp", {})
    if xmp.get("write_mode", "sidecar") != "sidecar":
        errors.append(
            "xmp.write_mode must be 'sidecar'; direct RAW metadata writes are not supported, "
            f"got: {xmp.get('write_mode')!r}"
        )
    if xmp.get("machine_tag_target", "identifier") not in {"identifier"}:
        errors.append(
            "xmp.machine_tag_target must be 'identifier', "
            f"got: {xmp.get('machine_tag_target')!r}"
        )

    if backend == "local":
        if cfg.get("commentary_enabled", False):
            errors.append(
                "commentary_enabled is not supported with backend 'local'; "
                "keep commentary_enabled false or choose an explicit legacy backend"
            )
        local = cfg.get("local", {})
        max_concurrent = local.get("max_concurrent", 1)
        if not isinstance(max_concurrent, int) or max_concurrent < 1:
            errors.append(f"local.max_concurrent must be an integer >= 1, got: {max_concurrent!r}")
        semantic = local.get("semantic", {})
        for key in ("enabled", "enforce_available"):
            if not _is_valid_bool_like(semantic.get(key, False)):
                errors.append(f"local.semantic.{key} must be a boolean, got: {semantic.get(key)!r}")
        for key in ("model_name", "pretrained", "device"):
            value = semantic.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"local.semantic.{key} must be a non-empty string, got: {value!r}")
        min_confidence = semantic.get("min_confidence", 0.30)
        if not isinstance(min_confidence, int | float) or not 0.0 <= float(min_confidence) <= 1.0:
            errors.append(
                "local.semantic.min_confidence must be a number between 0 and 1, "
                f"got: {min_confidence!r}"
            )
        quality = local.get("quality", {})
        for key in ("enabled", "enforce_available"):
            if not _is_valid_bool_like(quality.get(key, False)):
                errors.append(f"local.quality.{key} must be a boolean, got: {quality.get(key)!r}")
        for key in ("device", "policy_version"):
            value = quality.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"local.quality.{key} must be a non-empty string, got: {value!r}")
        metrics = quality.get("metrics", {})
        if not isinstance(metrics, dict) or not metrics:
            errors.append("local.quality.metrics must be a non-empty mapping")
        else:
            for name, spec in metrics.items():
                if not isinstance(spec, dict):
                    errors.append(f"local.quality.metrics.{name} must be a mapping")
                    continue
                raw_min = spec.get("raw_min")
                raw_max = spec.get("raw_max")
                if not isinstance(raw_min, int | float) or not isinstance(raw_max, int | float):
                    errors.append(
                        f"local.quality.metrics.{name}.raw_min/raw_max must be numeric"
                    )
                elif float(raw_max) <= float(raw_min):
                    errors.append(
                        f"local.quality.metrics.{name}.raw_max must exceed raw_min"
                    )
                if not isinstance(spec.get("lower_better"), bool):
                    errors.append(
                        f"local.quality.metrics.{name}.lower_better must be a boolean"
                    )
                if spec.get("role", "quality") not in {
                    "reject_prior",
                    "quality",
                    "aesthetic",
                }:
                    errors.append(
                        f"local.quality.metrics.{name}.role must be reject_prior, quality, or aesthetic"
                    )
        embedding = local.get("embedding", {})
        for key in ("enabled", "enforce_available"):
            if not _is_valid_bool_like(embedding.get(key, False)):
                errors.append(
                    f"local.embedding.{key} must be a boolean, got: {embedding.get(key)!r}"
                )
        if embedding.get("runtime", "transformers") not in {"transformers", "openvino"}:
            errors.append(
                "local.embedding.runtime must be 'transformers' or 'openvino', "
                f"got: {embedding.get('runtime')!r}"
            )
        for key in ("model_name", "device"):
            value = embedding.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"local.embedding.{key} must be a non-empty string, got: {value!r}"
                )
        if embedding.get("enabled", False) and embedding.get("runtime") == "openvino":
            for key in ("model_path", "processor_path", "compiled_cache_dir"):
                value = embedding.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"local.embedding.{key} must be set for OpenVINO embedding"
                    )
        face = local.get("face", {})
        for key in ("enabled", "enforce_available"):
            if not _is_valid_bool_like(face.get(key, False)):
                errors.append(f"local.face.{key} must be a boolean, got: {face.get(key)!r}")
        model_asset_path = face.get("model_asset_path")
        if not isinstance(model_asset_path, str) or not model_asset_path.strip():
            errors.append(
                "local.face.model_asset_path must be a non-empty string, "
                f"got: {model_asset_path!r}"
            )
        num_faces = face.get("num_faces", 5)
        if not isinstance(num_faces, int) or num_faces < 1:
            errors.append(f"local.face.num_faces must be an integer >= 1, got: {num_faces!r}")
        confidence = face.get("min_detection_confidence", 0.5)
        if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
            errors.append(
                "local.face.min_detection_confidence must be between 0 and 1, "
                f"got: {confidence!r}"
            )
        inference = cfg.get("inference", {})
        runtime = inference.get("runtime", "openvino")
        if runtime not in {"openvino", "onnxruntime", "cpu"}:
            errors.append(
                "inference.runtime must be one of ['openvino', 'onnxruntime', 'cpu'], "
                f"got: {runtime!r}"
            )
        device = inference.get("device", "AUTO:GPU,CPU")
        if not isinstance(device, str) or not device.strip():
            errors.append(f"inference.device must be a non-empty string, got: {device!r}")
        if not _is_valid_bool_like(inference.get("enforce_available", False)):
            errors.append(
                "inference.enforce_available must be a boolean, "
                f"got: {inference.get('enforce_available')!r}"
            )
    elif backend == "ollama":
        ollama = cfg.get("ollama", {})
        if "ollama" not in cfg:
            errors.append("Missing required config key: 'ollama'")
        for key in ("base_url", "vision_model", "commentary_model", "timeout"):
            if key not in ollama:
                errors.append(f"Missing required ollama config key: '{key}'")
        max_concurrent = ollama.get("max_concurrent", 3)
        if not isinstance(max_concurrent, int) or max_concurrent < 1:
            errors.append(f"ollama.max_concurrent must be an integer >= 1, got: {max_concurrent!r}")
    elif backend == "omlx":
        if not isinstance(raw_omlx, dict) or not raw_omlx:
            errors.append("Missing required config key: 'omlx'")
        for key in _OMLX_REQUIRED_KEYS:
            if _raw_omlx_value(raw_omlx, key) is None:
                errors.append(f"Missing required omlx config key: '{key}'")
        max_concurrent = _raw_omlx_value(raw_omlx, "max_concurrent")
        if max_concurrent is not None and (
            not isinstance(max_concurrent, int) or max_concurrent < 1
        ):
            errors.append(f"omlx.max_concurrent must be an integer >= 1, got: {max_concurrent!r}")
        model_dir_mode = _raw_omlx_value(raw_omlx, "model_dir_mode")
        if model_dir_mode is not None and model_dir_mode not in {"config_union"}:
            errors.append(f"omlx.model_dir_mode must be 'config_union', got: {model_dir_mode!r}")
        raw_requests = (
            raw_omlx.get("requests", {}) if isinstance(raw_omlx.get("requests"), dict) else {}
        )
        raw_runtime = (
            raw_omlx.get("runtime", {}) if isinstance(raw_omlx.get("runtime"), dict) else {}
        )
        contract_mode = raw_requests.get("contract_mode")
        if contract_mode is not None and str(contract_mode).lower() not in _OMLX_CONTRACT_MODES:
            errors.append(
                "omlx.requests.contract_mode must be one of "
                f"{sorted(_OMLX_CONTRACT_MODES)}, got: {contract_mode!r}"
            )
        model_profile_mode = raw_requests.get("model_profile_mode")
        if (
            model_profile_mode is not None
            and str(model_profile_mode).lower() not in _OMLX_MODEL_PROFILE_MODES
        ):
            errors.append(
                "omlx.requests.model_profile_mode must be one of "
                f"{sorted(_OMLX_MODEL_PROFILE_MODES)}, got: {model_profile_mode!r}"
            )
        for field in _OMLX_RUNTIME_BOOLEAN_FIELDS:
            value = raw_runtime.get(field)
            if value is not None and not _is_valid_bool_like(value):
                errors.append(f"omlx.runtime.{field} must be a boolean, got: {value!r}")
        for field in _OMLX_REQUEST_BOOLEAN_FIELDS:
            value = raw_requests.get(field)
            if value is not None and not _is_valid_bool_like(value):
                errors.append(f"omlx.requests.{field} must be a boolean, got: {value!r}")
        model_profiles = raw_omlx.get("model_profiles")
        if model_profiles is not None and not isinstance(model_profiles, dict):
            errors.append("omlx.model_profiles must be an object mapping model ids to profile configs")
        elif isinstance(model_profiles, dict):
            for model_name, profile in model_profiles.items():
                if not isinstance(profile, dict):
                    errors.append(
                        f"omlx.model_profiles.{model_name} must be an object, got: {profile!r}"
                    )
                    continue
                request_overrides = profile.get("request_overrides")
                if request_overrides is not None and not isinstance(request_overrides, dict):
                    errors.append(
                        f"omlx.model_profiles.{model_name}.request_overrides must be an object"
                    )
                prompt_overrides = profile.get("prompt_overrides")
                if prompt_overrides is not None and not isinstance(prompt_overrides, dict):
                    errors.append(
                        f"omlx.model_profiles.{model_name}.prompt_overrides must be an object"
                    )
        cache_enabled = _raw_omlx_value(raw_omlx, "cache_enabled")
        if cache_enabled is not None and not _is_valid_bool_like(cache_enabled):
            errors.append(f"omlx.cache_enabled must be a boolean, got: {cache_enabled!r}")
        image_max_edge = _raw_omlx_value(raw_omlx, "vision_image_max_edge")
        if image_max_edge is not None and (
            not isinstance(image_max_edge, int) or image_max_edge < 1
        ):
            errors.append(
                "omlx.vision_image_max_edge must be an integer >= 1, "
                f"got: {image_max_edge!r}"
            )
        jpeg_quality = _raw_omlx_value(raw_omlx, "vision_jpeg_quality")
        if jpeg_quality is not None and (
            not isinstance(jpeg_quality, int) or not 1 <= jpeg_quality <= 100
        ):
            errors.append(
                "omlx.vision_jpeg_quality must be an integer between 1 and 100, "
                f"got: {jpeg_quality!r}"
            )

    screening = cfg.get("screening", {})
    if screening:
        screening_backend = screening.get("backend", "musiq")
        if screening_backend not in {"musiq"}:
            errors.append(f"screening.backend must be 'musiq', got: {screening_backend!r}")
        if screening_backend == "musiq":
            musiq = screening.get("musiq", {})
            score_divisor = musiq.get("score_divisor", 10.0)
            if not isinstance(score_divisor, (int, float)) or score_divisor <= 0:
                errors.append(f"screening.musiq.score_divisor must be > 0, got: {score_divisor!r}")

    scene_profiles = cfg.get("scene_profiles", {})
    for scene, profile in raw_scene_profiles.items():
        weights = profile.get("aesthetic_weights", {}) if isinstance(profile, dict) else {}
        if not isinstance(weights, dict):
            continue
        unknown = set(weights) - set(AESTHETIC_DIMS)
        if unknown:
            errors.append(
                f"scene_profiles['{scene}'].aesthetic_weights has unknown dimensions: {sorted(unknown)}"
            )
    for scene, profile in scene_profiles.items():
        weights = profile.get("aesthetic_weights", {}) if isinstance(profile, dict) else {}
        if not isinstance(weights, dict):
            continue
        total = sum(weights.get(d, 0.0) for d in AESTHETIC_DIMS)
        if abs(total - 1.0) > 0.01:
            errors.append(
                f"scene_profiles['{scene}'].aesthetic_weights sums to {total:.4f}, expected 1.0"
            )
        unknown = set(weights) - set(AESTHETIC_DIMS)
        if unknown:
            errors.append(
                f"scene_profiles['{scene}'].aesthetic_weights has unknown dimensions: {sorted(unknown)}"
            )

    default_profile = scene_profiles.get("default", {})
    default_weights = (
        default_profile.get("aesthetic_weights", {}) if isinstance(default_profile, dict) else {}
    )
    missing_dims = [d for d in AESTHETIC_DIMS if d not in default_weights]
    if default_weights and missing_dims:
        errors.append(
            f"scene_profiles['default'].aesthetic_weights is missing dimensions: {missing_dims}"
        )

    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  • {error}")
        sys.exit(1)
