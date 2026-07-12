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
IQA models. Focus confirmation is the exception: resized previews are only a
cheap proxy for obvious blur, while eye focus or micro-shake on 30MP+ captures
needs a later high-resolution ROI pass on selected candidates.

## Default Stack

| Block | Default model | Why |
| --- | --- | --- |
| Technical quality | Existing exposure/sharpness CV metrics plus BRISQUE/NIQE reject priors | Fast deterministic metrics remain the hard fallback; BRISQUE and NIQE are very fast CPU priors for screenshot/non-photo rejection, not final aesthetic rankers. |
| No-reference quality | MUSIQ | Strong practical IQA baseline, available through PyIQA, works on Python 3.14 when fed resized previews. |
| Aesthetic score | NIMA plus CLIPIQA+, fallback CLIPIQA | NIMA is fast; CLIPIQA+ adds perceptual/aesthetic sensitivity and kept screenshots at the bottom in the local benchmark with only a tiny learned-prompt weight. |
| Grouping / similarity | DINOv2-small | Locally verified on Apple MPS, fast embeddings, good same-set nearest-neighbor behavior. |
| Scene / semantic tags | MobileCLIP2-S0 if available, otherwise MobileCLIP-S1 | Apple-oriented small CLIP family; MobileCLIP2-S0 is OpenCLIP-compatible and locally verified. |
| Face / portrait signals | MediaPipe Face Landmarker | Python 3.14 runtime works with the official task asset; gives face/landmark structure without a heavy VLM. |

## Candidate Backlog

| Block | Candidate | Status | Reason to test |
| --- | --- | --- | --- |
| IQA | BRISQUE / NIQE | Verified as reject priors | Extremely fast CPU metrics that ranked the screenshot worst in the local benchmark. Use as reject priors, not final aesthetic rankers. |
| IQA | CLIPIQA+ | Verified; preferred CLIPIQA variant | Tiny learned-prompt weight, no screenshot false positive in the local benchmark, and practical CPU throughput. |
| IQA | TOPIQ_NR | CPU fallback verified; not default | Modern IQA model in PyIQA, but MPS adaptive pooling failed and the local sample run ranked a screenshot too high. |
| IQA | PAQ2PIQ | CPU verified; not default | Fast after a moderate weight download, but ranked the screenshot above real photos in the local benchmark. |
| IQA | CNNIQA | CPU verified; not default | Lightweight, but ranked one real photo below the screenshot. |
| IQA | HyperIQA | CPU verified; not default | Rejects screenshots, but was far too slow for the NAS default path. |
| IQA | QualiCLIP+ | Blocked / too heavy in smoke test | The small plus checkpoint still triggers a 390 MB base `QualiCLIP.pth` download, which produced corrupted partial files before and is too heavy for default scoring. |
| IQA | LIQE / LIQE_mix | Deferred as too heavy | Each PyIQA weight is about 354 MB, so it is not a NAS-default scorer. |
| IQA | ARNIQA | Deferred after timeout | Requires a 107 MB download and timed out during local screening; keep only as a later research candidate. |
| IQA | MANIQA / DBCNN | Rejected for default path | MANIQA attempted a 518 MB checkpoint and DBCNN pulled VGG16-scale weights. |
| IQA | MACLIP | CUDA-only in local smoke test | Newer CLIP-based IQA/aesthetic candidate in PyIQA, but the current implementation asserts CUDA and does not run on Apple MPS. |
| IQA | Q-Align / Q-ReAlign mini | Deferred | More recent quality-alignment family, but larger and less NAS-friendly for a default path. |
| Embedding | DINOv3 ViT-S/16 ONNX | Verified backup | ONNX community Q4/quantized variants run on ONNX Runtime CPU; MHA Q4 was the best DINOv3 variant tested, but still did not beat DINOv2-small for grouping. |
| Embedding | DINOv3 ConvNeXt ONNX | Blocked in ONNX Runtime | Tiny and small Q4/quantized exports failed ONNX Runtime type inference on Loop/If/Concat nodes. |
| Embedding | DINOv2 with registers small | Verified; not default | Faster inference after load, but weaker same-group matching and screenshot separation than DINOv2-small. |
| Semantic tags | MobileCLIP2-S2 | Verified; not default | Larger than S0 and did not improve semantic labels or grouping on the local sample set. |
| Semantic tags | SigLIP2 B/16 and B/32 | Verified backup | Strong zero-shot family, but slower/heavier than MobileCLIP2-S0 locally and did not improve the current cleaning labels. |
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
- CLIPIQA+ runs correctly and remains preferred over plain CLIPIQA when the
  learned-prompt weight is available. Plain CLIPIQA remains a fallback. The
  maintained synthetic UI fixture later scored 0.597 with CLIPIQA+ and 65.8
  with MUSIQ, so neither may serve as the only non-photo reject signal.
