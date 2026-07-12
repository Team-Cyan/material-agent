import asyncio
import json
import logging

import httpx
import numpy as np

from material_agent.clients.base import make_client
from material_agent.clients.local import AsyncLocalClient
from material_agent.clients.ollama import AsyncOllamaClient
from material_agent.clients.omlx import AsyncOMLXClient
from material_agent.clients.protocol import parse_fast_score
from material_agent.core.commentary import (
    CommentaryGenerator,
    build_group_commentary_input,
    build_photo_commentary_context,
    regenerate_group_commentary,
    regenerate_post_commentary,
)
from material_agent.core.scoring_engine import RawFrame, compute_scores
from material_agent.scorers.base import ScorerResult


def _omlx_full_score_payload(**overrides) -> dict:
    payload = {
        "scene": "people",
        "scene_raw": "舞台上的人物",
        "subject": 7.0,
        "composition": 6.0,
        "lighting": 5.0,
        "color": 4.0,
        "clarity": 3.0,
        "depth": 2.0,
        "mood": 1.0,
    }
    payload.update(overrides)
    return payload


def _omlx_full_score_content(**overrides) -> str:
    return json.dumps(_omlx_full_score_payload(**overrides), ensure_ascii=False)


def _base_config() -> dict:
    return {
        "scorers": {
            "exposure": {
                "enabled": True,
                "weight": 0.5,
                "min_score": 0.0,
                "overexpose_threshold": 0.02,
                "overexpose_hard_limit": 2.0,
                "underexpose_threshold": 0.20,
                "underexpose_hard_limit": 2.0,
            },
            "sharpness": {
                "enabled": True,
                "weight": 0.5,
                "min_score": 0.0,
                "min_variance": 50,
                "max_variance": 1000,
            },
            "subject": {"enabled": True},
            "composition": {"enabled": True},
            "lighting": {"enabled": True},
            "color": {"enabled": True},
            "clarity": {"enabled": True},
            "depth": {"enabled": True},
            "mood": {"enabled": True},
        },
        "grouping": {
            "enabled": False,
            "visual_similarity": {"enabled": False},
            "group_guard": {"enabled": False, "min_score": 7.0},
        },
        "preview": {"max_size": 256, "jpeg_quality": 85},
        "scoring": {"pixel_weight": 0.3, "vision_weight": 0.7},
        "scene_weights": {
            "default": {
                "subject": 1 / 7,
                "composition": 1 / 7,
                "lighting": 1 / 7,
                "color": 1 / 7,
                "clarity": 1 / 7,
                "depth": 1 / 7,
                "mood": 1 / 7,
            }
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
        },
    }


def test_make_client_defaults_to_local():
    client = make_client(_base_config())
    assert isinstance(client, AsyncLocalClient)


def test_make_client_passes_inference_config_to_local_client():
    cfg = _base_config()
    cfg["inference"] = {
        "runtime": "cpu",
        "device": "CPU",
        "fallback_device": "CPU",
        "provider_tags": ["cpu"],
    }

    client = make_client(cfg)

    assert isinstance(client, AsyncLocalClient)
    assert client.inference["runtime"] == "cpu"
    assert client.runtime == "cpu"


def test_make_client_supports_legacy_vision_backend():
    cfg = _base_config()
    cfg["vision_backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "fast_vision_model": "Qwen/Qwen2.5-VL-3B-Instruct",
        "full_vision_model": "Qwen/Qwen2.5-VL-7B-Instruct",
        "commentary_model": "Qwen/Qwen2.5-VL-7B-Instruct",
        "timeout": 30,
    }
    client = make_client(cfg)
    assert isinstance(client, AsyncOMLXClient)


