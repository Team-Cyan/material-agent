# Local Model Selection

This document records the current local-model architecture for `material-agent`.
It is based on the latest model search plus local Apple M4 smoke tests on
Python 3.14.

## Selection Goals

- Run on NAS-class CPUs and Intel integrated GPUs first.
- Keep Apple Silicon native acceleration available outside Docker.
- Keep the default batch path small, deterministic, and explainable.
- Avoid HTTP VLM services in the default path.
- Prefer models with public weights, Python 3.14-compatible packages, and a path
  to ONNX, OpenVINO, CoreML, MLX, or PyTorch MPS.

## Pipeline Shape

Use a multi-model scoring stack instead of one general VLM:

```text
image -> preview decode -> technical metrics
      -> IQA/aesthetic scorers
      -> embedding scorer
      -> scene/semantic classifier
      -> optional face/subject signals
      -> calibrated local score
```

Every model must consume resized previews by default. Full-resolution inputs can
cause unnecessary memory pressure and were observed to fail on Apple MPS for some
IQA models.

## Default Stack

| Block | Default model | Why |
| --- | --- | --- |
| Technical quality | Existing exposure/sharpness CV metrics | Fast, deterministic, no model dependency, useful as a fallback. |
| No-reference quality | MUSIQ | Strong practical IQA baseline, available through PyIQA, works on Python 3.14 when fed resized previews. |
| Aesthetic score | NIMA plus CLIPIQA | NIMA is fast; CLIPIQA adds perceptual/aesthetic sensitivity. |
| Grouping / similarity | DINOv2-small | Locally verified on Apple MPS, fast embeddings, good same-set nearest-neighbor behavior. |
| Scene / semantic tags | MobileCLIP2-S0 if available, otherwise MobileCLIP-S1 | Apple-oriented small CLIP family; MobileCLIP2-S0 is OpenCLIP-compatible and locally verified. |
| Face / portrait signals | MediaPipe Face Landmarker | Python 3.14 runtime works with the official task asset; gives face/landmark structure without a heavy VLM. |

## Candidate Backlog

| Block | Candidate | Status | Reason to test |
| --- | --- | --- | --- |
| IQA | TOPIQ_NR | CPU fallback verified; not default | Modern IQA model in PyIQA, but MPS adaptive pooling failed and the local sample run ranked a screenshot too high. |
| IQA | QualiCLIP+ | Blocked in smoke test | Newer CLIP-based quality scorer in PyIQA, but the 390 MB checkpoint download produced corrupted partial files twice. |
| IQA | MACLIP | CUDA-only in local smoke test | Newer CLIP-based IQA/aesthetic candidate in PyIQA, but the current implementation asserts CUDA and does not run on Apple MPS. |
| IQA | Q-Align / Q-ReAlign mini | Deferred | More recent quality-alignment family, but larger and less NAS-friendly for a default path. |
| Embedding | DINOv3 ViT-S/16 distilled | Deferred behind access | Newer Meta embedding family; HF weights are gated in unauthenticated local tests. |
| Semantic tags | SigLIP2 base patch16 224 | Verified backup | Strong zero-shot semantics, but slower than MobileCLIP2-S0 locally and needs extra tokenizer dependencies. |
| Object/animal/person detection | YOLO26n | Verified optional signal | Small 5.3 MB detector; useful for subject signals, but slower than embedding/classifier passes and should not run on every image by default. |
| Subject/saliency | RMBG-2.0 / BiRefNet | Deferred | Strong subject/background separation, but heavier and licensing/trust-remote-code details need care. |
| Commentary / explanation | FastVLM-0.5B | Apple-native experiment only | Useful for explanations, not for the default batch scoring path. |

## Hardware Profiles

### CPU

Use deterministic CV metrics plus optional ONNX Runtime CPU models. This profile
must remain valid on any NAS. `onnxruntime` 1.27 installs on Python 3.14 in the
local smoke test.

### Intel OpenVINO

Use native OpenVINO first on Python 3.14. `onnxruntime-openvino` does not
currently publish `cp314` wheels, so it is not a viable default while the shared
Python 3.14 base is required. Native `openvino` 2026.2.1 installs on Python
3.14; the local Apple smoke test exposes CPU only, while Linux Intel containers
must probe `/dev/dri` and OpenVINO `AUTO:GPU,CPU`.

### Apple Native

Use PyTorch MPS first for experiments. A future production Apple profile can
consider CoreML or MLX conversion after the model set stabilizes.

Normal Docker containers should not assume Metal GPU access. Docker CPU mode or
a host-side service bridge are acceptable, but Apple GPU acceleration should be
native.

## Local Smoke-Test Findings

On Apple M4 with Python 3.14 and PyTorch MPS:

- PyIQA, OpenCLIP, Transformers/TIMM, MediaPipe, Ultralytics, and InsightFace can
  be installed and imported.
- MUSIQ, NIMA, and CLIPIQA run correctly when fed 512-pixel previews.
- Direct full-resolution IQA inference can trigger MPS out-of-memory failures.
- TOPIQ_NR runs on CPU, but failed on MPS because adaptive pooling with
  non-divisible input sizes is not implemented there. It also ranked a
  screenshot too high in the local sample set, so keep it out of the default
  score until calibrated.
- QualiCLIP+ did not complete a local smoke test because the checkpoint
  download repeatedly produced corrupted partial files.
- MACLIP did not run on Apple because the PyIQA implementation requires CUDA.
- DINOv2-small is fast and produced useful nearest-neighbor grouping signals:
  the two flower-wall images matched each other, cat images clustered, and the
  screenshot had very low photo similarity.
- DINOv3 ViT-S/16 weights are gated on Hugging Face, so they are not clean
  default dependencies.
- MobileCLIP2-S0 and MobileCLIP-S1 classified cats and screenshots reliably in
  the local smoke set. MobileCLIP2-S0 had a cached load time around 1.7 seconds
  and processed about 5 images/second on MPS.
- SigLIP2 base worked, but was slower and required extra tokenizer dependencies.
- MediaPipe Face Landmarker loaded the official task asset and processed the
  local sample set at about 5 images/second. The current sample set has no clear
  face-positive image, so recall still needs a fixture.
- YOLO26n loaded through Ultralytics, downloaded a 5.3 MB weight file, detected
  cats and people correctly in the sample set, and produced no screenshot
  detection. It was slower than the classifier/embedding passes on MPS.

## Evaluation Metrics

Do not choose defaults from single-image scores. Use fixed sample sets and track:

- group top-1 agreement
- pairwise preference accuracy
- reject false-negative rate
- screenshot/non-photo rejection
- scene/category calibration
- throughput per device
- fallback and failure rate

## Primary Sources

- PyIQA model zoo: https://github.com/chaofengc/IQA-PyTorch
- Apple MobileCLIP / MobileCLIP2: https://github.com/apple/ml-mobileclip
- Meta DINOv3: https://github.com/facebookresearch/dinov3
- Google SigLIP2 model card: https://huggingface.co/google/siglip2-base-patch16-224
- Apple FastVLM: https://github.com/apple/ml-fastvlm
- Ultralytics YOLO26: https://docs.ultralytics.com/models/yolo26/
- MediaPipe Face Landmarker: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
- BRIA RMBG-2.0: https://huggingface.co/briaai/RMBG-2.0
- BiRefNet: https://huggingface.co/ZhengPeng7/BiRefNet
