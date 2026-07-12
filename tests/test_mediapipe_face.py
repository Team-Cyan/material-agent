import asyncio
from io import BytesIO

from PIL import Image

from material_agent.adapters.models.mediapipe_face import MediaPipeFaceAdapter
from material_agent.clients.local import AsyncLocalClient


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (100, 100, 100)).save(output, format="JPEG")
    return output.getvalue()


class _FakeFaceRuntime:
    def detect(self, image):
        assert image.mode == "RGB"
        return [[(0.2, 0.1), (0.6, 0.1), (0.6, 0.7), (0.2, 0.7)]]


def test_face_adapter_reports_presence_count_and_area():
    adapter = MediaPipeFaceAdapter(runtime=_FakeFaceRuntime())

    result = asyncio.run(adapter.detect_faces(_jpeg_bytes()))

    assert result["face_present"] is True
    assert result["face_count"] == 1
    assert result["max_face_area_ratio"] == 0.24
    assert result["landmark_counts"] == [4]


class _FakeFaceAdapter:
    async def detect_faces(self, jpeg_bytes):
        return {
            "face_present": True,
            "face_count": 1,
            "max_face_area_ratio": 0.2,
            "landmark_counts": [478],
            "model_name": "fixture-face",
            "model_version": "fixture-v1",
            "runtime": "fixture-face-runtime",
            "device": "cpu",
        }


def test_local_client_adds_face_signal_without_enabling_portrait_penalty():
    client = AsyncLocalClient({"face": {"enabled": True}})
    client._face = _FakeFaceAdapter()

    result = asyncio.run(client.score_image(_jpeg_bytes()))

    assert result["_face"]["status"] == "model"
    assert result["_face"]["face_present"] is True
    assert result["_runtime"] == "cpu+fixture-face-runtime:cpu"