def test_async_omlx_client_sends_bearer_token(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": _omlx_full_score_content()}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:8000",
            "fast_vision_model": "Qwen/Qwen2.5-VL-3B-Instruct",
            "full_vision_model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "commentary_model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "timeout": 30,
            "api_key": "secret-token",
        }
    )

    asyncio.run(client.generate_text("hello", client.commentary_model))
    asyncio.run(client._vision_raw(client.full_vision_model, "prompt", b"jpeg", enable_thinking=False))

    assert len(requests) == 2
    assert requests[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert requests[1]["headers"]["Authorization"] == "Bearer secret-token"


def test_async_omlx_score_image_disables_thinking_and_caps_tokens(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": _omlx_full_score_content()}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_max_tokens": 256,
            "vision_retries": 1,
            "requests": {"enable_thinking": True},
        }
    )

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert requests[0]["json"]["enable_thinking"] is False
    assert requests[0]["json"]["max_tokens"] == 256
    assert "response_format" not in requests[0]["json"]
    structured_outputs = requests[0]["json"]["structured_outputs"]
    assert structured_outputs["json"]["required"] == [
        "scene",
        "scene_raw",
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]
    assert requests[0]["json"]["messages"][0]["role"] == "system"
    assert requests[0]["json"]["messages"][1]["role"] == "user"
    content = requests[0]["json"]["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert "Analyze the image using the provided scoring contract." in content[0]["text"]
    assert '"scene": "one of [' in content[0]["text"]
    assert "Do not double-count a technical flaw" in content[0]["text"]


def test_async_omlx_full_request_schema_does_not_require_overall(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": _omlx_full_score_content()
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert requests[0]["json"]["structured_outputs"]["json"]["required"] == [
        "scene",
        "scene_raw",
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]
    assert "overall" not in requests[0]["json"]["structured_outputs"]["json"]["required"]
    assert "overall" not in requests[0]["json"]["structured_outputs"]["json"]["properties"]


def test_async_omlx_score_image_ignores_legacy_overall_in_response(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "overall": 9.9,
                                    "scene": "people",
                                    "scene_raw": "舞台上的人物",
                                    "subject": 7.0,
                                    "composition": 6.0,
                                    "lighting": 5.0,
                                    "color": 4.0,
                                    "clarity": 3.0,
                                    "depth": 2.0,
                                    "mood": 1.0,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert result["subject"] == 7.0
    assert "overall" not in result


def test_async_omlx_fast_score_requires_signal_object_contract(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "technical_ok": 0.2,
                                    "subject_clear": 0.4,
                                    "composition_ok": 0.3,
                                    "usable_for_selection": 0.1,
                                }
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "fast_vision_max_tokens": 96,
        }
    )

    score = asyncio.run(client.score_image_fast(b"jpeg"))

    assert score == {
        "technical_ok": 0.2,
        "subject_clear": 0.4,
        "composition_ok": 0.3,
        "usable_for_selection": 0.1,
    }
    assert requests[0]["json"]["max_tokens"] == 96
    assert "response_format" not in requests[0]["json"]
    structured_outputs = requests[0]["json"]["structured_outputs"]
    assert structured_outputs["json"]["required"] == [
        "technical_ok",
        "subject_clear",
        "composition_ok",
        "usable_for_selection",
    ]


def test_async_omlx_fast_request_uses_text_first_compact_json_contract(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"technical_ok": 0.2, "subject_clear": 0.4, '
                                '"composition_ok": 0.3, "usable_for_selection": 0.1}'
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "fast_vision_max_tokens": 96,
        }
    )

    score = asyncio.run(client.score_image_fast(b"jpeg"))

    assert score == {
        "technical_ok": 0.2,
        "subject_clear": 0.4,
        "composition_ok": 0.3,
        "usable_for_selection": 0.1,
    }
    assert requests[0]["json"]["messages"][0]["content"] == (
        "You analyze photos and return exactly one JSON object that matches the user's contract."
    )
    content = requests[0]["json"]["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert '"technical_ok": 0.0' in content[0]["text"]
    assert '"usable_for_selection": 0.0' in content[0]["text"]
    assert "worth keeping or reviewing" in content[0]["text"]
    assert "your first character must be {" not in content[0]["text"]
    assert "do not add extra keys" not in content[0]["text"]


def test_async_omlx_full_request_uses_text_first_json_contract(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "parsed": {
                                "scene": "people",
                                "scene_raw": "舞台上的人物",
                                "subject": 7.0,
                                "composition": 6.0,
                                "lighting": 5.0,
                                "color": 4.0,
                                "clarity": 3.0,
                                "depth": 2.0,
                                "mood": 1.0,
                            },
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert "response_format" not in requests[0]["json"]
    structured_outputs = requests[0]["json"]["structured_outputs"]
    assert structured_outputs["json"]["required"] == [
        "scene",
        "scene_raw",
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]
    assert requests[0]["json"]["messages"][0]["content"] == (
        "You analyze photos and return exactly one JSON object that matches the user's contract."
    )
    content = requests[0]["json"]["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_async_omlx_score_image_uses_parsed_payload_when_content_is_none(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "parsed": {
                                "scene": "people",
                                "scene_raw": "舞台上的人物",
                                "subject": 7.0,
                                "composition": 6.0,
                                "lighting": 5.0,
                                "color": 4.0,
                                "clarity": 3.0,
                                "depth": 2.0,
                                "mood": 1.0,
                            },
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert result["scene_raw"] == "舞台上的人物"
    assert result["subject"] == 7.0


def test_async_omlx_logs_summary_without_base64(monkeypatch, caplog):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": _omlx_full_score_content()}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_max_tokens": 256,
            "vision_retries": 1,
        }
    )

    import logging
    with caplog.at_level(logging.DEBUG, logger="material_agent"):
        asyncio.run(client.score_image(b"jpeg-bytes"))

    messages = "\n".join(record.message for record in caplog.records)
    assert "OMLX vision request" in messages
    assert "image_bytes=10" in messages
    assert "max_tokens=256" in messages
    assert "data:image/jpeg;base64" not in messages


def test_async_omlx_score_image_raises_when_response_payload_is_malformed(monkeypatch, caplog):
    requests = []

    class _FakeResponse:
        def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
            self.status_code = status_code
            self._body = body or {}
            self.text = text
            self.request = httpx.Request("POST", "http://localhost:11435/v1/chat/completions")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("bad request", request=self.request, response=self)
            return None

        def json(self):
            return self._body

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse(200, body={})

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    import pytest

    with caplog.at_level(logging.WARNING, logger="material_agent"):
        with pytest.raises(ValueError, match="Malformed OMLX response payload"):
            asyncio.run(client.score_image(b"jpeg"))

    assert len(requests) == 1
    assert "response_format" not in requests[0]["json"]
    structured_outputs = requests[0]["json"]["structured_outputs"]
    assert structured_outputs["json"]["required"] == [
        "scene",
        "scene_raw",
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]
    assert "retrying without it" not in "\n".join(record.message for record in caplog.records)


def test_async_omlx_score_image_raises_on_empty_structured_body_without_retry(monkeypatch, caplog):
    requests = []

    class _FakeResponse:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            if len(requests) == 1:
                return _FakeResponse(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "reasoning_content": None,
                                    "tool_calls": None,
                                }
                            }
                        ]
                    }
                )
            return _FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"scene":"people","scene_raw":"舞台上的人物","subject":7.0,'
                                    '"composition":6.0,"lighting":5.0,"color":4.0,'
                                    '"clarity":3.0,"depth":2.0,"mood":1.0}'
                                )
                            }
                        }
                    ]
                }
            )

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_max_tokens": 256,
            "vision_retries": 1,
        }
    )

    with caplog.at_level(logging.WARNING, logger="material_agent"):
        import pytest
        with pytest.raises(ValueError, match="Empty or non-text OMLX structured response"):
            asyncio.run(client.score_image(b"jpeg"))

    assert len(requests) == 1
    assert "response_format" not in requests[0]["json"]
    structured_outputs = requests[0]["json"]["structured_outputs"]
    assert structured_outputs["json"]["required"] == [
        "scene",
        "scene_raw",
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]
    assert "empty structured body" not in "\n".join(record.message for record in caplog.records).lower()


