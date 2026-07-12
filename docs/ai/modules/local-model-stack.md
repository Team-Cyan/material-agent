# Local Model Stack Contract

## Purpose

This module owns optional learned signals used by the local backend. Every block
loads lazily and must preserve the service-free heuristic fallback.

## Main Files

- `src/material_agent/clients/local.py`
- `src/material_agent/adapters/models/openclip_semantic.py`
- `src/material_agent/adapters/models/pyiqa_quality.py`
- `src/material_agent/adapters/models/dinov2_embedding.py`
- `src/material_agent/adapters/models/openvino_embedding.py`
- `src/material_agent/adapters/models/mediapipe_face.py`
- `src/material_agent/app/openvino_model_service.py`

## Model Blocks

- semantic: MobileCLIP2-S0 through OpenCLIP;
- reject priors: BRISQUE and NIQE through PyIQA;
- quality: MUSIQ through PyIQA;
- aesthetic: NIMA and CLIPIQA+ through PyIQA;
- embeddings: DINOv2-small through Transformers or a native OpenVINO ONNX
  adapter;
- face structure: MediaPipe Face Landmarker.

## Invariants

- Optional packages are not imported when their block is disabled.
- Missing packages or weights produce explicit fallback metadata unless the
  block's `enforce_available` flag is true.
- Configured runtime and actual runtime are different provenance fields.
- Model signals do not alter the default total-score policy without a versioned
  calibration and promotion report.
- Reject priors, quality scores, and aesthetic scores remain separate roles.
- Non-photo detection must not depend only on IQA/aesthetic output.
- Embedding vectors are used transiently and are not written into benchmark
  reports or ordinary score metadata.
- Face presence does not enable portrait penalties by itself.

## OpenVINO Model Bundles

ONNX external-data files must be materialized next to the `.onnx` file. A Hugging
Face snapshot may use symlinks that resolve outside the model directory, which
OpenVINO rejects. Use:

```bash
uv run material-agent prepare-openvino-model \
  --source-model /path/to/model.onnx \
  --source-processor /path/to/processor-directory \
  --output-dir ~/.material-agent/models/model-name
```

The generated `bundle.json` records a digest covering the ONNX graph and its
external data. OpenVINO cache identity also includes the requested device and
OpenVINO version.

## Verified Limitations

- The DINOv3 MHA Q4 export uses `com.microsoft.MultiHeadAttention`, which native
  OpenVINO 2026.2.1 does not convert.
- The standard-operator DINOv3 ViT-S quantized export compiles and runs through
  native OpenVINO on CPU.
- PyIQA CLIPIQA+ still imports `pkg_resources` through `openai-clip`, so the
  `quality-models` extra pins setuptools below 81.
- The maintained UI fixture receives high MUSIQ and CLIPIQA+ scores. Semantic
  screenshot classification must remain an independent non-photo signal.

## Minimal Verification

```bash
uv run pytest \
  tests/test_openclip_semantic.py \
  tests/test_pyiqa_quality.py \
  tests/test_dinov2_embedding.py \
  tests/test_openvino_embedding.py \
  tests/test_mediapipe_face.py \
  tests/test_openvino_model_service.py
```
