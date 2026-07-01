import logging

import httpx
import requests

from ..adapters.models.ollama.contracts import (
    build_vision_prompt,
    parse_vision_response as parse_contract_vision_response,
)
from ..adapters.models.ollama.transport import (
    generate_text_async,
    generate_text_sync,
    generate_vision_async,
    generate_vision_sync,
)
from .prompting import PromptRegistry
from .prompts import build_group_commentary_prompt, build_post_commentary_prompt
from .protocol import drop_legacy_full_score_overall, parse_fast_screening

_log = logging.getLogger("material_agent")


def parse_vision_response(text: str) -> dict:
    return drop_legacy_full_score_overall(parse_contract_vision_response(text))


class OllamaClient:
    def __init__(self, config: dict):
        self.base_url = config["base_url"].rstrip("/")
        self.timeout = config["timeout"]
        self.vision_model = config["vision_model"]
        self.commentary_model = config["commentary_model"]
        self.output_language = config.get("output_language", "zh")
        self.vision_temperature = config.get("vision_temperature", 0.3)
        self.vision_retries = config.get("vision_retries", 3)

    def score_image(self, jpeg_bytes: bytes) -> dict:
        prompt = build_vision_prompt(self.output_language)
        last_err: Exception = RuntimeError("vision_retries exhausted with no attempts")
        for attempt in range(1, self.vision_retries + 1):
            try:
                text = self._vision_raw(self.vision_model, prompt, jpeg_bytes)
                return parse_vision_response(text)
            except (ValueError, requests.RequestException) as error:
                last_err = error
                _log.warning("Ollama vision attempt %s/%s failed: %s", attempt, self.vision_retries, error)
        _log.error("Ollama vision failed after %s attempts: %s", self.vision_retries, last_err)
        raise last_err

    def generate_group_commentary(self, group_data: str) -> str:
        prompt = build_group_commentary_prompt(group_data, output_language=self.output_language)
        return self._text_call(self.commentary_model, prompt)

    def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        prompt = build_post_commentary_prompt(
            score_line,
            group_commentary,
            output_language=self.output_language,
        )
        return self._text_call(self.commentary_model, prompt)

    def _vision_raw(self, model: str, prompt: str, jpeg_bytes: bytes) -> str:
        return generate_vision_sync(
            base_url=self.base_url,
            model=model,
            prompt=prompt,
            jpeg_bytes=jpeg_bytes,
            temperature=self.vision_temperature,
            timeout=self.timeout,
        )

    def _text_call(self, model: str, prompt: str) -> str:
        return generate_text_sync(
            base_url=self.base_url,
            model=model,
            prompt=prompt,
            timeout=self.timeout,
        )


class AsyncOllamaClient:
    def __init__(self, config: dict):
        self.base_url = config["base_url"].rstrip("/")
        self.vision_model = config["vision_model"]
        self.fast_vision_model = config.get("fast_vision_model", self.vision_model)
        self.commentary_model = config["commentary_model"]
        self.output_language = config.get("output_language", "zh")
        self.vision_temperature = config.get("vision_temperature", 0.3)
        self.vision_retries = config.get("vision_retries", 3)
        self.prompt_registry = PromptRegistry(
            {
                "full_vision_model": self.vision_model,
                "fast_vision_model": self.fast_vision_model,
                "commentary_model": self.commentary_model,
                "output_language": self.output_language,
                "vision_temperature": self.vision_temperature,
                "vision_max_tokens": 192,
                "fast_vision_max_tokens": 96,
                "requests": {
                    "prompt_preset": "default",
                    "contract_mode": "structured_outputs",
                    "model_profile_mode": "off",
                },
                "model_profiles": {},
            }
        )
        self._timeout = httpx.Timeout(config["timeout"])

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        bundle = self.prompt_registry.resolve("full_score", model=self.vision_model)
        last_err: Exception = RuntimeError("vision_retries exhausted with no attempts")
        for attempt in range(1, self.vision_retries + 1):
            try:
                text = await self._vision_raw(self.vision_model, bundle.prompt, jpeg_bytes)
                return parse_vision_response(text)
            except (ValueError, httpx.HTTPError) as error:
                last_err = error
                _log.warning("Ollama vision attempt %s/%s failed: %s", attempt, self.vision_retries, error)
        _log.error("Ollama vision failed after %s attempts: %s", self.vision_retries, last_err)
        raise last_err

    async def score_image_fast(self, jpeg_bytes: bytes) -> dict[str, float]:
        bundle = self.prompt_registry.resolve("fast_score", model=self.fast_vision_model)
        last_err: Exception = RuntimeError("fast score retries exhausted")
        for attempt in range(1, self.vision_retries + 1):
            try:
                text = await self._vision_raw(self.fast_vision_model, bundle.prompt, jpeg_bytes)
                return parse_fast_screening(text)
            except (ValueError, httpx.HTTPError) as error:
                last_err = error
                _log.warning("Ollama fast vision attempt %s/%s failed: %s", attempt, self.vision_retries, error)
        _log.error("Ollama fast vision failed after %s attempts: %s", self.vision_retries, last_err)
        raise last_err

    async def generate_group_commentary(self, group_data: str) -> str:
        prompt = build_group_commentary_prompt(group_data, output_language=self.output_language)
        return await self._text_call(self.commentary_model, prompt)

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        prompt = build_post_commentary_prompt(
            score_line,
            group_commentary,
            output_language=self.output_language,
        )
        return await self._text_call(self.commentary_model, prompt)

    async def _vision_raw(self, model: str, prompt: str, jpeg_bytes: bytes) -> str:
        return await generate_vision_async(
            base_url=self.base_url,
            model=model,
            prompt=prompt,
            jpeg_bytes=jpeg_bytes,
            temperature=self.vision_temperature,
            timeout=self._timeout,
        )

    async def _text_call(self, model: str, prompt: str) -> str:
        return await generate_text_async(
            base_url=self.base_url,
            model=model,
            prompt=prompt,
            timeout=self._timeout,
        )
