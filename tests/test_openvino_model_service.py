import json

import numpy as np
import pytest

from material_agent.app.local_embedding_identity import build_local_embedding_cache_key
from material_agent.app.openvino_model_service import materialize_openvino_bundle
from material_agent.commands.scoring import build_score_cache_key
from material_agent.shells.cli.main import build_parser


def _write_external_onnx(path):
    onnx = pytest.importorskip("onnx")
    from onnx import helper, numpy_helper

    first = numpy_helper.from_array(np.array([1.0, 2.0], dtype=np.float32), name="weight_a")
    second = numpy_helper.from_array(np.array([3.0, 4.0], dtype=np.float32), name="weight_b")
    graph = helper.make_graph([], "external-data-fixture", [], [], [first, second])
    model = helper.make_model(graph)
    onnx.save_model(
        model,
        path,
        save_as_external_data=True,
        all_tensors_to_one_file=False,
        size_threshold=0,
    )


def _openvino_config(source):
    return {
        "backend": "local",
        "inference": {"model_cache_dir": "~/.material-agent/models"},
        "local": {
            "embedding": {
                "enabled": True,
                "runtime": "openvino",
                "model_name": "fixture-dinov3",
                "model_path": str(source / "model.onnx"),
                "processor_path": str(source),
                "device": "CPU",
                "compiled_cache_dir": "~/.material-agent/openvino-cache",
                "result_cache_size": 256,
            }
        },
    }


def test_embedding_cache_key_tracks_model_processor_and_runtime_settings(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_external_onnx(source / "model.onnx")
    processor = source / "preprocessor_config.json"
    processor.write_text('{"size": 224}', encoding="utf-8")
    config = _openvino_config(source)

    baseline = build_local_embedding_cache_key(config)
    (source / "weight_a").write_bytes(b"replacement-weights")
    changed_model = build_local_embedding_cache_key(config)
    processor.write_text('{"size": 384}', encoding="utf-8")
    changed_processor = build_local_embedding_cache_key(config)
    config["local"]["embedding"]["device"] = "GPU"
    changed_device = build_local_embedding_cache_key(config)

    assert len({baseline, changed_model, changed_processor, changed_device}) == 4


def test_embedding_cache_key_tracks_raw_preview_inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_external_onnx(source / "model.onnx")
    (source / "preprocessor_config.json").write_text('{"size": 224}', encoding="utf-8")
    config = _openvino_config(source)
    config["preview"] = {"prefer_embedded": True, "max_size": 1024, "jpeg_quality": 85}

    baseline = build_local_embedding_cache_key(config)
    config["preview"]["max_size"] = 768

    assert build_local_embedding_cache_key(config) != baseline


def test_score_cache_key_tracks_openvino_bundle_content(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_external_onnx(source / "model.onnx")
    (source / "preprocessor_config.json").write_text('{"size": 224}', encoding="utf-8")
    config = _openvino_config(source)

    baseline = build_score_cache_key(config)
    (source / "weight_b").write_bytes(b"replacement-weights")

    assert build_score_cache_key(config) != baseline


def test_materialize_openvino_bundle_dereferences_external_data(tmp_path):
    source = tmp_path / "source"
    blobs = tmp_path / "blobs"
    source.mkdir()
    blobs.mkdir()
    _write_external_onnx(blobs / "model.onnx")
    for name in ("model.onnx", "weight_a", "weight_b"):
        (source / name).symlink_to(blobs / name)
    (source / "preprocessor_config.json").write_text("{}", encoding="utf-8")

    result = materialize_openvino_bundle(
        source / "model.onnx",
        source,
        tmp_path / "bundle",
    )

    model = tmp_path / "bundle" / "onnx" / "model.onnx"
    first_data = tmp_path / "bundle" / "onnx" / "weight_a"
    second_data = tmp_path / "bundle" / "onnx" / "weight_b"
    assert model.read_bytes() == (blobs / "model.onnx").read_bytes()
    assert first_data.read_bytes() == (blobs / "weight_a").read_bytes()
    assert second_data.read_bytes() == (blobs / "weight_b").read_bytes()
    assert not model.is_symlink()
    assert not first_data.is_symlink()
    assert not second_data.is_symlink()
    manifest = json.loads((tmp_path / "bundle" / "bundle.json").read_text())
    assert manifest["model_digest"] == result["model_digest"]
    assert manifest["schema_version"] == "material-agent.openvino-model-bundle.v2"
    assert manifest["assets"] == [
        "external/weight_a",
        "external/weight_b",
        "model/model.onnx",
        "processor/preprocessor_config.json",
    ]


def test_materialize_openvino_bundle_digest_includes_processor(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_external_onnx(source / "model.onnx")
    processor = source / "preprocessor_config.json"
    processor.write_text('{"size": 224}', encoding="utf-8")
    first = materialize_openvino_bundle(
        source / "model.onnx",
        source,
        tmp_path / "bundle-a",
    )

    processor.write_text('{"size": 384}', encoding="utf-8")
    second = materialize_openvino_bundle(
        source / "model.onnx",
        source,
        tmp_path / "bundle-b",
    )

    assert first["model_digest"] != second["model_digest"]


def test_materialize_openvino_bundle_rejects_parent_external_path(tmp_path):
    onnx = pytest.importorskip("onnx")
    source = tmp_path / "source"
    source.mkdir()
    model_path = source / "model.onnx"
    _write_external_onnx(model_path)
    model = onnx.load_model(str(model_path), load_external_data=False)
    for entry in model.graph.initializer[0].external_data:
        if entry.key == "location":
            entry.value = "../escape.bin"
    onnx.save_model(model, str(model_path))
    (source / "preprocessor_config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe ONNX external data location"):
        materialize_openvino_bundle(
            model_path,
            source,
            tmp_path / "bundle",
        )


def test_cli_exposes_prepare_openvino_model_command():
    args = build_parser().parse_args(
        [
            "prepare-openvino-model",
            "--source-model",
            "model.onnx",
            "--source-processor",
            "processor",
            "--output-dir",
            "bundle",
        ]
    )

    assert args.command == "prepare-openvino-model"
