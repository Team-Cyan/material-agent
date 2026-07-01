from __future__ import annotations

from .profile_resolver import prompt_override, request_override, resolve_prompt_profile
from .task_specs import PROMPT_TASK_SPECS
from .types import PromptBundle

_TEMPERATURE_DEFAULTS = {
    "vision_temperature": 0.0,
    "commentary_temperature": 0.0,
}

_MAX_TOKEN_DEFAULTS = {
    "vision_max_tokens": 192,
    "fast_vision_max_tokens": 96,
    "group_commentary_max_tokens": 128,
    "post_commentary_max_tokens": 128,
}

_COMMENTARY_MAX_TOKEN_KEYS = {
    "group_commentary_max_tokens",
    "post_commentary_max_tokens",
}


class PromptRegistry:
    def __init__(self, config: dict):
        self.config = config
        requests = config.get("requests", {})
        self.requests = requests if isinstance(requests, dict) else {}
        self.output_language = config.get("output_language", "zh")
        self.contract_mode = str(self.requests.get("contract_mode", "structured_outputs")).lower()
        self.profile_mode = str(self.requests.get("model_profile_mode", "auto")).lower()

    def _resolve_task_model(self, spec) -> str:
        expected_model = self.config.get(spec.model_config_key)
        if isinstance(expected_model, str):
            expected_model = expected_model.strip()
        else:
            expected_model = ""
        if expected_model:
            return expected_model
        return ""

    def _max_token_default(self, key: str) -> int:
        if key in self.config:
            return int(self.config[key])
        if key in _COMMENTARY_MAX_TOKEN_KEYS and "commentary_max_tokens" in self.config:
            return int(self.config["commentary_max_tokens"])
        return _MAX_TOKEN_DEFAULTS.get(key, 0)

    def resolve(self, task: str, *, model: str, **prompt_inputs) -> PromptBundle:
        if task not in PROMPT_TASK_SPECS:
            raise KeyError(f"Unknown prompt task: {task}")

        spec = PROMPT_TASK_SPECS[task]
        expected_model = self._resolve_task_model(spec)
        if expected_model and model != expected_model:
            raise ValueError(
                f"Prompt task '{task}' expects model '{expected_model}', got '{model}'"
            )

        resolved_model = expected_model or model
        profile = resolve_prompt_profile(self.config, resolved_model, self.profile_mode)
        prompt_preset = str(
            request_override(profile, "prompt_preset", self.requests.get("prompt_preset", "default"))
        ).lower()
        schema_name = str(
            self.requests.get(spec.schema_request_key, spec.default_schema_name)
        )
        temperature = float(
            request_override(
                profile,
                spec.temperature_key,
                self.config.get(
                    spec.temperature_key,
                    _TEMPERATURE_DEFAULTS.get(spec.temperature_key, 0.0),
                ),
            )
        )
        max_tokens = int(
            request_override(
                profile,
                spec.max_tokens_key,
                self._max_token_default(spec.max_tokens_key),
            )
        )
        prompt = spec.prompt_factory(
            output_language=self.output_language,
            prompt_preset=prompt_preset,
            extra_instructions=prompt_override(profile, spec.prompt_extra_key),
            structured_output=True,
            **prompt_inputs,
        )
        response_format = spec.response_format_factory(
            schema_name,
            contract_mode=self.contract_mode,
        )
        return PromptBundle(
            task=spec.name,
            model=resolved_model,
            prompt=prompt,
            response_format=response_format,
            request_options={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "enable_thinking": False,
            },
            evaluation_policy=spec.evaluation_policy,
        )
