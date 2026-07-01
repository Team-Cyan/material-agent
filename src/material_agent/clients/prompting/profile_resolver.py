from __future__ import annotations

from pathlib import Path
from typing import Any

from .types import PromptProfile


def resolve_prompt_profile(config: dict, model: str, profile_mode: str) -> PromptProfile:
    if str(profile_mode).lower() != "auto":
        return PromptProfile()

    raw_profiles = config.get("model_profiles", {})
    if not isinstance(raw_profiles, dict):
        return PromptProfile()

    for candidate in (model, Path(model).name):
        profile = raw_profiles.get(candidate)
        if not isinstance(profile, dict):
            continue
        request_overrides = profile.get("request_overrides", {})
        prompt_overrides = profile.get("prompt_overrides", {})
        return PromptProfile(
            request_overrides=request_overrides if isinstance(request_overrides, dict) else {},
            prompt_overrides=prompt_overrides if isinstance(prompt_overrides, dict) else {},
        )
    return PromptProfile()


def request_override(profile: PromptProfile, key: str, default: Any) -> Any:
    value = profile.request_overrides.get(key)
    return default if value is None else value


def prompt_override(profile: PromptProfile, key: str | None) -> str | None:
    if not key:
        return None
    value = profile.prompt_overrides.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
