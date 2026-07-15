from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from material_agent.adapters.models.openvino_nima_aesthetic import (
    OpenVinoNimaAestheticAdapter,
)
from material_agent.clients.local import AsyncLocalClient
from material_agent.domain.layered_decision import summarize_signals


def _jpeg(color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), color).save(output, format="JPEG")
    return output.getvalue()


class _FakeRuntime:
    requested_device = "GPU"
    compiled_device = "GPU"
    fallback_device = "CPU"
    fallback_used = False
    fallback_reason = None
    execution_devices = ["GPU.0"]
    execution_device_readback_error = None
    openvino_version = "fixture"
    performance_hint = "THROUGHPUT"
    batch_size = 4
    infer_requests = 2
    optimal_infer_requests = 2
    last_run_timing = {"inference_seconds": 0.01, "image_count": 1}

    def score_many(self, images):
        distribution = [0.0] * 10
        distribution[6] = 1.0
        return [(7.0, distribution) for _ in images]


def test_nima_adapter_returns_learned_distribution_with_actual_device():
    adapter = OpenVinoNimaAestheticAdapter(
        {"model_path": "/fixture/nima.tflite", "device": "GPU", "batch_size": 4},
        runtime=_FakeRuntime(),
    )

    result = asyncio.run(adapter.score_image(_jpeg()))

    assert result["score"] == 7.0
    assert result["distribution"][6] == 1.0
    assert result["execution_devices"] == ["GPU.0"]
    assert result["requested_device"] == "GPU"
    assert result["batch_size_actual"] == 4


def test_local_client_batches_and_caches_aesthetic_predictions():
    class Scorer:
        calls = 0

        async def score_images(self, payloads):
            self.calls += 1
            return [
                {
                    "score": 6.25,
                    "distribution": [0.1] * 10,
                    "model_name": "fixture-nima",
                    "runtime": "openvino",
                    "execution_devices": ["CPU"],
                }
                for _ in payloads
            ]

    client = AsyncLocalClient({"aesthetic": {"enabled": True, "result_cache_size": 8}})
    client._aesthetic = Scorer()
    first = asyncio.run(client.score_aesthetics([_jpeg("red"), _jpeg("red"), _jpeg("blue")]))
    second = asyncio.run(client.score_image(_jpeg("red")))

    assert client._aesthetic.calls == 1
    assert [row["score"] for row in first] == [6.25, 6.25, 6.25]
    assert second["aesthetic_score"] == 6.25
    assert second["_aesthetic"]["status"] == "model"


def test_learned_aesthetic_score_owns_aesthetic_total():
    signals = [
        {"stage": "technical", "signal_key": "technical_quality", "value": 8.0},
        {"stage": "aggregate", "signal_key": "subject_focus", "value": 8.0},
        {"stage": "screening", "signal_key": "screening_prior", "value": 8.0},
        {"stage": "aesthetic", "signal_key": "composition", "value": 2.0},
        {"stage": "aesthetic", "signal_key": "lighting", "value": 2.0},
        {"stage": "aesthetic", "signal_key": "overall_aesthetic", "value": 7.0},
    ]
    config = {
        "screening_policy": {"weight": 0.10},
        "decision_policy": {
            "keep_threshold": 7.5,
            "review_threshold": 5.5,
            "hard_reject": {},
        },
    }

    summary = summarize_signals(signals, scene="other", config=config)

    assert summary.visible_breakdown["aesthetic_model_score"] == 7.0
    assert summary.total_score == 7.5