def test_async_omlx_fast_score_raises_on_invalid_structured_output(monkeypatch):
    requests = []

    class _FakeResponse:
        def __init__(self, content: str):
            self._content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            if len(requests) == 1:
                return _FakeResponse("This is not a photograph and cannot be rated usefully in the requested format.")
            return _FakeResponse(
                '{"scene":"people","scene_raw":"舞台上的人物","subject":7.0,"composition":6.0,'
                '"lighting":5.0,"color":4.0,"clarity":3.0,"depth":2.0,"mood":1.0}'
            )

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    import pytest

    with pytest.raises(ValueError, match="No reliable fast score"):
        asyncio.run(client.score_image_fast(b"jpeg"))
    assert len(requests) == 1


def test_async_omlx_fast_score_retries_parse_failures_until_success(monkeypatch):
    requests = []

    class _FakeResponse:
        def __init__(self, content: str):
            self._content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            if len(requests) == 1:
                return _FakeResponse("This is not valid JSON for the requested fast score.")
            return _FakeResponse(
                '{"technical_ok": 0.4, "subject_clear": 0.5, "composition_ok": 0.6, "usable_for_selection": 0.7}'
            )

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 3,
        }
    )

    score = asyncio.run(client.score_image_fast(b"jpeg"))
    assert score == {
        "technical_ok": 0.4,
        "subject_clear": 0.5,
        "composition_ok": 0.6,
        "usable_for_selection": 0.7,
    }
    assert len(requests) == 2


def test_async_omlx_fast_score_does_not_treat_scale_text_as_zero(monkeypatch):
    requests = []

    class _FakeResponse:
        def __init__(self, content: str):
            self._content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            if len(requests) == 1:
                return _FakeResponse(
                    "The user wants a rating for the provided photo on a scale of 0.0 to 10.0. "
                    "The rating should cover overall quality and usefulness. "
                    "The output must be a JSON object with a single key."
                )
            return _FakeResponse(
                '{"scene":"people","scene_raw":"舞台上的人物","subject":7.0,"composition":6.0,'
                '"lighting":5.0,"color":4.0,"clarity":3.0,"depth":2.0,"mood":1.0}'
            )

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    import pytest

    with pytest.raises(ValueError, match="No reliable fast score"):
        asyncio.run(client.score_image_fast(b"jpeg"))
    assert len(requests) == 1


def test_async_omlx_debug_logs_full_payload_without_base64(monkeypatch, caplog):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": _omlx_full_score_content(composition=7.0)
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_max_tokens": 256,
            "log_level": "debug",
        }
    )

    import logging
    with caplog.at_level(logging.DEBUG, logger="material_agent"):
        asyncio.run(client.score_image(b"jpeg-bytes"))

    messages = "\n".join(record.message for record in caplog.records)
    assert "OMLX vision request payload=" in messages
    assert '"max_tokens": 256' in messages
    assert '"image_url": {"url": "[omitted base64 image; bytes=10]"}' in messages
    assert "data:image/jpeg;base64" not in messages
    assert "OMLX vision response payload={" in messages
    assert '"scene": "people"' in messages
    assert '"composition": 7.0' in messages


def test_async_omlx_generate_text_accepts_text_part_lists(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "【组内问题】整体偏暗。"}
                            ]
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
        }
    )

    text = asyncio.run(client.generate_text("写一句点评", client.commentary_model))
    assert text == "【组内问题】整体偏暗。"


def test_async_omlx_generate_text_uses_commentary_max_tokens(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "【后期指导】阴影提一点。"}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "commentary_max_tokens": 96,
        }
    )

    text = asyncio.run(client.generate_text("写一句点评", client.commentary_model))

    assert text == "【后期指导】阴影提一点。"
    assert requests[0]["json"]["max_tokens"] == 96


def test_async_omlx_generate_group_commentary_formats_structured_json(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "parsed": {
                                "group_issues": "整体偏暗，舞台高光也有点硬。",
                                "shooting": "拍摄时补一点面光并避开最刺眼的灯位。",
                            }
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append(json)
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "commentary_max_tokens": 160,
            "group_commentary_max_tokens": 256,
            "requests": {"temperature": 0.7},
        }
    )

    text = asyncio.run(client.generate_group_commentary("1. a.jpg total=7.0"))

    assert text == "【组内问题】整体偏暗，舞台高光也有点硬。\n【拍摄建议】拍摄时补一点面光并避开最刺眼的灯位。"
    structured_outputs = requests[0]["structured_outputs"]
    assert structured_outputs["json"]["required"] == ["group_issues", "shooting"]
    assert requests[0]["max_tokens"] == 256
    assert requests[0]["temperature"] == 0.0


def test_async_omlx_generate_text_uses_structured_outputs_without_retry_fallback(monkeypatch, caplog):
    requests = []

    class _FakeResponse:
        def __init__(self, status_code, *, text="", body=None):
            self.status_code = status_code
            self.text = text
            self._body = body or {}
            self.request = httpx.Request("POST", "http://localhost:11435/v1/chat/completions")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("boom", request=self.request, response=self)

        def json(self):
            return self._body

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append(json)
            structured_outputs = json.get("structured_outputs")
            if structured_outputs is not None:
                return _FakeResponse(400, text="unsupported field: structured_outputs")
            return _FakeResponse(200, body={})

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
        }
    )

    import pytest

    with caplog.at_level(logging.WARNING, logger="material_agent"):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(
                client.generate_text(
                    "Return one compact JSON object only.",
                    client.commentary_model,
                    response_format={
                        "json": {
                            "type": "object",
                            "properties": {
                                "post": {"type": "string", "minLength": 1},
                            },
                            "required": ["post"],
                            "additionalProperties": False,
                        },
                    },
                )
            )

    assert len(requests) == 1
    structured_outputs = requests[0]["structured_outputs"]
    assert structured_outputs["json"]["required"] == ["post"]
    assert "retrying without it" not in caplog.text


def test_async_omlx_generate_text_rejects_wrapped_json_for_structured_requests(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Thinking...\n"
                                '{"post":"后期把阴影提一点。"}\n'
                                "Done."
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
        }
    )

    import pytest

    with pytest.raises(ValueError, match="strict JSON object"):
        asyncio.run(
            client.generate_text(
                "Return one short post suggestion.",
                client.commentary_model,
                response_format={
                    "json": {
                        "type": "object",
                        "properties": {
                            "post": {"type": "string", "minLength": 1},
                        },
                        "required": ["post"],
                        "additionalProperties": False,
                    },
                },
            )
        )


