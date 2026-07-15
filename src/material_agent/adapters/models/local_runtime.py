from __future__ import annotations

from importlib import util
from pathlib import Path
from typing import Any


def probe_local_runtime(config: dict[str, Any]) -> dict[str, Any]:
    """Report local runtime package/device state without changing score policy."""

    inference = config.get("inference", {}) if isinstance(config.get("inference"), dict) else {}
    local = config.get("local", {}) if isinstance(config.get("local"), dict) else {}
    aesthetic = local.get("aesthetic", {}) if isinstance(local.get("aesthetic"), dict) else {}
    runtime = str(inference.get("runtime", "cpu")).lower()
    device = str(inference.get("device", "CPU"))
    fallback_device = str(inference.get("fallback_device", "CPU"))
    provider_tags = _as_list(inference.get("provider_tags", []))
    model_cache_dir = str(
        Path(str(inference.get("model_cache_dir", "~/.material-agent/models"))).expanduser()
    )
    enforce_available = _as_bool(inference.get("enforce_available", False))

    payload: dict[str, Any] = {
        "backend": "local",
        "runtime": runtime,
        "device": device,
        "fallback_device": fallback_device,
        "provider_tags": provider_tags,
        "model_cache_dir": model_cache_dir,
        "model_cache_dir_exists": Path(model_cache_dir).exists(),
        "enforce_available": enforce_available,
        "heuristic_scoring_active": True,
        "learned_aesthetic_active": _as_bool(aesthetic.get("enabled", False)),
        "aesthetic_model_name": aesthetic.get("model_name"),
        "capability_valid": True,
        "capability_failure": None,
        "available_devices": [],
        "available_providers": [],
        "accelerator_available": False,
    }

    if runtime == "cpu":
        payload["available_devices"] = ["CPU"]
        return payload
    if runtime == "onnxruntime":
        return _probe_onnxruntime(payload)
    if runtime == "openvino":
        return _probe_openvino(payload)

    return _with_failure(
        payload,
        code="unsupported_runtime",
        summary=f"Unsupported local inference runtime: {runtime!r}",
    )


def _probe_onnxruntime(payload: dict[str, Any]) -> dict[str, Any]:
    if util.find_spec("onnxruntime") is None:
        return _with_failure(
            payload,
            code="package_missing",
            summary="onnxruntime is not installed in the current environment.",
        )
    try:
        import onnxruntime as ort

        providers = list(ort.get_available_providers())
    except Exception as error:  # pragma: no cover - defensive package-import boundary
        return _with_failure(payload, code="probe_error", summary=str(error))

    payload["available_providers"] = providers
    payload["accelerator_available"] = any(
        provider != "CPUExecutionProvider" for provider in providers
    )
    if "CPUExecutionProvider" not in providers:
        return _with_failure(
            payload,
            code="cpu_provider_missing",
            summary="onnxruntime is installed but CPUExecutionProvider is unavailable.",
        )
    return payload


def _probe_openvino(payload: dict[str, Any]) -> dict[str, Any]:
    if util.find_spec("openvino") is None:
        return _with_failure(
            payload,
            code="package_missing",
            summary="openvino is not installed in the current environment.",
        )
    try:
        import openvino as ov

        core = ov.Core()
        devices = list(core.available_devices)
        version = getattr(ov, "__version__", "")
    except Exception as error:  # pragma: no cover - defensive package-import boundary
        return _with_failure(payload, code="probe_error", summary=str(error))

    payload["openvino_version"] = version
    payload["available_devices"] = devices
    payload["accelerator_available"] = any(device != "CPU" for device in devices)
    if not devices:
        return _with_failure(
            payload,
            code="device_missing",
            summary="openvino is installed but did not report any available devices.",
        )
    requested_device = str(payload.get("device", "CPU"))
    if not _openvino_request_is_available(requested_device, devices):
        return _with_failure(
            payload,
            code="requested_device_missing",
            summary=(
                f"OpenVINO device {requested_device!r} is unavailable; "
                f"visible devices: {devices!r}."
            ),
        )
    fallback_device = str(payload.get("fallback_device", "")).strip()
    if fallback_device and not _openvino_device_is_available(fallback_device, devices):
        return _with_failure(
            payload,
            code="fallback_device_missing",
            summary=(
                f"OpenVINO fallback device {fallback_device!r} is unavailable; "
                f"visible devices: {devices!r}."
            ),
        )
    return payload


def _openvino_request_is_available(requested: str, available: list[str]) -> bool:
    request = requested.strip().upper()
    if not request:
        return False
    if ":" not in request:
        if request in {"AUTO", "MULTI", "HETERO"}:
            return bool(available)
        return _openvino_device_is_available(request, available)

    plugin, raw_candidates = request.split(":", 1)
    candidates = [candidate.strip() for candidate in raw_candidates.split(",") if candidate.strip()]
    if plugin == "AUTO":
        return bool(candidates) and any(
            _openvino_device_is_available(candidate, available) for candidate in candidates
        )
    if plugin in {"MULTI", "HETERO"}:
        return bool(candidates) and all(
            _openvino_device_is_available(candidate, available) for candidate in candidates
        )
    return _openvino_device_is_available(request, available)


def _openvino_device_is_available(requested: str, available: list[str]) -> bool:
    request = requested.strip().upper()
    visible = [str(device).strip().upper() for device in available]
    if "." in request:
        return request in visible
    return any(device == request or device.startswith(f"{request}.") for device in visible)


def _with_failure(payload: dict[str, Any], *, code: str, summary: str) -> dict[str, Any]:
    payload["capability_valid"] = False
    payload["capability_failure"] = {"code": code, "summary": summary}
    return payload


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]
