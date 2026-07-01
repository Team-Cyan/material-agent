from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re

import httpx

from .contracts import extract_omlx_structured_dict


_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass(slots=True)
class OMLXCapabilityFailure:
    code: str
    summary: str
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class OMLXCapabilityProfile:
    reachable: bool
    version: str | None
    structured_outputs: bool | None
    xgrammar: bool | None
    served_models: list[str]
    linked_models: list[str]
    expected_models: list[str]
    instance_matches: bool
    effective_model_set_matches: bool = False
    served_models_catalog_superset: bool = False
    settings_drift: list[str] = field(default_factory=list)
    error: str | None = None
    active_structured_probe: bool | None = None
    active_structured_probe_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def probe_omlx_capabilities(
    *,
    base_url: str,
    headers: dict[str, str],
    linked_models: list[str],
    expected_models: list[str],
    timeout: float = 5.0,
    local_version_fallback: str | None = None,
) -> OMLXCapabilityProfile:
    models_payload, error = _fetch_required_json(f"{base_url}/v1/models", headers=headers, timeout=timeout)
    if models_payload is None:
        settings_drift = ["server was unreachable"]
        if _normalized_model_names(expected_models) != _normalized_model_names(linked_models):
            settings_drift.append("linked models do not match configured active models")
        return OMLXCapabilityProfile(
            reachable=False,
            version=None,
            structured_outputs=None,
            xgrammar=None,
            served_models=[],
            linked_models=sorted(linked_models),
            expected_models=sorted(expected_models),
            instance_matches=False,
            effective_model_set_matches=False,
            served_models_catalog_superset=False,
            settings_drift=settings_drift,
            error=error,
        )

    health_payload = _fetch_optional_json(f"{base_url}/health", headers=headers, timeout=timeout)
    admin_settings_payload = _fetch_optional_json(f"{base_url}/admin/settings", headers=headers, timeout=timeout)
    admin_model_settings_payload = _fetch_optional_json(
        f"{base_url}/admin/model_settings",
        headers=headers,
        timeout=timeout,
    )
    version_payload = _fetch_optional_json(f"{base_url}/version", headers=headers, timeout=timeout)
    served_models = _extract_served_models(models_payload)
    version = _extract_version(
        version_payload=version_payload,
        health_payload=health_payload,
        admin_settings_payload=admin_settings_payload,
        admin_model_settings_payload=admin_model_settings_payload,
        models_payload=models_payload,
    )
    if version is None:
        version = _coerce_version(local_version_fallback)
    structured_outputs = _extract_capability_flag(
        version_payload=version_payload,
        health_payload=health_payload,
        admin_settings_payload=admin_settings_payload,
        admin_model_settings_payload=admin_model_settings_payload,
        models_payload=models_payload,
        capability_name="structured_outputs",
    )
    xgrammar = _extract_capability_flag(
        version_payload=version_payload,
        health_payload=health_payload,
        admin_settings_payload=admin_settings_payload,
        admin_model_settings_payload=admin_model_settings_payload,
        models_payload=models_payload,
        capability_name="xgrammar",
    )
    active_structured_probe: bool | None = None
    active_structured_probe_error: str | None = None
    if structured_outputs is None or xgrammar is None:
        probe_model = _active_probe_model(expected_models, linked_models, served_models)
        if probe_model is not None:
            active_structured_probe, active_structured_probe_error = _run_active_structured_probe(
                base_url=base_url,
                headers=headers,
                timeout=timeout,
                model=probe_model,
            )
            if structured_outputs is None:
                structured_outputs = active_structured_probe
            if xgrammar is None:
                xgrammar = active_structured_probe

    normalized_served = set(_normalized_model_names(served_models))
    normalized_linked = set(_normalized_model_names(linked_models))
    normalized_expected = set(_normalized_model_names(expected_models))
    linked_matches_expected = normalized_expected == normalized_linked
    missing_linked = normalized_linked - normalized_served
    extra_served = normalized_served - normalized_linked
    instance_matches = normalized_served == normalized_linked and normalized_linked == normalized_expected
    effective_model_set_matches = linked_matches_expected and not missing_linked
    served_models_catalog_superset = bool(extra_served) and effective_model_set_matches

    settings_drift: list[str] = []
    if not linked_matches_expected:
        settings_drift.append("linked models do not match configured active models")
    if missing_linked:
        settings_drift.append("served models do not include linked models")
    if extra_served:
        settings_drift.append("served models include models outside the linked set")

    return OMLXCapabilityProfile(
        reachable=True,
        version=version,
        structured_outputs=structured_outputs,
        xgrammar=xgrammar,
        served_models=sorted(served_models),
        linked_models=sorted(linked_models),
        expected_models=sorted(expected_models),
        instance_matches=instance_matches,
        effective_model_set_matches=effective_model_set_matches,
        served_models_catalog_superset=served_models_catalog_superset,
        settings_drift=settings_drift,
        error=None,
        active_structured_probe=active_structured_probe,
        active_structured_probe_error=active_structured_probe_error,
    )