def test_async_omlx_score_image_rejects_partial_json_even_if_json_exists(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"scene":"people","scene_raw":"人像","subject":8.0,'
                                '"composition":7.0,"lighting":7.0,"color":7.0,'
                                '"depth":6.0,"mood":8.0}'
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    import pytest

    with pytest.raises(ValueError, match="missing required keys"):
        asyncio.run(client.score_image(b"fake-jpeg"))


def test_async_omlx_generate_post_commentary_formats_structured_json(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "parsed": {
                                "post": "后期把阴影提一点，再轻压红色饱和度。"
                            }
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            requests.append(json)
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "commentary_max_tokens": 160,
            "post_commentary_max_tokens": 256,
        }
    )

    text = asyncio.run(client.generate_post_commentary("subject=8.0", "【组内问题】整体偏暗。"))

    assert text == "【后期指导】后期把阴影提一点，再轻压红色饱和度。"
    structured_outputs = requests[0]["structured_outputs"]
    assert structured_outputs["json"]["required"] == ["post"]
    assert requests[0]["max_tokens"] == 256


def test_async_omlx_generate_post_commentary_rejects_reasoning_text_without_json(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Thinking Process:\n"
                                "Draft ideas:\n"
                                '- "后期增加锐度和饱和度。"\n'
                                '- "建议后期加强锐化和调色。"\n'
                                '- "后期重点提升锐度和色彩。"\n'
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "commentary_max_tokens": 160,
            "post_commentary_max_tokens": 512,
        }
    )

    import pytest

    with pytest.raises(ValueError, match="No structured commentary JSON returned"):
        asyncio.run(client.generate_post_commentary("subject=8.0", "【组内问题】整体偏暗。"))


def test_async_omlx_generate_post_commentary_rejects_placeholder_values(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "parsed": {
                                "post": "string"
                            }
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "commentary_max_tokens": 160,
        }
    )

    import pytest

    with pytest.raises(ValueError, match="placeholder"):
        asyncio.run(client.generate_post_commentary("subject=8.0", "【组内问题】整体偏暗。"))


def test_async_omlx_generate_post_commentary_tolerates_extra_json_keys(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"scene":"people","decision":"keep",'
                                '"post":"后期先压一点高光，再把主体阴影轻提回来。"}'
                            )
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "commentary_max_tokens": 160,
        }
    )

    text = asyncio.run(client.generate_post_commentary("subject=8.0", "【组内问题】整体偏暗。"))

    assert text == "【后期指导】后期先压一点高光，再把主体阴影轻提回来。"


def test_async_ollama_fast_score_falls_back_to_vision_model(monkeypatch):
    client = AsyncOllamaClient(
        {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
        }
    )

    async def fake_vision_raw(model, prompt, jpeg_bytes):
        assert model == "llava:7b"
        return (
            '{"technical_ok": 0.6, "subject_clear": 0.5, '
            '"composition_ok": 0.4, "usable_for_selection": 0.7}'
        )

    monkeypatch.setattr(client, "_vision_raw", fake_vision_raw)
    score = asyncio.run(client.score_image_fast(b"fake"))
    assert score == {
        "technical_ok": 0.6,
        "subject_clear": 0.5,
        "composition_ok": 0.4,
        "usable_for_selection": 0.7,
    }


class _CommentaryClient:
    async def score_image(self, jpeg_bytes: bytes) -> dict:
        return {}

    async def score_image_fast(self, jpeg_bytes: bytes) -> float:
        return 0.0

    async def generate_group_commentary(self, group_data: str) -> str:
        raise RuntimeError("boom")

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        raise RuntimeError("boom")


def test_commentary_generator_returns_empty_when_disabled():
    gen = CommentaryGenerator(_CommentaryClient(), enabled=False)
    assert asyncio.run(gen.for_group([("a.jpg", 1.0)])) == ""
    assert asyncio.run(gen.for_photo("exp:1.0", "")) == ""


def test_commentary_generator_swallows_backend_errors():
    gen = CommentaryGenerator(_CommentaryClient(), enabled=True)
    assert asyncio.run(gen.for_group([("a.jpg", 1.0)])) == ""
    assert asyncio.run(gen.for_photo("exp:1.0", "")) == ""


def test_commentary_generator_logs_backend_errors(caplog):
    gen = CommentaryGenerator(_CommentaryClient(), enabled=True)
    with caplog.at_level(logging.WARNING, logger="material_agent"):
        assert asyncio.run(gen.for_group([("a.jpg", 1.0)])) == ""
    assert any("Group commentary failed" in record.message for record in caplog.records)


def test_commentary_generator_logs_error_type_when_message_is_empty(caplog):
    class _SilentCommentaryClient(_CommentaryClient):
        async def generate_group_commentary(self, group_data: str) -> str:
            raise TimeoutError()

    gen = CommentaryGenerator(_SilentCommentaryClient(), enabled=True)
    with caplog.at_level(logging.WARNING, logger="material_agent"):
        assert asyncio.run(gen.for_group([("a.jpg", 1.0)])) == ""
    assert any("TimeoutError" in record.message for record in caplog.records)


def test_commentary_generator_falls_back_to_group_heuristic_on_backend_error():
    gen = CommentaryGenerator(_CommentaryClient(), enabled=True)
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.5)],
            [
                {"exposure": 4.0, "clarity": 3.0, "lighting": 4.5, "composition": 6.5},
                {"exposure": 4.5, "clarity": 3.5, "lighting": 4.0, "composition": 6.0},
            ],
        )
    )
    assert "【组内问题】" in text
    assert "【拍摄建议】" in text


