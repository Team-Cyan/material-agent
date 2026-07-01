import asyncio
import json
import shutil
from pathlib import Path

from material_agent.app.omlx_benchmark_service import BenchmarkCandidate, OMLXBenchmarkService
from material_agent.clients.omlx import AsyncOMLXClient
from material_agent.clients.prompts import build_post_commentary_response_format


def _omlx_config(tmp_path: Path) -> dict:
    return {
        "backend": "omlx",
        "output_language": "zh",
        "log_level": "info",
        "omlx": {
            "base_url": "http://127.0.0.1:11435",
            "fast_vision_model": "gemma-4-26b-a4b-it-4bit",
            "full_vision_model": "gemma-4-26b-a4b-it-4bit",
            "commentary_model": "gemma-4-26b-a4b-it-4bit",
            "timeout": 30,
            "vision_temperature": 0.0,
            "commentary_temperature": 0.0,
            "vision_max_tokens": 192,
            "post_commentary_max_tokens": 160,
            "fast_vision_max_tokens": 96,
            "api_key": "secret",
            "cache_enabled": True,
            "instance_root": str(tmp_path / "instance"),
            "requests": {
                "contract_mode": "structured_outputs",
                "prompt_preset": "default",
                "enable_thinking": False,
            },
            "runtime": {
                "required_version": ">=0.3.0",
                "require_structured_outputs": True,
                "require_xgrammar": True,
                "probe_on_run": True,
                "enforce_dedicated_instance": True,
            },
        },
    }


def test_async_omlx_generate_text_uses_response_format_json_schema(monkeypatch):
    requests = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"parsed": {"post": "后期先提一点阴影，再轻压高光。"}}}]
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
            "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "full_vision_model": "Qwen3-VL-8B-Instruct-4bit",
            "commentary_model": "gemma-4-26b-a4b-it-4bit",
            "timeout": 30,
            "requests": {
                "contract_mode": "response_format_json_schema",
            },
        }
    )

    text = asyncio.run(
        client.generate_text(
            "Return structured post guidance.",
            client.commentary_model,
            response_format=build_post_commentary_response_format(
                contract_mode="response_format_json_schema"
            ),
        )
    )

    assert '"post"' in text
    assert "response_format" in requests[0]
    assert "structured_outputs" not in requests[0]
    assert requests[0]["response_format"]["type"] == "json_schema"


def test_omlx_benchmark_service_writes_single_fixture_summary(tmp_path, monkeypatch):
    fixture = Path(__file__).resolve().parent / "fixtures" / "omlx_live_sample.jpg"

    class _FakeClient:
        def __init__(self, config):
            self.fast_vision_model = config["fast_vision_model"]
            self.full_vision_model = config["full_vision_model"]
            self.commentary_model = config["commentary_model"]
            self.fast_vision_max_tokens = config["fast_vision_max_tokens"]
            self.vision_max_tokens = config["vision_max_tokens"]
            self.post_commentary_max_tokens = config["post_commentary_max_tokens"]
            self.commentary_temperature = config["commentary_temperature"]
            self.contract_mode = config["requests"]["contract_mode"]
            self.prompt_preset = config["requests"]["prompt_preset"]
            self.structured_enable_thinking = config["requests"]["enable_thinking"]
            self.output_language = config.get("output_language", "zh")
            self.post_commentary_schema_name = "material_agent.post_commentary"

        async def _vision_raw(
            self,
            model,
            prompt,
            jpeg_bytes,
            enable_thinking,
            max_tokens,
            response_mode="full",
        ):
            if response_mode == "fast":
                return (
                    '{"technical_ok": 0.7, "subject_clear": 0.8, '
                    '"composition_ok": 0.6, "usable_for_selection": 0.7}'
                )
            return (
                '{"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
                '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
            )

        async def generate_text(
            self, prompt, model, response_format=None, max_tokens=None, temperature=None
        ):
            return '{"post":"后期先提一点阴影，再轻压高光。"}'

    monkeypatch.setattr(
        "material_agent.app.omlx_benchmark_service.OMLXInstanceService.status",
        lambda self, config: {
            "reachable": True,
            "base_url": "http://127.0.0.1:11435",
            "error": None,
            "version": "0.3.2",
            "xgrammar": False,
            "structured_outputs": False,
        },
    )
    service = OMLXBenchmarkService(client_cls=_FakeClient)

    summary = service.run(
        _omlx_config(tmp_path),
        models=["gemma-4-26b-a4b-it-4bit"],
        mode="single_fixture",
        repeat_count=2,
        sample_set=[str(fixture)],
        result_path=str(tmp_path / "results"),
        contract_modes=["response_format_json_schema"],
        prompt_presets=["gemma"],
    )

    summary_path = Path(summary["run_dir"]) / "summary.json"
    attempts_path = Path(summary["attempts_path"])
    best_path = Path(summary["result_root"]) / "best_candidates.json"

    assert summary["best_by_model"]["gemma-4-26b-a4b-it-4bit"]["candidate"]["contract_mode"] == (
        "response_format_json_schema"
    )
    assert summary_path.exists()
    assert attempts_path.exists()
    assert best_path.exists()
    loaded_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert loaded_summary["results"][0]["overall_schema_success_rate"] == 1.0
    assert loaded_summary["runtime_contract_support"]["server_version"] == "0.3.2"
    assert loaded_summary["results"][0]["contract_execution"]["requested_contract_mode"] == (
        "response_format_json_schema"
    )
    assert loaded_summary["results"][0]["contract_execution"]["effective_constraint_path"] == (
        "prompt_injection_and_post_parse"
    )