- BRISQUE and NIQE are extremely fast CPU reject priors and both ranked the
  screenshot worst in the fixed local sample set. Use them as early reject
  priors rather than as final aesthetic scores.
- Direct full-resolution IQA inference can trigger MPS out-of-memory failures.
- TOPIQ_NR runs on CPU, but failed on MPS because adaptive pooling with
  non-divisible input sizes is not implemented there. It also ranked a
  screenshot too high in the local sample set, so keep it out of the default
  score until calibrated.
- PAQ2PIQ also ranked the screenshot too high and should not be a default
  scorer without calibration.
- QualiCLIP+ did not complete a local smoke test because the checkpoint
  download repeatedly produced corrupted partial files. The plus variants still
  trigger the 390 MB base `QualiCLIP.pth` download, so keep them out of the
  default path.
- LIQE and LIQE_mix were not downloaded because each weight is about 354 MB.
- ARNIQA and MUSIQ-PAQ2PIQ timed out during weight download; keep them as later
  research candidates, not defaults.
- HyperIQA rejected the screenshot but was much too slow for the NAS default
  path. MANIQA and DBCNN were interrupted after starting 500 MB-class downloads.
- MACLIP did not run on Apple because the PyIQA implementation requires CUDA.
- DINOv2-small is fast and produced useful nearest-neighbor grouping signals:
  the two flower-wall images matched each other, cat images clustered, and the
  screenshot had very low photo similarity.
- DINOv3 ViT-S/16 ONNX community exports are accessible and run on ONNX Runtime
  CPU. The MHA Q4 variant was the best DINOv3 variant tested, but DINOv2-small
  still had better same-group matching and screenshot separation.
- DINOv3 ConvNeXt Tiny/Small ONNX Q4 and quantized exports failed to load in
  ONNX Runtime because of a Loop/If/Concat type-inference error.
- MobileCLIP2-S0 and MobileCLIP-S1 classified cats and screenshots reliably in
  the local smoke set. MobileCLIP2-S0 had a cached load time around 1.7 seconds
  and processed about 5 images/second on MPS.
- MobileCLIP2-S2 worked, but did not improve semantic labels or grouping on the
  local sample set.
- SigLIP2 B/16 and B/32 worked, but were slower/heavier and did not improve the
  current cleaning labels.
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

## Latest Fixed-Sample Benchmark

Detailed measurements from the 2026-07-01 candidate pass are recorded in
`docs/operations/2026-07-01-local-model-candidate-benchmark.md`.

The maintained synthetic regression reports are stored under
`docs/operations/benchmarks/`. The 2026-07-11 MobileCLIP2-S0 CPU report verifies
the first production-shaped semantic adapter, including lazy loading, fallback,
provenance, and repeatability. Keep the block disabled by default until a
broader real-camera fixture set confirms scene calibration.

The full synthetic stack report also verifies DINOv2-small and MediaPipe Face
Landmarker. DINOv2 matched the maintained near-duplicate pair at 2/2 and
MediaPipe reached 2/2 face recall. The quality/aesthetic blocks reached only 2/3
pairwise preference because the UI screenshot outranked the low-light photo;
keep their signals out of default score fusion until broader calibration.

## Primary Sources

- PyIQA model zoo: https://github.com/chaofengc/IQA-PyTorch
- PyIQA weights: https://huggingface.co/chaofengc/IQA-PyTorch-Weights
- Apple MobileCLIP / MobileCLIP2: https://github.com/apple/ml-mobileclip
- Meta DINOv3: https://github.com/facebookresearch/dinov3
- DINOv3 Transformers docs: https://huggingface.co/docs/transformers/en/model_doc/dinov3
- DINOv3 ViT-S ONNX: https://huggingface.co/onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX
- Google SigLIP2 model card: https://huggingface.co/google/siglip2-base-patch16-224
- Apple FastVLM: https://github.com/apple/ml-fastvlm
- Ultralytics YOLO26: https://docs.ultralytics.com/models/yolo26/
- MediaPipe Face Landmarker: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
- BRIA RMBG-2.0: https://huggingface.co/briaai/RMBG-2.0
- BiRefNet: https://huggingface.co/ZhengPeng7/BiRefNet