def test_commentary_generator_falls_back_to_post_heuristic_on_backend_error():
    gen = CommentaryGenerator(_CommentaryClient(), enabled=True)
    text = asyncio.run(
        gen.for_photo(
            "exp=4.0 clar=3.0",
            "",
            {"exposure": 4.0, "clarity": 3.0, "color": 5.0},
        )
    )
    assert text.startswith("【后期指导】")


def test_commentary_generator_refines_generic_group_output():
    class _GenericGroupClient(_CommentaryClient):
        async def generate_group_commentary(self, group_data: str) -> str:
            return (
                "【组内问题】这组照片主要短板在锐度和色彩，整体稳定性还不够。\n"
                "【拍摄建议】拍摄时先保住对焦和机身稳定，别让糊片拖掉整组完成度。"
            )

    gen = CommentaryGenerator(_GenericGroupClient(), enabled=True)
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.6)],
            [
                {"_scene": "people", "clarity": 4.0, "color": 5.2, "lighting": 6.0},
                {"_scene": "people", "clarity": 4.4, "color": 5.5, "lighting": 5.8},
            ],
        )
    )
    assert text.startswith("【组内问题】这组")
    assert "清晰=4.2" in text
    assert "人物场景" in text


def test_commentary_generator_refines_generic_post_output():
    class _GenericPostClient(_CommentaryClient):
        async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
            return "【后期指导】后期锐化要保守一点，优先保住可看的细节而不是硬拉。"

    gen = CommentaryGenerator(_GenericPostClient(), enabled=True)
    text = asyncio.run(
        gen.for_photo(
            "clarity=4.0 lighting=4.5 color=6.0",
            "",
            {"clarity": 4.0, "lighting": 4.5, "color": 6.0},
            scene="people",
        )
    )
    assert text.startswith("【后期指导】这张更该先救清晰和光线")
    assert "先把人物状态和轮廓保住" in text
    assert "锐化和降噪都收着做" in text


def test_commentary_generator_refines_post_output_when_model_returns_shooting_advice():
    class _WrongModePostClient(_CommentaryClient):
        async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
            return "【后期指导】拍摄时先确保对焦在人物眼睛上，使用三脚架保持机身稳定。"

    gen = CommentaryGenerator(_WrongModePostClient(), enabled=True)
    text = asyncio.run(
        gen.for_photo(
            "clarity=4.0 exposure=4.8 color=6.0",
            "",
            {"clarity": 4.0, "exposure": 4.8, "color": 6.0},
            scene="people",
        )
    )
    assert text.startswith("【后期指导】这张更该先救清晰和曝光")
    assert "拍摄时" not in text
    assert "三脚架" not in text


def test_commentary_generator_refines_group_output_when_model_returns_raw_score_dump():
    class _RawScoreGroupClient(_CommentaryClient):
        async def generate_group_commentary(self, group_data: str) -> str:
            return (
                "【组内问题】锐度=4.5, 曝光=5.3, 色彩=5.5, 构图=8.0, 主体=7.5\n"
                "【拍摄建议】拍摄时先保住对焦和机身稳定，别让糊片拖掉整组完成度。"
            )

    gen = CommentaryGenerator(_RawScoreGroupClient(), enabled=True)
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.6)],
            [
                {"_scene": "people", "clarity": 4.0, "exposure": 5.3, "color": 5.5, "subject": 7.5},
                {"_scene": "people", "clarity": 5.0, "exposure": 5.3, "color": 5.4, "subject": 7.5},
            ],
        )
    )
    assert text.startswith("【组内问题】这组")
    assert "清晰=" in text
    assert "人物场景" in text


def test_commentary_generator_refines_group_output_when_shooting_advice_is_empty_restatement():
    class _RestatedGroupClient(_CommentaryClient):
        async def generate_group_commentary(self, group_data: str) -> str:
            return (
                "【组内问题】锐度和色彩普遍偏弱，需加强细节表现与饱和度控制。\n"
                "【拍摄建议】提升锐度与色彩饱和度，确保舞台灯光下主体清晰且色彩鲜明。"
            )

    gen = CommentaryGenerator(_RestatedGroupClient(), enabled=True)
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.8)],
            [
                {"_scene": "people", "clarity": 4.0, "color": 5.1, "lighting": 6.1},
                {"_scene": "people", "clarity": 4.3, "color": 5.4, "lighting": 5.9},
            ],
        )
    )
    assert text.startswith("【组内问题】这组")
    assert "拍摄时优先把快门再提一点并稳住机位" in text
    assert "拍摄时尽量避开最脏的混色灯位" in text
    assert "提升锐度与色彩饱和度" not in text


def test_commentary_generator_refines_group_output_when_shooting_advice_is_generic_tripod_only():
    class _TripodOnlyGroupClient(_CommentaryClient):
        async def generate_group_commentary(self, group_data: str) -> str:
            return (
                "【组内问题】锐度和层次普遍偏弱，影响主体表现力。\n"
                "【拍摄建议】优先使用三脚架稳定机身，避免手持抖动。"
            )

    gen = CommentaryGenerator(_TripodOnlyGroupClient(), enabled=True)
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.8)],
            [
                {"_scene": "people", "_scene_raw": "舞台上的歌手", "clarity": 4.0, "depth": 5.1, "lighting": 6.2},
                {"_scene": "people", "_scene_raw": "舞台上的歌手", "clarity": 4.3, "depth": 5.3, "lighting": 6.0},
            ],
        )
    )
    assert text.startswith("【组内问题】这组")
    assert "优先使用三脚架稳定机身" not in text
    assert "拍摄时优先把快门再提一点并稳住机位" in text
    assert "拍摄时尝试换机位，把前后层次再拉开一点" in text


def test_commentary_generator_refines_english_group_output_when_zh_is_expected():
    class _EnglishGroupClient(_CommentaryClient):
        async def generate_group_commentary(self, group_data: str) -> str:
            return (
                "【组内问题】Color and lighting stay weak across the set, so the scene feels flat.\n"
                "【拍摄建议】Use a tripod and wait for cleaner light before pressing the shutter."
            )

    gen = CommentaryGenerator(_EnglishGroupClient(), enabled=True)
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.8)],
            [
                {"_scene": "people", "clarity": 4.0, "color": 5.1, "lighting": 5.0},
                {"_scene": "people", "clarity": 4.3, "color": 5.4, "lighting": 5.2},
            ],
        )
    )
    assert text.startswith("【组内问题】这组")
    assert "Color and lighting stay weak across the set" not in text
    assert "Use a tripod" not in text


