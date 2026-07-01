# Inference Runtime Design

This document defines the runtime strategy for `material-agent`.

## Goal

Run photo culling on NAS-class hardware without requiring a local HTTP VLM service.

The first target is Intel integrated GPU hardware such as i7-11700T-class systems. The implementation should still run on CPU-only hosts.

## Non-Goals

- Do not make Ollama, OMLX, or another OpenAI-compatible service part of the default path.
- Do not build one Docker image with every vendor runtime installed.
- Do not assume Apple Metal GPU passthrough inside normal Linux containers.
- Do not train or fine-tune a full vision backbone before local labels exist.

## Runtime Abstraction

The application should talk to one local inference interface:

```python
class VisionRuntime:
    def available_devices(self) -> list[str]: ...
    def embed_batch(self, images) -> EmbeddingBatch: ...
    def score_quality_batch(self, images) -> QualityBatch: ...
    def classify_batch(self, images) -> ClassificationBatch: ...
```

Adapters own vendor-specific setup. The review pipeline should not import OpenVINO, CUDA, MIGraphX, CoreML, or MLX directly.

## Provider Priority

1. `cpu`
   - Universal fallback.
   - Use plain `onnxruntime` or deterministic heuristics.
   - Must always remain runnable.

2. `intel-openvino`
   - First accelerated implementation.
   - Target Intel CPU, integrated GPU, discrete GPU, and NPU through OpenVINO.
   - Use native OpenVINO on Python 3.14; `onnxruntime-openvino` does not yet publish `cp314` wheels.
   - Default device: `AUTO:GPU,CPU`.
   - Docker should mount `/dev/dri` on Linux hosts.

3. `nvidia-cuda`
   - Later accelerated tag.
   - Use ONNX Runtime CUDA first; TensorRT only after models and shapes stabilize.

4. `amd-migraphx`
   - Later experimental tag.
   - AMD coverage depends heavily on ROCm and MIGraphX host support.

5. `apple-native`
   - Native install, not normal Docker GPU.
   - Use CoreML, MLX, or PyTorch MPS.
   - A host-side service bridge is acceptable if Docker Model Runner is useful.

## Docker Tag Model

Use one source tree and multiple build targets:

```text
material-agent:cpu
material-agent:intel-openvino
material-agent:nvidia-cuda
material-agent:amd-migraphx
```

All Docker targets should start from the shared Python 3.14 + uv base image:

```text
ghcr.io/astral-sh/uv:python3.14-trixie
```

The `apple-native` profile should be documented as a local install first. A Docker image on Apple can still run CPU mode or call a host service, but it should not pretend to own Metal directly.

## Current Runtime Package Findings

Python 3.14 smoke tests on Apple M4:

- `openvino` 2026.2.1 installs and imports cleanly; the local device list is
  `CPU` because this is not an Intel GPU host.
- `onnxruntime` 1.27 installs and exposes `CoreMLExecutionProvider`,
  `AzureExecutionProvider`, and `CPUExecutionProvider` on Apple.
- `onnxruntime-openvino` is not installable on Python 3.14 because current
  wheels stop at `cp313`.

The Intel image should therefore use native OpenVINO APIs directly. Plain ONNX
Runtime remains useful for CPU fallback and non-OpenVINO providers.

## First Intel Implementation

The first useful Intel pass should add:

- `Dockerfile.cpu` from the shared Python 3.14 + uv base
- `Dockerfile.intel-openvino` from the shared Python 3.14 + uv base
- provider probe command or runtime preflight
- ONNX model cache directory under `~/.material-agent/models`
- one embedding scorer and one quality scorer behind the local backend
- benchmark output that records device, provider, throughput, and fallback decisions

## Model Candidate Order

Start with the default model stack in `docs/ai/model-selection.md`:

- MUSIQ, NIMA, and CLIPIQA for quality and aesthetic scoring
- DINOv2-small for grouping and similarity embeddings
- MobileCLIP2 or MobileCLIP-S1 for scene and semantic tags
- MediaPipe Face Landmarker for portrait/face structure

Only replace production score policy after the benchmark beats the current local heuristic baseline on group-level metrics.

## Metrics

Track group-level and culling-risk metrics before per-image score aesthetics:

- group top-1 agreement
- pairwise preference accuracy
- reject false-negative rate
- scene/category calibration
- throughput per device
- model fallback rate

## Current Migration State

`material-agent` still contains copied legacy OMLX/Ollama modules from `material-judge`. Treat them as migration debt. New work should not call them from the default path, and they should be quarantined or deleted after local diagnostics and benchmark commands exist.
