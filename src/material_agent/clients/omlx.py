import base64
import json
import logging
from typing import Any

import httpx

from ..adapters.models.omlx.instance import discover_omlx_api_key
from ..adapters.models.omlx.contracts import (
    build_omlx_vision_messages,
    extract_omlx_message_content,
    extract_omlx_structured_json_text,
    omlx_structured_json_present,
    validate_omlx_full_score_payload,
)
from ..adapters.models.omlx.transport import post_chat_completion
from .ollama import parse_vision_response
from .prompting import PromptRegistry
from .protocol import extract_last_json_object, parse_fast_screening
from ..domain.commentary import format_group_commentary, format_post_commentary

_log = logging.getLogger("material_agent")


class AsyncOMLXClient:
    def __init__(self, config: dict):
        self.base_url = config["base_url"].rstrip("/")
        self.full_vision_model = config["full_vision_model"]
        self.fast_vision_model = config.get("fast_vision_model", self.full_vision_model)
        self.commentary_model = config["commentary_model"]
        self.output_language = config.get("output_language", "zh")
        self.api_key = discover_omlx_api_key(config)
        self.prompt_registry = PromptRegistry(config)
        self.log_level = config.get("log_level", "info")
        self.vision_temperature = config.get("vision_temperature", 0.0)
        self.fast_vision_max_tokens = config.get("fast_vision_max_tokens", 96)
        self.vision_max_tokens = config.get("vision_max_tokens", 192)
        self.commentary_temperature = config.get("commentary_temperature", 0.0)
        self.commentary_max_tokens = config.get("commentary_max_tokens", 128)
        self.group_commentary_max_tokens = config.get(
            "group_commentary_max_tokens",
            self.commentary_max_tokens,
        )
        self.post_commentary_max_tokens = config.get(
            "post_commentary_max_tokens",
            self.commentary_max_tokens,
        )
        self.request_schemas = config.get("requests", {})
        self.post_commentary_schema_name = self.request_schemas.get(
            "post_commentary_schema",
            "material_agent.post_commentary",
        )
        self.fast_vision_schema_name = self.request_schemas.get(
            "fast_vision_schema", "material_agent.fast_screening_signals"
        )
        self.vision_schema_name = self.request_schemas.get(
            "vision_schema", "material_agent.full_score"
        )
        self.contract_mode = str(
            self.request_schemas.get("contract_mode", "structured_outputs")
        ).lower()
        self.prompt_preset = str(self.request_schemas.get("prompt_preset", "default")).lower()
        self.structured_enable_thinking = bool(self.request_schemas.get("enable_thinking", False))
        self.structured_temperature = float(
            self.request_schemas.get("temperature", self.vision_temperature)
        )
        self.structured_xtc_probability = float(self.request_schemas.get("xtc_probability", 0.0))
        self.vision_retries = config.get("vision_retries", 2)
        self._timeout = httpx.Timeout(config["timeout"])

    def _headers(self) -> dict[str, str] | None:
        if not self.api_key:
            return None
        return {"Authorization": f"Bearer {self.api_key}"}

    def _debug_enabled(self) -> bool:
        return self.log_level == "debug"

    def _redact_payload(self, payload: dict) -> dict:
        redacted = json.loads(json.dumps(payload))
        messages = redacted.get("messages", [])
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    image_url = part.get("image_url")
                    if part.get("type") == "image_url" and isinstance(image_url, dict):
                        url = image_url.get("url", "")
                        if isinstance(url, str) and url.startswith("data:image/jpeg;base64,"):
                            b64 = url.split(",", 1)[1]
                            image_url["url"] = (
                                f"[omitted base64 image; bytes={len(base64.b64decode(b64))}]"
                            )
        return redacted

    def _log_invalid_response(self, prefix: str, text: str) -> None:
        _log.warning("%s payload=%r", prefix, text)

    def _apply_response_contract(
        self, payload: dict[str, Any], response_contract: dict | None
    ) -> None:
        if response_contract is None:
            return
        if self.contract_mode == "response_format_json_schema":
            payload["response_format"] = response_contract
            return
        payload["structured_outputs"] = response_contract

    def _vision_messages(
        self, prompt: str, img_b64: str, response_mode: str
    ) -> list[dict[str, Any]]:
        system_prompt = "You analyze photos and return exactly one JSON object that matches the user's contract."
        return build_omlx_vision_messages(prompt, img_b64, system_prompt=system_prompt)

    def _structured_json_present(self, text: str) -> bool:
        return omlx_structured_json_present(text)

    @staticmethod
    def _extract_message_content(body: dict) -> str:
        return extract_omlx_message_content(body)

    async def _post_chat(self, payload: dict) -> httpx.Response:
        resp = await post_chat_completion(
            base_url=self.base_url,
            payload=payload,
            headers=self._headers(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        bundle = self.prompt_registry.resolve("full_score", model=self.full_vision_model)
        last_err: Exception = RuntimeError("vision_retries exhausted with no attempts")
        for attempt in range(1, self.vision_retries + 1):
            text = ""
            try:
                text = await self._vision_raw(
                    bundle.model,
                    bundle.prompt,
                    jpeg_bytes,
                    enable_thinking=bundle.request_options["enable_thinking"],
                    max_tokens=bundle.request_options["max_tokens"],
                    temperature=bundle.request_options["temperature"],
                    response_format=bundle.response_format,
                    response_mode="full",
                )
                validate_omlx_full_score_payload(json.loads(text))
                return parse_vision_response(text)
            except ValueError as error:
                last_err = error
                _log.warning(
                    "OMLX vision attempt %s/%s failed: %s", attempt, self.vision_retries, error
                )
                if text:
                    self._log_invalid_response("OMLX vision invalid response", text)
            except httpx.HTTPError as error:
                last_err = error
                _log.warning(
                    "OMLX vision attempt %s/%s failed: %s", attempt, self.vision_retries, error
                )
        _log.error("OMLX vision failed after %s attempts: %s", self.vision_retries, last_err)
        raise last_err

    async def score_image_fast(self, jpeg_bytes: bytes) -> dict[str, float]:
        bundle = self.prompt_registry.resolve("fast_score", model=self.fast_vision_model)
        last_err: Exception = RuntimeError("fast score retries exhausted")
        for attempt in range(1, self.vision_retries + 1):
            text = ""
            try:
                text = await self._vision_raw(
                    bundle.model,
                    bundle.prompt,
                    jpeg_bytes,
                    enable_thinking=bundle.request_options["enable_thinking"],
                    max_tokens=bundle.request_options["max_tokens"],
                    temperature=bundle.request_options["temperature"],
                    response_format=bundle.response_format,
                    response_mode="fast",
                )
                return parse_fast_screening(text)
            except ValueError as error:
                last_err = error
                _log.warning(
                    "OMLX fast vision attempt %s/%s failed: %s", attempt, self.vision_retries, error
                )
                if text:
                    self._log_invalid_response("OMLX fast vision invalid response", text)
                continue
            except httpx.HTTPError as error:
                last_err = error
                _log.warning(
                    "OMLX fast vision attempt %s/%s failed: %s", attempt, self.vision_retries, error
                )
        if isinstance(last_err, ValueError):
            _log.warning(
                "OMLX fast vision giving control back to full scoring after invalid structured output"
            )
            raise ValueError("No reliable fast score") from last_err
        _log.error("OMLX fast vision failed after %s attempts: %s", self.vision_retries, last_err)
        raise last_err

    async def generate_group_commentary(self, group_data: str) -> str:
        bundle = self.prompt_registry.resolve(
            "group_commentary",
            model=self.commentary_model,
            group_data=group_data,
        )
        data = await self._generate_structured_commentary(
            bundle.prompt,
            bundle.response_format,
            ("group_issues", "shooting"),
            max_tokens=bundle.request_options["max_tokens"],
            temperature=bundle.request_options["temperature"],
        )
        return format_group_commentary(data["group_issues"], data["shooting"], self.output_language)

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        bundle = self.prompt_registry.resolve(
            "post_commentary",
            model=self.commentary_model,
            score_line=score_line,
            group_commentary=group_commentary,
        )
        data = await self._generate_structured_commentary(
            bundle.prompt,
            bundle.response_format,
            ("post",),
            max_tokens=bundle.request_options["max_tokens"],
            temperature=bundle.request_options["temperature"],
        )
        return format_post_commentary(data["post"], self.output_language)

    async def generate_text(
        self,
        prompt: str,
        model: str,
        response_format: dict | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        messages: list[dict[str, Any]]
        structured_request = response_format is not None
        if structured_request:
            messages = [
                {
                    "role": "system",
                    "content": "You provide concise photography guidance and follow the provided structured output schema.",
                },
                {"role": "user", "content": prompt},
            ]
        else:
            messages = [{"role": "user", "content": prompt}]
        effective_max_tokens = self.commentary_max_tokens if max_tokens is None else max_tokens
        if temperature is None:
            effective_temperature = (
                self.structured_temperature if structured_request else self.commentary_temperature
            )
        else:
            effective_temperature = temperature
        payload = {
            "model": model,
            "enable_thinking": self.structured_enable_thinking if structured_request else False,
            "messages": messages,
            "temperature": effective_temperature,
            "max_tokens": effective_max_tokens,
        }
        if structured_request:
            self._apply_response_contract(payload, response_format)
            if self.structured_xtc_probability > 0:
                payload["xtc_probability"] = self.structured_xtc_probability
        _log.debug(
            "OMLX text request model=%s prompt_chars=%s temperature=%s max_tokens=%s",
            model,
            len(prompt),
            effective_temperature,
            effective_max_tokens,
        )
        if self._debug_enabled():
            _log.debug("OMLX text request payload=%s", json.dumps(payload, ensure_ascii=False))
        resp = await self._post_chat(payload)
        body = resp.json()
        if structured_request:
            content = extract_omlx_structured_json_text(body).strip()
        else:
            content = self._extract_message_content(body).strip()
        _log.debug(
            "OMLX text response model=%s chars=%s preview=%r",
            model,
            len(content),
            content[:160],
        )
        if self._debug_enabled():
            _log.debug("OMLX text response payload=%s", content)
        return content

    async def _generate_structured_commentary(
        self,
        prompt: str,
        response_format: dict,
        required_fields: tuple[str, ...],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, str]:
        try:
            text = await self.generate_text(
                prompt,
                self.commentary_model,
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except ValueError as error:
            raise ValueError("No structured commentary JSON returned") from error
        try:
            data = extract_last_json_object(text)
        except ValueError as error:
            self._log_invalid_response("OMLX commentary invalid response", text)
            raise ValueError("No structured commentary JSON returned") from error

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(
                f"Structured commentary missing required keys {sorted(missing_fields)}, "
                f"got: {sorted(data)}"
            )
        extra_fields = [field for field in data if field not in required_fields]
        if extra_fields:
            _log.warning(
                "Structured commentary returned extra keys; keeping only required fields. "
                "required=%s extra=%s",
                sorted(required_fields),
                sorted(extra_fields),
            )
        normalized: dict[str, str] = {}
        for field in required_fields:
            value = data.get(field, "")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Structured commentary missing {field!r}")
            stripped = value.strip()
            if stripped.lower() in {"string", "text", "todo", "tbd", "n/a", "na"}:
                raise ValueError(f"Structured commentary placeholder for {field!r}")
            normalized[field] = stripped
        return normalized

    async def _vision_raw(
        self,
        model: str,
        prompt: str,
        jpeg_bytes: bytes,
        enable_thinking: bool,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict | None = None,
        response_mode: str = "full",
    ) -> str:
        img_b64 = base64.b64encode(jpeg_bytes).decode()
        payload = {
            "model": model,
            "enable_thinking": enable_thinking,
            "messages": self._vision_messages(prompt, img_b64, response_mode),
            "temperature": self.vision_temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        self._apply_response_contract(payload, response_format)
        if self.structured_xtc_probability > 0:
            payload["xtc_probability"] = self.structured_xtc_probability
        _log.debug(
            "OMLX vision request model=%s thinking=%s max_tokens=%s prompt_chars=%s image_bytes=%s",
            model,
            enable_thinking,
            max_tokens,
            len(prompt),
            len(jpeg_bytes),
        )
        if self._debug_enabled():
            _log.debug(
                "OMLX vision request payload=%s",
                json.dumps(self._redact_payload(payload), ensure_ascii=False),
            )
        resp = await self._post_chat(payload)
        body = resp.json()
        try:
            content = extract_omlx_structured_json_text(body)
        except ValueError:
            self._log_invalid_response(
                "OMLX vision invalid response",
                json.dumps(body, ensure_ascii=False),
            )
            raise
        _log.debug(
            "OMLX vision response model=%s chars=%s preview=%r",
            model,
            len(content),
            content[:160],
        )
        if self._debug_enabled():
            _log.debug("OMLX vision response payload=%s", content)
        return content
