import json

from material_agent.app.openvino_model_service import materialize_openvino_bundle
from material_agent.shells.cli.main import build_parser


def test_materialize_openvino_bundle_dereferences_external_data(tmp_path):
    source = tmp_path / "source"
    blobs = tmp_path / "blobs"
    source.mkdir()
    blobs.mkdir()
    (blobs / "model-bytes").write_bytes(b"onnx")
    (blobs / "data-bytes").write_bytes(b"weights")
    (source / "model.onnx").symlink_to(blobs / "model-bytes")
    (source / "model.onnx_data").symlink_to(blobs / "data-bytes")
    (source / "preprocessor_config.json").write_text("{}", encoding="utf-8")

    result = materialize_openvino_bundle(
        source / "model.onnx",
        source,
        tmp_path / "bundle",
    )

    model = tmp_path / "bundle" / "onnx" / "model.onnx"
    data = tmp_path / "bundle" / "onnx" / "model.onnx_data"
    assert model.read_bytes() == b"onnx"
    assert data.read_bytes() == b"weights"
    assert not model.is_symlink()
    manifest = json.loads((tmp_path / "bundle" / "bundle.json").read_text())
    assert manifest["model_digest"] == result["model_digest"]


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