def validate_omlx_capability(
    profile: OMLXCapabilityProfile,
    *,
    required_version: str | None = None,
    require_structured_outputs: bool = False,
    require_xgrammar: bool = False,
    require_dedicated_instance: bool = True,
) -> tuple[bool, OMLXCapabilityFailure | None]:
    if not profile.reachable:
        return False, OMLXCapabilityFailure(
            code="omlx_unreachable",
            summary="OMLX API did not respond at the configured base URL.",
            details={"error": profile.error or ""},
        )
    if require_dedicated_instance and (profile.settings_drift or not profile.instance_matches):
        return False, OMLXCapabilityFailure(
            code="instance_mismatch",
            summary="Reachable OMLX server does not match the dedicated instance model set.",
            details={
                "served_models": profile.served_models,
                "linked_models": profile.linked_models,
                "settings_drift": profile.settings_drift,
            },
        )
    if required_version and profile.version is None:
        return False, OMLXCapabilityFailure(
            code="version_unknown",
            summary=f"OMLX did not report a version, so material-agent cannot verify {required_version}.",
            details={"required_version": required_version, "version": profile.version},
        )
    if required_version and profile.version is not None and not _version_satisfies(profile.version, required_version):
        return False, OMLXCapabilityFailure(
            code="version_too_old",
            summary=f"OMLX {profile.version or 'unknown'} does not satisfy {required_version}.",
            details={"required_version": required_version, "version": profile.version},
        )
    if require_structured_outputs and profile.structured_outputs is None:
        return False, OMLXCapabilityFailure(
            code="structured_outputs_unknown",
            summary="Could not confirm whether structured outputs are available.",
            details={"structured_outputs": profile.structured_outputs},
        )
    if require_structured_outputs and profile.structured_outputs is False:
        return False, OMLXCapabilityFailure(
            code="structured_outputs_missing",
            summary="Structured outputs are required but unavailable.",
            details={"structured_outputs": profile.structured_outputs},
        )
    if require_xgrammar and profile.xgrammar is None:
        return False, OMLXCapabilityFailure(
            code="xgrammar_unknown",
            summary="Could not confirm whether xgrammar support is available.",
            details={"xgrammar": profile.xgrammar},
        )
    if require_xgrammar and profile.xgrammar is False:
        return False, OMLXCapabilityFailure(
            code="xgrammar_missing",
            summary="xgrammar support is required but unavailable.",
            details={"xgrammar": profile.xgrammar},
        )
    return True, None


def _fetch_required_json(url: str, *, headers: dict[str, str], timeout: float) -> tuple[dict | list | None, str | None]:
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:  # pragma: no cover - behavior exercised through service tests
        return None, str(exc)


def _fetch_optional_json(url: str, *, headers: dict[str, str], timeout: float) -> dict | list | None:
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def _active_probe_model(expected_models: list[str], linked_models: list[str], served_models: list[str]) -> str | None:
    for candidates in (expected_models, linked_models, served_models):
        for model in candidates:
            if model:
                return model
    return None


def _run_active_structured_probe(
    *,
    base_url: str,
    headers: dict[str, str],
    timeout: float,
    model: str,
) -> tuple[bool | None, str | None]:
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok"]},
        },
        "required": ["status"],
        "additionalProperties": False,
    }
    payload = {
        "model": model,
        "enable_thinking": False,
        "messages": [
            {
                "role": "system",
                "content": "Follow the provided structured output contract exactly.",
            },
            {
                "role": "user",
                "content": "Ignore the user text and return whatever the schema requires.",
            },
        ],
        "temperature": 0.0,
        "max_tokens": 32,
        "structured_outputs": {"json": schema},
    }
    try:
        response = httpx.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        data = extract_omlx_structured_dict(response.json())
        if data == {"status": "ok"}:
            return True, None
        return False, f"Active structured probe returned unexpected payload: {data!r}"
    except httpx.HTTPStatusError as error:  # pragma: no cover - covered with monkeypatched tests
        status_code = error.response.status_code if error.response is not None else None
        if status_code in {400, 404, 405, 409, 410, 415, 422}:
            return False, str(error)
        return None, str(error)
    except httpx.RequestError as error:  # pragma: no cover - covered with monkeypatched tests
        return None, str(error)
    except ValueError as error:  # pragma: no cover - covered with monkeypatched tests
        return False, str(error)
    except Exception as error:  # pragma: no cover - covered with monkeypatched tests
        return False, str(error)