def test_commentary_generator_refines_english_post_output_when_zh_is_expected():
    class _EnglishPostClient(_CommentaryClient):
        async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
            return (
                "【后期指导】Enhance color saturation slightly, soften the brightest sky area, "
                "and improve local contrast in the foreground."
            )

    gen = CommentaryGenerator(_EnglishPostClient(), enabled=True)
    text = asyncio.run(
        gen.for_photo(
            "clarity=4.0 lighting=4.5 color=6.0",
            "",
            {"clarity": 4.0, "lighting": 4.5, "color": 6.0},
            scene="people",
        )
    )
    assert text.startswith("【后期指导】这张更该先救")
    assert "Enhance color saturation slightly" not in text


def test_commentary_generator_fallback_can_output_english():
    gen = CommentaryGenerator(_CommentaryClient(), enabled=True, output_language="en")
    text = asyncio.run(
        gen.for_group(
            [("a.jpg", 6.0), ("b.jpg", 5.5)],
            [
                {"exposure": 4.0, "clarity": 3.0, "lighting": 4.5, "composition": 6.5},
                {"exposure": 4.5, "clarity": 3.5, "lighting": 4.0, "composition": 6.0},
            ],
        )
    )
    assert "Group issues:" in text
    assert "Shooting advice:" in text


def test_build_group_commentary_input_includes_scene_and_ranked_dims():
    text = build_group_commentary_input(
        [("a.jpg", 6.4), ("b.jpg", 7.1)],
        [
            {
                "_scene": "people",
                "_scene_raw": "桥边的人像",
                "_decision": "review",
                "exposure": 4.2,
                "lighting": 4.8,
                "composition": 7.5,
                "clarity": 5.0,
            },
            {
                "_scene": "city",
                "_scene_raw": "夜景街道",
                "_decision": "keep",
                "exposure": 6.8,
                "lighting": 5.1,
                "composition": 8.2,
                "clarity": 6.0,
            },
        ],
    )
    assert "scene=人物" in text
    assert "scene_raw=桥边的人像" in text
    assert "weak=曝光=4.2, 光线=4.8, 清晰=5.0" in text
    assert "strong=构图=7.5" in text
    assert "组内反复偏弱维度：" in text


def test_build_photo_commentary_context_includes_ranked_dims_and_breakdown():
    text = build_photo_commentary_context(
        "exp:5.0 sharp:8.0 subj:7.0 comp:8.5 lit:4.5 color:6.0 clar:5.5 dep:7.0 mood:6.5",
        scores={
            "exposure": 5.0,
            "sharpness": 8.0,
            "subject": 7.0,
            "composition": 8.5,
            "lighting": 4.5,
            "color": 6.0,
            "clarity": 5.5,
            "depth": 7.0,
            "mood": 6.5,
        },
        scene="people",
        scene_raw="桥边的人像",
        decision="review",
        visible_breakdown={
            "technical_quality": 5.4,
            "lighting": 4.5,
            "composition": 8.5,
            "mood_story": 6.5,
        },
    )
    assert "Scene: 人物 | Scene detail: 桥边的人像" in text
    assert "Decision: review" in text
    assert "Weak dimensions: 光线=4.5, 曝光=5.0, 清晰=5.5" in text
    assert "Strong dimensions: 构图=8.5, 锐度=8.0" in text
    assert "Visible breakdown: 光线=4.5, 技术质量=5.4" in text


def test_regenerated_group_commentary_varies_by_scene_context():
    stage_text = regenerate_group_commentary(
        [
            {"_scene": "people", "_scene_raw": "舞台上的歌手", "clarity": 4.0, "color": 5.0, "lighting": 6.2},
            {"_scene": "people", "_scene_raw": "舞台上的表演者", "clarity": 4.3, "color": 5.2, "lighting": 6.0},
        ]
    )
    camp_text = regenerate_group_commentary(
        [
            {"_scene": "landscape", "_scene_raw": "夜晚露营场景", "clarity": 4.0, "color": 5.0, "lighting": 6.2},
            {"_scene": "landscape", "_scene_raw": "山间露营营地", "clarity": 4.3, "color": 5.2, "lighting": 6.0},
        ]
    )

    assert stage_text != camp_text
    assert "主光" in stage_text or "混色灯位" in stage_text
    assert "露营" in camp_text or "氛围" in camp_text or "高光" in camp_text


def test_regenerated_post_commentary_varies_by_scene_rank_and_decision():
    people_keep = regenerate_post_commentary(
        {"clarity": 4.0, "color": 5.1, "sharpness": 5.3},
        scene="people",
        scene_raw="舞台上的歌手",
        decision="keep",
        rank=1,
        group_size=6,
    )
    camp_reject = regenerate_post_commentary(
        {"clarity": 4.0, "color": 5.1, "sharpness": 5.3},
        scene="landscape",
        scene_raw="夜晚露营场景",
        decision="reject",
        rank=5,
        group_size=6,
    )

    assert people_keep != camp_reject
    assert "这张在这组里已经靠前" in people_keep
    assert "舞台" in people_keep or "人物状态" in people_keep
    assert "先把能救回来的观感拉回及格线" in camp_reject
    assert "露营" in camp_reject or "氛围" in camp_reject


def test_regenerated_post_commentary_can_stably_spread_wording_by_variant_key():
    first = regenerate_post_commentary(
        {"clarity": 4.0, "color": 5.1, "sharpness": 5.3},
        scene="people",
        scene_raw="舞台上的歌手",
        variant_key="a.ARW",
    )
    second = regenerate_post_commentary(
        {"clarity": 4.0, "color": 5.1, "sharpness": 5.3},
        scene="people",
        scene_raw="舞台上的歌手",
        variant_key="b.ARW",
    )
    repeat_first = regenerate_post_commentary(
        {"clarity": 4.0, "color": 5.1, "sharpness": 5.3},
        scene="people",
        scene_raw="舞台上的歌手",
        variant_key="a.ARW",
    )

    assert first != second
    assert first == repeat_first


