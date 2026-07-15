import asyncio
from io import BytesIO

import numpy as np
from PIL import Image

from material_agent.adapters.models.openvino_ssd_detection import (
    OpenVinoSsdObjectDetectorAdapter,
)
from material_agent.clients.local import AsyncLocalClient


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 48), (80, 120, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


class _FakeRuntime:
    requested_device = "GPU"
    compiled_device = "CPU"
    fallback_used = True
    fallback_reason = "GPU unavailable"
    execution_devices = ["CPU"]
    openvino_version = "fixture"

    def detect(self, rgb: np.ndarray):
        assert rgb.shape == (48, 64, 3)
        return [
            {"class_id": 18, "confidence": 0.92, "bbox": [0.2, 0.1, 0.8, 0.9]},
            {"class_id": 3, "confidence": 0.10, "bbox": [0.0, 0.0, 0.2, 0.2]},
        ], {"compile_seconds": 0.2, "preprocess_seconds": 0.01, "inference_seconds": 0.03}


def test_openvino_ssd_adapter_filters_labels_and_records_provenance():
    adapter = OpenVinoSsdObjectDetectorAdapter(
        {
            "model_path": "/missing/fixture.onnx",
            "device": "GPU",
            "fallback_device": "CPU",
            "score_threshold": 0.3,
        },
        runtime=_FakeRuntime(),
    )

    result = asyncio.run(adapter.detect_objects(_jpeg_bytes()))

    assert [item["label"] for item in result["objects"]] == ["dog"]
    assert result["primary_subject"]["label"] == "dog"
    assert result["scene"] == "animals"
    assert result["compiled_device"] == "CPU"
    assert result["fallback_used"] is True
    assert result["execution_devices"] == ["CPU"]
    assert result["inference_run_id"]


class _FakeDetectionAdapter:
    async def detect_objects(self, jpeg_bytes):
        assert jpeg_bytes
        return {
            "model_name": "fixture-ssd",
            "runtime": "openvino",
            "device": "CPU",
            "execution_devices": ["CPU"],
            "scene": "animals",
            "objects": [],
            "faces": [],
        }


def test_local_client_composes_detection_with_heuristic_scores():
    client = AsyncLocalClient({"detection": {"enabled": True}})
    client._detection = _FakeDetectionAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["scene"] == "animals"
    assert result["_scoring_mode"] == "hybrid"
    assert result["_model_stack"] == ["fixture-ssd"]
    assert result["_runtime"] == "cpu+openvino:CPU"
    assert result["_detection"]["status"] == "model"
