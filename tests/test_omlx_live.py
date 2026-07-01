import asyncio
import os
from pathlib import Path

import cv2
import httpx
import pytest
import yaml

from material_agent.adapters.models.omlx.instance import discover_omlx_api_key
from material_agent.clients.omlx import AsyncOMLXClient
from material_agent.clients.prompts import (
    build_fast_prompt,
    build_full_prompt,
    build_group_commentary_prompt,
    build_group_commentary_response_format,
    build_post_commentary_prompt,
    build_post_commentary_response_format,
)
from material_agent.clients.protocol import extract_last_json_object
from material_agent.utils.config_validator import normalize_config
from material_agent.utils.constants import SCENE_LIST, VISION_DIMS


def _load_live_omlx_config() -> dict:
    if os.getenv("PIXEL_JUDGE_RUN_OMLX_TESTS") != "1":
        pytest.skip(
            "Set PIXEL_JUDGE_RUN_OMLX_TESTS=1 to run live OMLX integration tests.",
        )

    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = normalize_config(raw)
    omlx = dict(config.get("omlx", {}))

    omlx["base_url"] = os.getenv("PIXEL_JUDGE_OMLX_BASE_URL", omlx.get("base_url", ""))
    discovered_api_key = discover_omlx_api_key(config)
    omlx["api_key"] = os.getenv(
        "PIXEL_JUDGE_OMLX_API_KEY", omlx.get("api_key") or discovered_api_key
    )
    omlx["fast_vision_model"] = os.getenv(
        "PIXEL_JUDGE_OMLX_FAST_MODEL",
        omlx.get("fast_vision_model", ""),
    )
    omlx["full_vision_model"] = os.getenv(
        "PIXEL_JUDGE_OMLX_FULL_MODEL",
        omlx.get("full_vision_model", ""),
    )
    omlx["commentary_model"] = os.getenv(
        "PIXEL_JUDGE_OMLX_COMMENTARY_MODEL",
        omlx.get("commentary_model", omlx.get("fast_vision_model", "")),
    )
    omlx["timeout"] = int(os.getenv("PIXEL_JUDGE_OMLX_TIMEOUT", str(omlx.get("timeout", 120))))
    omlx["vision_retries"] = int(os.getenv("PIXEL_JUDGE_OMLX_VISION_RETRIES", "1"))
    omlx["vision_temperature"] = float(os.getenv("PIXEL_JUDGE_OMLX_VISION_TEMPERATURE", "0.0"))
    omlx["commentary_temperature"] = float(
        os.getenv("PIXEL_JUDGE_OMLX_COMMENTARY_TEMPERATURE", "0.0")
    )
    omlx["fast_vision_max_tokens"] = int(os.getenv("PIXEL_JUDGE_OMLX_FAST_MAX_TOKENS", "256"))
    omlx["vision_max_tokens"] = int(os.getenv("PIXEL_JUDGE_OMLX_FULL_MAX_TOKENS", "1024"))
    omlx["post_commentary_max_tokens"] = int(
        os.getenv(
            "PIXEL_JUDGE_OMLX_POST_MAX_TOKENS", str(omlx.get("post_commentary_max_tokens", 160))
        )
    )
    requests = dict(omlx.get("requests", {}))
    requests["contract_mode"] = os.getenv(
        "PIXEL_JUDGE_OMLX_CONTRACT_MODE",
        requests.get("contract_mode", "structured_outputs"),
    )
    requests["prompt_preset"] = os.getenv(
        "PIXEL_JUDGE_OMLX_PROMPT_PRESET",
        requests.get("prompt_preset", "default"),
    )
    requests["enable_thinking"] = os.getenv(
        "PIXEL_JUDGE_OMLX_ENABLE_THINKING",
        str(requests.get("enable_thinking", "false")),
    ).strip().lower() in {"1", "true", "yes", "on"}
    omlx["requests"] = requests

    missing = [
        key
        for key in (
            "base_url",
            "fast_vision_model",
            "full_vision_model",
            "commentary_model",
            "timeout",
        )
        if not omlx.get(key)
    ]
    if missing:
        pytest.fail(f"Live OMLX config missing required keys: {missing}")

    headers = {}
    if omlx.get("api_key"):
        headers["Authorization"] = f"Bearer {omlx['api_key']}"

    try:
        response = httpx.get(
            f"{omlx['base_url'].rstrip('/')}/v1/models", headers=headers, timeout=10.0
        )
        response.raise_for_status()
    except Exception as error:
        pytest.fail(f"Live OMLX endpoint is not reachable: {error}")

    return omlx