def test_omlx_benchmark_service_limits_kv_batch_to_first_ten_images(tmp_path, monkeypatch):
    fixture = Path(__file__).resolve().parent / "fixtures" / "omlx_live_sample.jpg"
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    for index in range(12):
        shutil.copyfile(fixture, sample_dir / f"sample-{index}.jpg")

    class _FakeClient:
        def __init__(self, config):
            self.fast_vision_model = config["fast_vision_model"]
            self.full_vision_model = config["full_vision_model"]
            self.commentary_model = config["commentary_model"]
            self.fast_vision_max_tokens = config["fast_vision_max_tokens"]
            self.vision_max_tokens = config["vision_max_tokens"]
            self.post_commentary_max_tokens = config["post_commentary_max_tokens"]
            self.commentary_temperature = config["commentary_temperature"]
            self.contract_mode = config["requests"]["contract_mode"]
            self.prompt_preset = config["requests"]["prompt_preset"]
            self.structured_enable_thinking = config["requests"]["enable_thinking"]
            self.output_language = config.get("output_language", "zh")
            self.post_commentary_schema_name = "material_agent.post_commentary"

        async def _vision_raw(
            self,
            model,
            prompt,
            jpeg_bytes,
            enable_thinking,
            max_tokens,
            response_mode="full",
        ):
            return (
                '{"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
                '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
            )

        async def generate_text(
            self, prompt, model, response_format=None, max_tokens=None, temperature=None
        ):
            return '{"post":"后期先提一点阴影，再轻压高光。"}'

    monkeypatch.setattr(
        "material_agent.app.omlx_benchmark_service.OMLXInstanceService.status",
        lambda self, config: {
            "reachable": True,
            "base_url": "http://127.0.0.1:11435",
            "error": None,
            "version": "0.3.2",
            "xgrammar": False,
            "structured_outputs": False,
        },
    )
    service = OMLXBenchmarkService(client_cls=_FakeClient)

    summary = service.run(
        _omlx_config(tmp_path),
        models=["Qwen3-VL-8B-Instruct-4bit"],
        mode="kv_cache_batch",
        repeat_count=1,
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
    )

    assert summary["results"][0]["sample_count"] == 10
    assert summary["results"][0]["contract_execution"]["requested_contract_mode"] == (
        "structured_outputs"
    )
    assert summary["results"][0]["contract_execution"]["effective_constraint_path"] == (
        "not_available"
    )


def test_omlx_benchmark_candidate_config_syncs_grouped_admin_models(tmp_path):
    service = OMLXBenchmarkService()
    config = _omlx_config(tmp_path)
    config["omlx"]["admin"] = {
        "full_vision_model": "stale-full",
        "commentary_model": "stale-commentary",
        "fast_vision_model": "stale-fast",
    }
    config["full_vision_model"] = "root-stale-full"
    config["commentary_model"] = "root-stale-commentary"
    config["fast_vision_model"] = "root-stale-fast"

    candidate = service._build_candidate_config(
        config,
        "Qwen3-VL-8B-Instruct-4bit",
        BenchmarkCandidate(
            contract_mode="response_format_json_schema",
            prompt_preset="qwen3",
            vision_temperature=0.0,
            commentary_temperature=0.0,
            vision_max_tokens=192,
            post_commentary_max_tokens=160,
            enable_thinking=False,
            image_max_edge=1024,
            vision_jpeg_quality=92,
        ),
    )

    assert candidate["full_vision_model"] == "Qwen3-VL-8B-Instruct-4bit"
    assert candidate["commentary_model"] == "Qwen3-VL-8B-Instruct-4bit"
    assert candidate["fast_vision_model"] == "Qwen3-VL-8B-Instruct-4bit"
    assert candidate["admin"]["full_vision_model"] == "Qwen3-VL-8B-Instruct-4bit"
    assert candidate["admin"]["commentary_model"] == "Qwen3-VL-8B-Instruct-4bit"
    assert candidate["admin"]["fast_vision_model"] == "Qwen3-VL-8B-Instruct-4bit"