def test_regenerated_group_commentary_can_stably_spread_wording_by_variant_key():
    first = regenerate_group_commentary(
        [
            {"_scene": "people", "_scene_raw": "舞台上的歌手", "clarity": 4.0, "color": 5.0, "lighting": 6.2},
            {"_scene": "people", "_scene_raw": "舞台上的表演者", "clarity": 4.3, "color": 5.2, "lighting": 6.0},
        ],
        variant_key="group-a",
    )
    second = regenerate_group_commentary(
        [
            {"_scene": "people", "_scene_raw": "舞台上的歌手", "clarity": 4.0, "color": 5.0, "lighting": 6.2},
            {"_scene": "people", "_scene_raw": "舞台上的表演者", "clarity": 4.3, "color": 5.2, "lighting": 6.0},
        ],
        variant_key="group-b",
    )
    repeat_first = regenerate_group_commentary(
        [
            {"_scene": "people", "_scene_raw": "舞台上的歌手", "clarity": 4.0, "color": 5.0, "lighting": 6.2},
            {"_scene": "people", "_scene_raw": "舞台上的表演者", "clarity": 4.3, "color": 5.2, "lighting": 6.0},
        ],
        variant_key="group-a",
    )

    assert first != second
    assert first == repeat_first


def test_landscape_mountain_sunset_does_not_trigger_camp_language():
    text = regenerate_post_commentary(
        {"subject": 0.0, "sharpness": 2.4, "depth": 5.0, "mood": 8.0},
        scene="landscape",
        scene_raw="山间日落",
        decision="review",
        rank=2,
        group_size=2,
        variant_key="20241129_123125_01.arw",
    )

    assert "露营" not in text
    assert "火光" not in text
    assert "帐篷" not in text


def test_build_xmp_instructions_can_output_english_labels():
    from material_agent.domain.scoring_engine import build_xmp_instructions

    text = build_xmp_instructions({"exposure": 8.2, "clarity": 6.5}, output_language="en")
    assert "Exposure:8.2" in text
    assert "Clarity:6.5" in text


def test_async_omlx_logs_retry_warning_and_final_error(monkeypatch, caplog):
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 2,
        }
    )

    async def fake_vision_raw(*args, **kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(client, "_vision_raw", fake_vision_raw)
    with caplog.at_level(logging.WARNING, logger="material_agent"):
        import pytest
        with pytest.raises(ValueError, match="bad json"):
            asyncio.run(client.score_image(b"jpeg"))

    messages = "\n".join(record.message for record in caplog.records)
    assert "OMLX vision attempt 1/2 failed" in messages
    assert "OMLX vision failed after 2 attempts" in messages


def test_async_omlx_logs_full_response_when_json_parse_fails(monkeypatch, caplog):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "The user wants strict JSON output, but here is a prose answer instead."
                        }
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers=None):
            return _FakeResponse()

    monkeypatch.setattr("material_agent.clients.omlx.httpx.AsyncClient", _FakeAsyncClient)
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "fast_vision_model": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    import pytest

    with caplog.at_level(logging.WARNING, logger="material_agent"):
        with pytest.raises(ValueError, match="strict JSON object"):
            asyncio.run(client.score_image(b"jpeg"))

    messages = "\n".join(record.message for record in caplog.records)
    assert "OMLX vision invalid response payload=" in messages
    assert "The user wants strict JSON output" in messages


class _ScreeningClient:
    def __init__(self, fast_score=1.0, fast_error: Exception | None = None):
        self.fast_score = fast_score
        self.fast_error = fast_error
        self.score_image_called = False

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        self.score_image_called = True
        return {
            "scene": "people",
            "scene_raw": "舞台上的人物",
            "subject": 8.0,
            "composition": 8.0,
            "lighting": 8.0,
            "color": 8.0,
            "clarity": 8.0,
            "depth": 8.0,
            "mood": 8.0,
        }

    async def score_image_fast(self, jpeg_bytes: bytes) -> float:
        if self.fast_error:
            raise self.fast_error
        return self.fast_score

    async def generate_group_commentary(self, group_data: str) -> str:
        return ""

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        return ""


def test_scoring_engine_tier1_rejects_before_model_call():
    cfg = _base_config()
    cfg["screening"] = {"enabled": True, "tier1_threshold": 1.5, "tier2_threshold": 2.5}
    client = _ScreeningClient()
    frame = RawFrame(
        pixels=np.zeros((8, 8), dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.zeros((8, 8), dtype=np.uint8),
    )
    bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=client))
    assert bundle.status == "pixel_rejected"
    assert bundle.scene == "other"
    assert bundle.scene_raw == ""
    assert bundle.decision == "reject"
    assert "screening_tier1_reject" in bundle.decision_reasons
    assert bundle.visible_breakdown["technical_quality"] == 0.0
    assert bundle.screening_prior == 0.0
    assert bundle.signals
    assert client.score_image_called is False


def test_scoring_engine_tier2_fast_rejects_before_full_model():
    cfg = _base_config()
    cfg["screening"] = {"enabled": True, "tier1_threshold": 1.5, "tier2_threshold": 2.5}
    client = _ScreeningClient(fast_score=1.0)
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )
    bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=client))
    assert bundle.status == "fast_rejected"
    assert bundle.scene == "other"
    assert bundle.scene_raw == ""
    assert bundle.decision == "reject"
    assert "screening_tier2_reject" in bundle.decision_reasons
    assert bundle.screening_prior == 1.0
    assert bundle.visible_breakdown["technical_quality"] > 0.0
    assert bundle.signals
    assert client.score_image_called is False