def _sample_jpeg_bytes() -> bytes:
    fixture = Path(__file__).resolve().parent / "fixtures" / "omlx_live_sample.jpg"
    if not fixture.exists():
        pytest.fail(f"Live JPEG fixture is missing: {fixture}")
    image = cv2.imread(str(fixture))
    if image is None:
        pytest.fail(f"Live JPEG fixture is unreadable: {fixture}")
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > 1024:
        scale = 1024 / float(longest)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok is True
    return encoded.tobytes()


def test_omlx_live_fast_raw_response_is_strict_json_object():
    client = AsyncOMLXClient(_load_live_omlx_config())
    raw = asyncio.run(
        client._vision_raw(
            client.fast_vision_model,
            build_fast_prompt(structured_output=True),
            _sample_jpeg_bytes(),
            enable_thinking=False,
            max_tokens=client.fast_vision_max_tokens,
            response_mode="fast",
        )
    )

    stripped = raw.strip()
    assert stripped.startswith("{")
    assert stripped.endswith("}")
    data = extract_last_json_object(raw)
    assert set(data.keys()) == {
        "technical_ok",
        "subject_clear",
        "composition_ok",
        "usable_for_selection",
    }
    for key in data:
        assert isinstance(data[key], (int, float))
        assert 0.0 <= float(data[key]) <= 1.0


def test_omlx_live_full_raw_response_is_strict_json_object():
    client = AsyncOMLXClient(_load_live_omlx_config())
    raw = asyncio.run(
        client._vision_raw(
            client.full_vision_model,
            build_full_prompt(structured_output=True),
            _sample_jpeg_bytes(),
            enable_thinking=False,
            max_tokens=client.vision_max_tokens,
            response_mode="full",
        )
    )

    data = extract_last_json_object(raw)
    assert data["scene"] in SCENE_LIST
    assert isinstance(data["scene_raw"], str)
    assert data["scene_raw"].strip() != ""
    for dim in VISION_DIMS:
        assert isinstance(data[dim], (int, float))
        assert 0.0 <= float(data[dim]) <= 10.0


def test_omlx_live_fast_score_returns_signal_object():
    client = AsyncOMLXClient(_load_live_omlx_config())
    score = asyncio.run(client.score_image_fast(_sample_jpeg_bytes()))

    assert set(score.keys()) == {
        "technical_ok",
        "subject_clear",
        "composition_ok",
        "usable_for_selection",
    }
    for value in score.values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0


def test_omlx_live_full_score_returns_expected_schema():
    client = AsyncOMLXClient(_load_live_omlx_config())
    result = asyncio.run(client.score_image(_sample_jpeg_bytes()))

    assert result["scene"] in SCENE_LIST
    assert isinstance(result["scene_raw"], str)
    assert result["scene_raw"].strip() != ""
    for dim in VISION_DIMS:
        assert isinstance(result[dim], float)
        assert 0.0 <= result[dim] <= 10.0


def test_omlx_live_group_commentary_raw_response_is_strict_json_object():
    client = AsyncOMLXClient(_load_live_omlx_config())
    prompt = build_group_commentary_prompt(
        "1. a.jpg total=7.0\n2. b.jpg total=6.2\n3. c.jpg total=3.4"
    )
    raw = asyncio.run(
        client.generate_text(
            prompt,
            client.commentary_model,
            response_format=build_group_commentary_response_format(),
            max_tokens=client.group_commentary_max_tokens,
        )
    )

    data = extract_last_json_object(raw)
    assert isinstance(data["group_issues"], str)
    assert data["group_issues"].strip()
    assert data["group_issues"] != "string"
    assert isinstance(data["shooting"], str)
    assert data["shooting"].strip()
    assert data["shooting"] != "string"


def test_omlx_live_post_commentary_raw_response_is_strict_json_object():
    client = AsyncOMLXClient(_load_live_omlx_config())
    prompt = build_post_commentary_prompt(
        "exp:9.4 sharp:3.9 subj:8.5 comp:7.5 lit:7.0 color:6.0 clar:7.0 dep:7.5 mood:8.5",
        "【组内问题】整体偏暗。\n【拍摄建议】拍摄时补一点面光。",
    )
    raw = asyncio.run(
        client.generate_text(
            prompt,
            client.commentary_model,
            response_format=build_post_commentary_response_format(),
            max_tokens=client.post_commentary_max_tokens,
            temperature=0.0,
        )
    )

    data = extract_last_json_object(raw)
    assert isinstance(data["post"], str)
    assert data["post"].strip()
    assert data["post"] != "string"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in data["post"])