def _extract_served_models(payload: dict | list) -> list[str]:
    if isinstance(payload, dict):
        data = payload.get("data", [])
        if isinstance(data, list):
            models = [item.get("id", "") for item in data if isinstance(item, dict) and item.get("id")]
            if models:
                return models
    return []


def _extract_version(
    *,
    version_payload: dict | list | None,
    health_payload: dict | list | None,
    admin_settings_payload: dict | list | None,
    admin_model_settings_payload: dict | list | None,
    models_payload: dict | list,
) -> str | None:
    candidates = [
        _get_in(version_payload, ("version",)),
        _get_in(version_payload, ("server_version",)),
        _get_in(version_payload, ("omlx_version",)),
        _get_in(version_payload, ("app_version",)),
        _get_in(version_payload, ("server", "version")),
        _get_in(health_payload, ("version",)),
        _get_in(health_payload, ("server_version",)),
        _get_in(health_payload, ("omlx_version",)),
        _get_in(admin_settings_payload, ("server", "version")),
        _get_in(admin_settings_payload, ("runtime", "version")),
        _get_in(admin_settings_payload, ("version",)),
        _get_in(admin_settings_payload, ("server_version",)),
        _get_in(admin_model_settings_payload, ("server", "version")),
        _get_in(admin_model_settings_payload, ("runtime", "version")),
        _get_in(admin_model_settings_payload, ("version",)),
        _get_in(models_payload, ("version",)),
        _get_in(models_payload, ("server_version",)),
    ]
    for candidate in candidates:
        parsed = _coerce_version(candidate)
        if parsed is not None:
            return parsed
    return None


def _extract_capability_flag(
    *,
    version_payload: dict | list | None,
    health_payload: dict | list | None,
    admin_settings_payload: dict | list | None,
    admin_model_settings_payload: dict | list | None,
    models_payload: dict | list,
    capability_name: str,
) -> bool | None:
    aliases = (capability_name, f"supports_{capability_name}")
    candidates = [
        _capability_candidates(version_payload, aliases),
        _capability_candidates(health_payload, aliases),
        _capability_candidates(admin_settings_payload, aliases),
        _capability_candidates(admin_model_settings_payload, aliases),
        _capability_candidates(models_payload, aliases),
    ]
    saw_unknown = False
    for values in candidates:
        for value in values:
            parsed = _coerce_capability_value(value)
            if parsed is not None:
                return parsed
            if value is not None:
                saw_unknown = True
    if saw_unknown:
        return None
    return None


def _capability_candidates(payload: dict | list | None, aliases: tuple[str, ...]) -> list[object]:
    candidates: list[object] = []
    for alias in aliases:
        candidates.extend(
            [
                _get_in(payload, (alias,)),
                _get_in(payload, ("capabilities", alias)),
                _get_in(payload, ("server", alias)),
                _get_in(payload, ("server", "capabilities", alias)),
                _get_in(payload, ("runtime", alias)),
                _get_in(payload, ("runtime", "capabilities", alias)),
                _get_in(payload, ("features", alias)),
                _get_in(payload, ("features", "capabilities", alias)),
            ]
        )
    return candidates


def _get_in(payload: dict | list | None, path: tuple[str, ...]) -> object | None:
    current: object = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _coerce_capability_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "enabled", "available"}:
            return True
        if lowered in {"false", "no", "disabled", "unavailable"}:
            return False
    return None


def _coerce_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _VERSION_PATTERN.search(value)
    if match is None:
        return None
    return ".".join(match.groups())


def _version_satisfies(version: str | None, requirement: str) -> bool:
    if version is None:
        return False
    requirement = requirement.strip()
    if not requirement.startswith(">="):
        return version == requirement
    minimum = _coerce_version(requirement[2:])
    parsed_version = _parse_version(version)
    parsed_minimum = _parse_version(minimum)
    if parsed_version is None or parsed_minimum is None:
        return False
    return parsed_version >= parsed_minimum


def _parse_version(version: str | None) -> tuple[int, int, int] | None:
    if version is None:
        return None
    match = _VERSION_PATTERN.search(version)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _normalized_model_names(models: list[str]) -> list[str]:
    return sorted({Path(model).name for model in models if model})