def test_scoring_engine_fast_parse_failure_falls_back_to_full_model(caplog):
    cfg = _base_config()
    cfg["screening"] = {"enabled": True, "tier1_threshold": 1.5, "tier2_threshold": 2.5}
    client = _ScreeningClient(fast_error=ValueError("No reliable fast score"))
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )
    with caplog.at_level(logging.INFO, logger="material_agent"):
        bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=client))
    assert bundle.status == "full"
    assert bundle.scene == "people"
    assert client.score_image_called is True
    assert "Fast screening skipped after parse failure" in "\n".join(r.message for r in caplog.records)


def test_scoring_engine_logs_fast_rejection(caplog):
    cfg = _base_config()
    cfg["screening"] = {"enabled": True, "tier1_threshold": 1.5, "tier2_threshold": 2.5}
    client = _ScreeningClient(fast_score=1.0)
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )
    with caplog.at_level(logging.INFO, logger="material_agent"):
        bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=client))
    assert bundle.status == "fast_rejected"
    assert "Fast screening rejected image" in "\n".join(r.message for r in caplog.records)


def test_scoring_engine_full_path_builds_instructions():
    cfg = _base_config()
    client = _ScreeningClient(fast_score=8.0)
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )
    bundle = asyncio.run(compute_scores(frame, client, cfg))
    assert bundle.status == "full"
    assert bundle.scene == "people"
    assert "comp:" in bundle.instructions
    assert "exp:" in bundle.instructions


def test_scoring_engine_final_total_is_owned_by_local_layered_summary():
    cfg = _base_config()

    class _LegacyOverallClient(_ScreeningClient):
        async def score_image(self, jpeg_bytes: bytes) -> dict:
            self.score_image_called = True
            return {
                "overall": 9.9,
                "scene": "people",
                "scene_raw": "舞台上的人物",
                "subject": 6.0,
                "composition": 6.0,
                "lighting": 6.0,
                "color": 6.0,
                "clarity": 6.0,
                "depth": 6.0,
                "mood": 6.0,
            }

    client = _LegacyOverallClient(fast_score=8.0)
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )

    bundle = asyncio.run(compute_scores(frame, client, cfg))

    assert bundle.total == bundle.extra["layered_total"]
    assert bundle.total != 9.9
    assert bundle.extra["aggregated_total"] != bundle.total


def test_scoring_engine_uses_scene_aware_exposure_in_final_total(monkeypatch):
    cfg = _base_config()
    cfg["scorers"]["sharpness"]["enabled"] = False
    cfg["scorers"]["exposure"]["weight"] = 1.0
    cfg["scoring"] = {"pixel_weight": 1.0, "vision_weight": 0.0}
    for dim in ("composition", "lighting", "color", "clarity", "depth", "mood"):
        cfg["scorers"][dim]["enabled"] = False
    client = _ScreeningClient(fast_score=8.0)

    calls = []

    def fake_score_image(self, gray, scene=None):
        calls.append(scene)
        score = 1.0 if scene is None else 9.0
        return ScorerResult(
            name="exposure",
            score=score,
            enabled=True,
            weight=1.0,
            min_score=0.0,
            metadata={"exposure_scene": scene or "default"},
        )

    monkeypatch.setattr(
        "material_agent.core.scoring_engine.ExposureScorer.score_image",
        fake_score_image,
    )

    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )
    bundle = asyncio.run(compute_scores(frame, client, cfg))

    assert calls == [None, "people"]
    assert bundle.scores["exposure"] == 9.0
    assert bundle.meta["exposure_scene"] == "people"
    assert bundle.visible_breakdown["technical_quality"] == 9.0
    assert bundle.decision == "keep"
    assert bundle.total == 8.35


def test_parse_fast_score_rejects_numbered_list_reasoning():
    import pytest
    with pytest.raises(ValueError, match="No reliable fast score"):
        parse_fast_score("1. 构图一般\n2. 光线很差\n3. 整体质量较低")


def test_parse_fast_score_accepts_explicit_overall_label():
    assert parse_fast_score("overall: 2.7") == 2.7


def test_main_routes_scan_scenes(monkeypatch):
    import importlib

    cli_main_module = importlib.import_module("material_agent.shells.cli.main")

    called = {}

    def fake_scan(args):
        called["dir"] = args.dir

    monkeypatch.setattr(cli_main_module, "cmd_scan_scenes", fake_scan)
    monkeypatch.setattr("sys.argv", ["material-agent", "scan-scenes", "--dir", "/tmp/photos"])
    cli_main_module.main()
    assert called["dir"] == "/tmp/photos"


def test_make_fast_screening_port_keeps_screening_module_unloaded_when_disabled():
    import importlib
    import sys

    for module_name in (
        "material_agent.clients.base",
        "material_agent.adapters.screening",
        "material_agent.adapters.screening.musiq",
    ):
        sys.modules.pop(module_name, None)

    base_module = importlib.import_module("material_agent.clients.base")
    cfg = {
        "backend": "ollama",
        "screening": {"enabled": False},
        "scorers": {},
        "grouping": {},
        "preview": {},
        "scoring": {},
        "ollama": {"base_url": "http://127.0.0.1:11434", "vision_model": "vision", "commentary_model": "text", "timeout": 30},
    }

    assert "material_agent.adapters.screening" not in sys.modules
    assert base_module.make_fast_screening_port(cfg) is None
    assert "material_agent.adapters.screening" not in sys.modules
    assert "material_agent.adapters.screening.musiq" not in sys.modules


def test_async_omlx_client_exposes_prompt_registry_for_scoring_tasks():
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
            "timeout": 30,
        }
    )

    bundle = client.prompt_registry.resolve("full_score", model=client.full_vision_model)

    assert bundle.task == "full_score"
    assert bundle.request_options["max_tokens"] == client.vision_max_tokens


def test_async_omlx_client_exposes_prompt_registry_for_group_commentary():
    client = AsyncOMLXClient(
        {
            "base_url": "http://localhost:11435",
            "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
            "timeout": 30,
        }
    )

    bundle = client.prompt_registry.resolve(
        "group_commentary",
        model=client.commentary_model,
        group_data="1. a.jpg total=7.0",
    )

    assert bundle.task == "group_commentary"
    assert bundle.request_options["max_tokens"] == client.group_commentary_max_tokens
