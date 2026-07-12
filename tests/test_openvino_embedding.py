import asyncio
from io import BytesIO

from PIL import Image

from material_agent.adapters.models.openvino_embedding import OpenVinoEmbeddingAdapter


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (10, 20, 30)).save(output, format="JPEG")
    return output.getvalue()


class _FakeOpenVinoRuntime:
    execution_devices = ["CPU"]

    def embed(self, image):
        assert image.mode == "RGB"
        return [0.25, 0.5, 0.75]


def test_openvino_embedding_reports_actual_execution_device():
    adapter = OpenVinoEmbeddingAdapter(
        {
            "model_path": "/models/model.onnx",
            "processor_path": "/models/processor",
            "device": "AUTO:GPU,CPU",
        },
        runtime=_FakeOpenVinoRuntime(),
    )

    result = asyncio.run(adapter.embed_image(_jpeg_bytes()))

    assert result["vector"] == [0.25, 0.5, 0.75]
    assert result["runtime"] == "openvino"
    assert result["device"] == "AUTO:GPU,CPU"
    assert result["execution_devices"] == ["CPU"]
