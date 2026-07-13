from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..adapters.models.openvino_embedding import (
    _model_bundle_assets,
    _model_bundle_digest,
    _onnx_external_data_locations,
)


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
    for relative_path in _onnx_external_data_locations(model_path):
        external_data = model_path.parent / relative_path
        if not external_data.is_file():
            raise ValueError(f"ONNX external data file does not exist: {external_data}")
        destination_data = onnx_dir / relative_path
        destination_data.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(external_data.resolve(), destination_data)
    shutil.copy2(preprocessor.resolve(), destination / "preprocessor_config.json")
    bundle_assets = _model_bundle_assets(destination_model, destination)
    manifest = {
        "schema_version": "material-agent.openvino-model-bundle.v2",
        "model_path": str(destination_model.relative_to(destination)),
        "processor_path": ".",
        "model_digest": _model_bundle_digest(destination_model, destination),
        "assets": [name for name, _ in bundle_assets],
    }
    manifest_path = destination / "bundle.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "bundle_path": str(destination), "manifest_path": str(manifest_path)}
