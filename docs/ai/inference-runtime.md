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
   - Default device: `CPU` after the target i7-11700T throughput matrix.
     `AUTO:GPU,CPU` and explicit `GPU` remain supported overrides.
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
does not by itself mean a configured model is wired into the scoring path.
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

### Lightweight object and focus pipeline

The Intel image bundles the FP32 ONNX Model Zoo SSD MobileNet V1 opset-12 graph
for COCO object localization and the OpenCV YuNet INT8 graph for face and five-
point landmark localization. SSD is resized to 320x320 and runs through native
OpenVINO; YuNet runs through OpenCV DNN. This path adds neither YOLO nor CLIP,
and keeps Torch, TensorFlow, MediaPipe, and OpenCV contrib out of the image.
Both model repository revisions and their SHA-256 digests are pinned in the
Dockerfile.

The scoring order is deliberate:

1. exposure and whole-frame Laplacian sharpness run on CPU; only catastrophic
   blur can stop the pipeline before model inference;
2. SSD selects a primary subject using confidence, area, center position, and a
   person/animal preference;
3. focus is measured again in that subject ROI; detected faces promote the
   measurement to two eye ROIs;
4. images without a confident detection use a NumPy/OpenCV spectral-residual
   saliency ROI rather than failing or scoring the whole frame as the subject.

Artifacts retain detected objects, normalized boxes, face landmarks, subject
selection, model SHA-256 digests, requested/compiled/execution devices,
fallback details, compiled-cache identity, and per-stage timing. The retained
focus grayscale preview is bounded to a 2048-pixel edge; it is more precise than
the normal 1024 scoring preview but is not represented as a full-resolution RAW
crop.

### Learned aesthetic scoring

The default Intel image bundles NIMA MobileNet aesthetic scoring rather than a
general-purpose DINO embedding. The graph is the Apache-2.0
`litert-community/NIMA-LiteRT` FP16 TFLite export pinned at revision
`15308061b353e9ef1de4c9d33b8f0fab0a7e350e`; the image build verifies SHA-256
`a5051a0fcced735682735e3e0fd58ee54c83ed664282a003f52235b3dbcb9320`.
It predicts the ten AVA rating buckets and exposes their 1-10 expected value.

`local.aesthetic.enabled` is a real fusion input, not metadata-only
observability. When a learned result is available,
`aesthetic.overall_aesthetic` owns the layered policy's `aesthetic_total`.
The older heuristic composition, lighting, color, depth, mood, and subject
signals remain visible for diagnostics and provide the fallback only when the
model is unavailable. Technical quality, subject focus, and screening policy
remain separate from aesthetic preference. Every result records the full
distribution, model digest/version, requested and actual device, fallback,
batch/request settings, cache identity, and stage timing.

NIMA remains a general whole-frame aesthetic predictor. Optional
`local.aesthetic.calibration` keeps the raw score and applies a versioned,
human-label-fitted affine profile in exact-object, scene, then default order.
Object adjustments are blended by detector confidence. Profiles below the
configured label threshold are a no-op, so generated XMP or model decisions
cannot silently masquerade as preference tuning. Fresh runs persist raw and
effective signals plus calibration provenance; rescore can reapply scene-level
profiles from the raw signal. See
`docs/operations/aesthetic-target-calibration.md`.

The client primes one NIMA batch for each prepared review window and reuses the
bounded content-addressed result cache during per-image scoring. The isolated
benchmark reports NIMA's effective score rather than the mean of heuristic
dimensions and includes raw/calibration provenance when configured.
The production profile disables DINO embeddings because embedding grouping is
still opt-in and those vectors do not affect the score.

`OpenVinoEmbeddingAdapter` now loads a local ONNX bundle with native OpenVINO,
compiles it with a persistent cache, performs inference, and records actual
execution devices. `prepare-openvino-model` materializes Hugging Face ONNX
external-data symlinks into a self-contained bundle. Bundle and compiled-cache
identity cover the ONNX graph, every declared external-data file, processor
assets, OpenVINO/runtime settings, and preprocessing revision. External-data
paths that escape the model directory are rejected at runtime, so a normal
Hugging Face symlink snapshot must be materialized before direct use.

The embedding path is throughput-aware rather than one-image synchronous:

- `performance_hint` is passed to OpenVINO and defaults to `THROUGHPUT`;
- `batch_size` reshapes the model batch dimension, pads only the final partial
  batch when the graph supports reshape. If an export has fixed internal
  shapes, the adapter uses OpenVINO's native `BATCH:<device>(N)` plugin to
  combine batch-1 asynchronous requests. Only failure of both strategies falls
  back to batch 1, and provenance reports `reshape`, `auto_batch`, or `single`;
- `AsyncInferQueue` runs the configured request pool while preserving input
  order; `infer_requests: auto` reads
  `OPTIMAL_NUMBER_OF_INFER_REQUESTS` and caps it with `max_in_flight`;
- the review pipeline prepares a bounded window in parallel, primes all
  embeddings in that window once across original group boundaries, then reuses
  the ordinary result cache during scoring. Score artifacts are collected first
  and the existing group commentary/ranking/write phase follows, so grouping
  semantics and resumability remain unchanged. Screening-enabled runs skip
  priming so early rejection still avoids unnecessary model work;
- per-run provenance records requested/actual batch size, request count,
  optimal-request readback, performance hint, and actual execution devices.

The Intel image uses a 32-preview preparation window, batch 1, and up to eight
in-flight requests. This target-specific default avoids the dynamic-shape
auto-batch path because batch 4/8 did not improve throughput on the i7-11700T.
These are throughput controls, not semantic model settings,
so changing them does not invalidate persisted embedding vectors.
The preparation window remains capped at 32 to bound memory, while the separate
read-only `review_pipeline.max_files` pilot limit accepts up to 4096 files so a
throughput run can cover many windows without accidentally selecting the whole
multi-terabyte library.

Stage timing separates RAW preview decode, local heuristic scoring, OpenVINO
preprocessing, inference, postprocessing, and compile time. Review job summaries
and `benchmark-local` reports aggregate a shared asynchronous inference run only
once even though every image retains the same provenance. Stage sums can overlap
because RAW preparation and inference requests are intentionally concurrent;
use end-to-end elapsed time for throughput comparisons.

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

Target Intel GPU execution and steady-state parity are verified on the Unraid
Linux NAS through DockerMan-managed, read-only pilots. The fixed 128-RAW matrix
tested CPU and `GPU.0` at batch 1/4/8, with eight asynchronous requests and
`THROUGHPUT`. CPU warm throughput was 6.737 files/second for every batch size;
GPU warm throughput was 0.496 files/second for every batch size. GPU embedding
inference took about 242.4 seconds versus 2.8-2.9 seconds on CPU. OpenVINO native
auto-batch did report actual batch 4/8 with no fallback, so the result is not a
device-selection failure. The winning CPU batch-1 profile then processed 512
RAW files in 88 seconds (5.818 files/second), with 512 model embeddings and no
errors. The durable report is
`docs/operations/benchmarks/2026-07-15-unraid-openvino-cpu-gpu-matrix.md`.

## Current Intel Image Contract

The maintained Intel image now provides:

- digest-pinned Python/uv base, checksum-pinned Intel userspace packages, and
  checksum-pinned bundled NIMA, SSD MobileNet, and YuNet model assets;
- a baked `backend: local` profile with SSD/YuNet detection, subject/eye focus,
  and NIMA learned aesthetic scoring enabled on `CPU`, explicit CPU fallback,
  throughput-mode async NIMA inference, and compiled cache under `/config`;
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
