from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..adapters.models.openvino_embedding import _model_bundle_digest


def materialize_openvino_bundle(
    source_model: str | Path,
    source_processor: str | Path,
    output_dir: str | Path,
) -> dict:
    model_path = Path(source_model).expanduser().absolute()
    processor_path = Path(source_processor).resolve()
    destination = Path(output_dir).resolve()
    if not model_path.is_file():
        raise ValueError(f"source model does not exist: {model_path}")
    preprocessor = (
        processor_path / "preprocessor_config.json"
        if processor_path.is_dir()
        else processor_path
    )
    if not preprocessor.is_file():
        raise ValueError(f"preprocessor_config.json does not exist: {preprocessor}")
    onnx_dir = destination / "onnx"
    onnx_dir.mkdir(parents=True, exist_ok=True)
    destination_model = onnx_dir / model_path.name
    shutil.copy2(model_path.resolve(), destination_model)
    external_data = model_path.with_name(f"{model_path.name}_data")
    if external_data.exists():
        shutil.copy2(external_data.resolve(), onnx_dir / external_data.name)
    shutil.copy2(preprocessor.resolve(), destination / "preprocessor_config.json")
    manifest = {
        "schema_version": "material-agent.openvino-model-bundle.v1",
        "model_path": str(destination_model.relative_to(destination)),
        "processor_path": ".",
        "model_digest": _model_bundle_digest(destination_model),
    }
    manifest_path = destination / "bundle.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "bundle_path": str(destination), "manifest_path": str(manifest_path)}
