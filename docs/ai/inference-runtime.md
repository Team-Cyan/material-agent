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

## Runtime Preflight

`backend: local` now records a report-only runtime preflight event before a run.
The preflight checks the configured `inference.runtime`, optional package
availability, visible providers/devices, model cache path, and whether the run is
still using heuristic scoring.

The default remains non-blocking because the current scoring baseline must still
run on CPU-only hosts without optional OpenVINO packages. Set
`inference.enforce_available: true` only when a deployment must fail fast if the
declared runtime package or provider is unavailable.

Preflight is observability, not model execution. A passing OpenVINO preflight
does not mean DINO, MobileCLIP, or IQA models are wired into the scoring path.
Strict model execution separately records the requested device, compiled device,
configured fallback, whether application-level fallback occurred, and the
actual `EXECUTION_DEVICES` readback. If OpenVINO cannot provide that readback,
the result is marked unknown rather than copying the requested device into an
"actual" field.

## Semantic Vertical Slice

The first learned local block is implemented behind
`SemanticClassifierPort` and `OpenClipSemanticAdapter`. It loads lazily, so the
default heuristic path does not import Torch or OpenCLIP. Enable it with
`local.semantic.enabled: true` after installing the `local-models` optional
dependencies.

The verified CPU profile is:

- model: `MobileCLIP2-S0`;
- pretrained tag: `dfndr2b`;
- runtime: OpenCLIP 3.3 with Torch on Python 3.14;
- fallback: preserve heuristic `scene=other` and record `_semantic.status` as
  `fallback` unless `local.semantic.enforce_available` is true;
- provenance: report actual `open_clip:cpu` execution separately from the
  configured future OpenVINO runtime.

On the maintained synthetic v1 fixture set, this slice changed scene accuracy
from 1/4 to 4/4 and the `other` rate from 4/4 to 1/4. This is architecture and
regression evidence, not enough coverage to enable the model by default for
production photography.

## Native OpenVINO Vertical Slice

`OpenVinoEmbeddingAdapter` now loads a local ONNX bundle with native OpenVINO,
compiles it with a persistent cache, performs inference, and records actual
execution devices. `prepare-openvino-model` materializes Hugging Face ONNX
external-data symlinks into a self-contained bundle. Bundle and compiled-cache
identity cover the ONNX graph, every declared external-data file, processor
assets, OpenVINO/runtime settings, and preprocessing revision. External-data
paths that escape the model directory are rejected at runtime, so a normal
Hugging Face symlink snapshot must be materialized before direct use.

Device fallback has two valid forms:

- OpenVINO may compile `AUTO:GPU,CPU` successfully and internally select CPU;
  this is actual CPU execution but not application-level fallback.
- If the requested compile target is unavailable, the adapter may compile the
  explicit configured fallback such as `CPU`; this sets `fallback_used=true`
  and records the original exception reason.

Verified on OpenVINO 2026.2.1 CPU:

- DINOv3 ViT-S MHA Q4 is incompatible because the graph contains
  `com.microsoft.MultiHeadAttention` without an OpenVINO conversion rule;
- the standard-operator quantized DINOv3 ViT-S export compiles and runs;
- the maintained near-duplicate metric is 2/2;
- the compiled cache creates a device-specific blob;
- repeated-process cold load improved from about 4.55 seconds to 2.89 seconds
  with the cache, while warm fixture inference stayed around 0.53 seconds;
- actual execution device readback on the Apple verification host is `CPU`.

The corrected synthetic CPU benchmark is
`docs/operations/benchmarks/2026-07-13-openvino-dinov3-quantized-cpu-synthetic-v2/`.
It clears the bounded per-image result cache before every repetition while
retaining the persistent compiled-model cache. On the Apple CPU verification
host it records 1.561 seconds for the first four-image run, a 0.530-second warm
p50 for four real inferences, and 4.577 images/second across three repetitions.
The older 2026-07-11 v1 report remains historical, but its 0.07-second warm p50
was dominated by result-cache hits and must not be cited as inference speed.

Target Intel GPU execution is now verified on the Unraid Linux NAS through a
DockerMan-managed, read-only pilot. The container exposed `/dev/dri`, OpenVINO
reported both `CPU` and `GPU`, and all ten bounded score payloads recorded
`runtime=openvino` with actual execution device `GPU.0`. The pilot used a fresh
appdata-backed runtime directory, mounted the photo library read-only, ran with
dry-run enabled, and left both source-side XMP count and source-side runtime
directory count at zero. This proves model execution on the target iGPU; it does
not yet provide warm CPU/GPU parity or target-host utilization measurements. A
single cold full-pipeline comparison over the same ten-file bounded set recorded
about 28 seconds on CPU (0.357 files/second) and 43 seconds on GPU (0.233
files/second). GPU was slower in that cold, tiny sample; model initialization,
container/cache temperature, and non-model pipeline work make it unsuitable as
a steady-state accelerator conclusion.

## Current Intel Image Contract

The maintained Intel image now provides:

- digest-pinned Python/uv base, checksum-pinned Intel userspace packages, and a
  checksum-pinned bundled DINOv3 ONNX bundle;
- a baked `backend: local` profile with DINOv3 OpenVINO embedding enabled,
  `AUTO:GPU,CPU`, explicit CPU fallback, and compiled cache under `/config`;
- a lean Intel dependency set without Torch, Transformers, OpenCLIP, PyIQA, or
  MediaPipe, with unsupported screening disabled in the baked profile;
- root startup limited to PUID/PGID alignment, `/dev/dri` supplementary groups,
  and allowlisted appdata migration before `gosu` drops to an unprivileged user;
- `/config/state.db`, `/config/run.log`, and `/config/openvino-cache` as the
  writable appdata contract while `/photos` remains a read-only input mount;
- immutable commit image publication followed by entrypoint, ownership,
  dependency, bundled-model, AUTO-selection, and explicit fallback smoke tests;
  the mutable `intel-openvino` tag is promoted only after those checks pass.

## Model Candidate Order

Start with the default model stack in `docs/ai/model-selection.md`:

- BRISQUE/NIQE reject priors plus MUSIQ, NIMA, and CLIPIQA+ for quality and
  aesthetic scoring
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

`material-agent` still contains copied legacy OMLX/Ollama modules from
`material-judge`. Production `run` now requires `legacy.enabled: true` before a
legacy backend may be selected, legacy commands are absent from the CLI, and
the commands package no longer re-exports OMLX runtime helpers. Retain the
remaining modules only for explicit teacher/compatibility work until their
deprecation inventory is reviewed.
