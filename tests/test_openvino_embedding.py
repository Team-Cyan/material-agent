import asyncio
import json
import sys
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from material_agent.adapters.models.openvino_embedding import (
    OpenVinoEmbeddingAdapter,
    _NumpyImageProcessor,
    _OpenVinoRuntime,
    _read_execution_devices,
)


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (10, 20, 30)).save(output, format="JPEG")
    return output.getvalue()


class _FakeOpenVinoRuntime:
    execution_devices = ["CPU"]

    def embed(self, image):
        assert image.mode == "RGB"
        return [0.25, 0.5, 0.75]


class _FallbackOpenVinoRuntime(_FakeOpenVinoRuntime):
    requested_device = "AUTO:GPU,CPU"
    compiled_device = "CPU"
    fallback_device = "CPU"
    fallback_used = True
    fallback_reason = 'RuntimeError: Device with "GPU" name is not registered'


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
    assert result["requested_device"] == "AUTO:GPU,CPU"
    assert result["compiled_device"] == "AUTO:GPU,CPU"
    assert result["fallback_device"] == "CPU"
    assert result["fallback_used"] is False
    assert result["fallback_reason"] is None
    assert result["execution_devices"] == ["CPU"]
    assert result["execution_device_readback"] == "actual"


def test_openvino_embedding_reports_compile_fallback_provenance():
    adapter = OpenVinoEmbeddingAdapter(
        {
            "model_path": "/models/model.onnx",
            "processor_path": "/models/processor",
            "device": "AUTO:GPU,CPU",
            "fallback_device": "CPU",
        },
        runtime=_FallbackOpenVinoRuntime(),
    )

    result = asyncio.run(adapter.embed_image(_jpeg_bytes()))

    assert result["requested_device"] == "AUTO:GPU,CPU"
    assert result["compiled_device"] == "CPU"
    assert result["fallback_device"] == "CPU"
    assert result["fallback_used"] is True
    assert 'Device with "GPU" name is not registered' in result["fallback_reason"]
    assert result["execution_devices"] == ["CPU"]


def test_openvino_runtime_falls_back_when_requested_gpu_is_unavailable(
    monkeypatch,
    tmp_path,
):
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"fixture")
    (tmp_path / "preprocessor_config.json").write_text(
        json.dumps({"size": {"height": 2, "width": 2}}),
        encoding="utf-8",
    )
    compile_calls = []

    class _Compiled:
        def get_property(self, _name):
            return ["CPU"]

    class _Core:
        available_devices = ["CPU"]

        def read_model(self, path):
            return path

        def compile_model(self, model, device, config):
            compile_calls.append((model, device, config))
            if device == "AUTO:GPU,CPU":
                raise RuntimeError('Device with "GPU" name is not registered')
            return _Compiled()

    monkeypatch.setitem(
        sys.modules,
        "openvino",
        SimpleNamespace(__version__="fixture-openvino", Core=_Core),
    )

    runtime = _OpenVinoRuntime(
        model_path=str(model_path),
        processor_path=str(tmp_path),
        device="AUTO:GPU,CPU",
        fallback_device="CPU",
        compiled_cache_dir=str(tmp_path / "cache"),
    )

    assert [call[1] for call in compile_calls] == ["AUTO:GPU,CPU", "CPU"]
    assert runtime.requested_device == "AUTO:GPU,CPU"
    assert runtime.compiled_device == "CPU"
    assert runtime.fallback_device == "CPU"
    assert runtime.fallback_used is True
    assert 'Device with "GPU" name is not registered' in runtime.fallback_reason
    assert runtime.execution_devices == ["CPU"]


def test_openvino_runtime_real_cpu_fallback(tmp_path):
    onnx = pytest.importorskip("onnx")
    ov = pytest.importorskip("openvino")
    if any(str(device).upper().startswith("GPU") for device in ov.Core().available_devices):
        pytest.skip("real fallback contract requires a CPU-only OpenVINO host")
    from onnx import TensorProto, helper

    model_path = tmp_path / "identity.onnx"
    tensor_in = helper.make_tensor_value_info(
        "pixel_values", TensorProto.FLOAT, [1, 3, 2, 2]
    )
    tensor_out = helper.make_tensor_value_info(
        "embedding", TensorProto.FLOAT, [1, 3, 2, 2]
    )
    graph = helper.make_graph(
        [helper.make_node("Identity", ["pixel_values"], ["embedding"])],
        "identity-embedding",
        [tensor_in],
        [tensor_out],
    )
    onnx.save_model(
        helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)]),
        model_path,
    )
    (tmp_path / "preprocessor_config.json").write_text(
        json.dumps(
            {
                "do_resize": True,
                "size": {"height": 2, "width": 2},
                "do_rescale": True,
                "do_normalize": False,
                "data_format": "channels_first",
            }
        ),
        encoding="utf-8",
    )

    runtime = _OpenVinoRuntime(
        model_path=str(model_path),
        processor_path=str(tmp_path),
        device="AUTO:GPU,CPU",
        fallback_device="CPU",
        compiled_cache_dir=str(tmp_path / "cache"),
    )
    vector = runtime.embed(Image.new("RGB", (2, 2), (10, 20, 30)))

    assert len(vector) == 12
    assert runtime.fallback_used is True
    assert runtime.compiled_device == "CPU"
    assert runtime.execution_devices == ["CPU"]


def test_openvino_execution_device_readback_failure_is_unknown():
    class _UnreadableCompiledModel:
        def get_property(self, _name):
            raise RuntimeError("property unsupported")

    devices, error = _read_execution_devices(_UnreadableCompiledModel())

    assert devices == ["unknown"]
    assert error == "RuntimeError: property unsupported"


def test_openvino_empty_execution_device_readback_is_unknown():
    class _EmptyCompiledModel:
        def get_property(self, _name):
            return []

    devices, error = _read_execution_devices(_EmptyCompiledModel())

    assert devices == ["unknown"]
    assert error == "EXECUTION_DEVICES returned no devices"


def test_openvino_numpy_preprocessor_does_not_require_torch(tmp_path):
    config = {
        "do_resize": True,
        "size": {"height": 2, "width": 4},
        "resample": 2,
        "do_rescale": True,
        "rescale_factor": 0.1,
        "do_normalize": True,
        "image_mean": [1.0, 2.0, 3.0],
        "image_std": [1.0, 1.0, 1.0],
        "data_format": "channels_first",
    }
    (tmp_path / "preprocessor_config.json").write_text(
        json.dumps(config),
        encoding="utf-8",
    )
    processor = _NumpyImageProcessor(tmp_path, np)

    result = processor(Image.new("RGB", (1, 1), (10, 20, 30)))

    assert result.shape == (1, 3, 2, 4)
    assert result.dtype == np.float32
    assert np.allclose(result, 0.0)
