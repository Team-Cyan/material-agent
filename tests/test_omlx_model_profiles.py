import asyncio

from material_agent.app.omlx_benchmark_service import BenchmarkCandidate, OMLXBenchmarkService
from material_agent.clients.omlx import AsyncOMLXClient


def _config() -> dict:
    return {
        "base_url": "http://127.0.0.1:11435",
        "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
        "timeout": 120,
        "vision_temperature": 0.0,
        "commentary_temperature": 0.0,
        "fast_vision_max_tokens": 96,
        "vision_max_tokens": 192,
        "group_commentary_max_tokens": 160,
        "post_commentary_max_tokens": 160,
        "requests": {
            "contract_mode": "response_format_json_schema",
            "prompt_preset": "default",
            "model_profile_mode": "auto",
            "enable_thinking": False,
            "temperature": 0.0,
            "xtc_probability": 0.0,
        },
        "model_profiles": {
            "Qwen3-VL-4B-Instruct-4bit": {
                "request_overrides": {
                    "prompt_preset": "qwen3",
                    "vision_temperature": 0.1,
                    "commentary_temperature": 0.2,
                    "vision_max_tokens": 222,
                    "post_commentary_max_tokens": 111,
                },
                "prompt_overrides": {
                    "full_prompt_extra": "Stay grounded in visible details.",
                    "post_prompt_extra": "Give only practical retouching steps.",
                },
            }
        },
    }


def test_async_omlx_client_applies_model_profile_to_full_prompt(monkeypatch):
    client = AsyncOMLXClient(_config())
    captured = {}

    async def _fake_vision_raw(
        model,
        prompt,
        jpeg_bytes,
        enable_thinking,
        max_tokens=None,
        temperature=None,
        response_format=None,
        response_mode="full",
    ):
        captured.update(
            {
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
                "response_mode": response_mode,
            }
        )
        return (
            '{"scene":"people","scene_raw":"人物坐在砖墙边","subject":7.5,"composition":8.0,'
            '"lighting":6.5,"color":7.0,"clarity":8.5,"depth":7.0,"mood":7.5}'
        )

    monkeypatch.setattr(client, "_vision_raw", _fake_vision_raw)

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert captured["model"] == "Qwen3-VL-4B-Instruct-4bit"
    assert captured["max_tokens"] == 222
    assert captured["temperature"] == 0.1
    assert captured["response_mode"] == "full"
    assert "Stay grounded in visible details." in captured["prompt"]
    assert "output the final JSON object only" in captured["prompt"]


def test_async_omlx_client_applies_model_profile_to_post_prompt(monkeypatch):
    client = AsyncOMLXClient(_config())
    captured = {}

    async def _fake_generate_text(prompt, model, response_format=None, max_tokens=None, temperature=None):
        captured.update(
            {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        return '{"post":"后期先提一点阴影，再轻压高光。"}'

    monkeypatch.setattr(client, "generate_text", _fake_generate_text)

    result = asyncio.run(client.generate_post_commentary("exp:9.0 sharp:8.0", "【组内问题】整体偏暗。"))

    assert "后期指导" in result
    assert captured["model"] == "Qwen3-VL-4B-Instruct-4bit"
    assert captured["max_tokens"] == 111
    assert captured["temperature"] == 0.2
    assert "Give only practical retouching steps." in captured["prompt"]
    assert "output the final JSON object only" in captured["prompt"]


def test_omlx_benchmark_candidate_config_turns_off_model_profiles():
    service = OMLXBenchmarkService()
    candidate = BenchmarkCandidate(
        contract_mode="response_format_json_schema",
        prompt_preset="qwen3",
        vision_temperature=0.0,
        commentary_temperature=0.0,
        vision_max_tokens=192,
        post_commentary_max_tokens=160,
        enable_thinking=False,
        image_max_edge=1024,
        vision_jpeg_quality=92,
    )

    built = service._build_candidate_config(
        {
            "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
            "requests": {"model_profile_mode": "auto"},
            "model_profiles": {"Qwen3-VL-4B-Instruct-4bit": {"request_overrides": {"vision_max_tokens": 1}}},
        },
        "Qwen3-VL-4B-Instruct-4bit",
        candidate,
    )

    assert built["requests"]["model_profile_mode"] == "off"
