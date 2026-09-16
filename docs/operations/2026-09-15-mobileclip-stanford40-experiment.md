> Design update 2026-09-16: grouping now uses adjacent time AND hash proximity, with hash threshold 0 selecting time-only grouping. Semantic/action classification is not a grouping prerequisite or veto. Earlier promotion criteria below are historical; see [current grouping contract](../ai/modules/grouping.md).

# MobileCLIP2-S0 isolated diagnostic experiment

This continues the approved Phase 1 work and the
[Phase 2 candidate matrix](2026-09-15-inference-unification-readiness.md).
The user authorized downloading a standard dataset when the previous ten RAW
paths were unavailable. All data, weights, environments and raw reports remain
in ignored `.local/` storage. Existing photos/XMP and production state were not
written. No model default, grouping policy, score threshold or deployment changed.

## Frozen runtime and baseline

- Platform: macOS arm64, Python 3.14.3; this is not Intel-target evidence.
- Separate environment: `.local/phase2-mobileclip-env`, synchronized from the
  existing lock with `--extra local-models --extra intel-openvino`.
- OpenCLIP 3.3.0, Torch 2.13.0, torchvision 0.28.0, timm 1.0.27.
- Model: `MobileCLIP2-S0`, pretrained tag `dfndr2b`, repository
  `timm/MobileCLIP2-S0-OpenCLIP`, revision
  `095906d28bf54d7584dc411e8ffe448f34289e05`.
- Safetensors SHA-256:
  `ab91a1a0c4330d6b1913e24d5035dfdea15423316aaec649610c6b1c6ddd0e95`.
- Keep the pretrained tag to retain its transform: RGB, bilinear short-side
  resize 256, center crop 256, tensor conversion, mean `(0,0,0)`, std `(1,1,1)`.
  Passing a bare checkpoint as the pretrained tag would lose that configuration.
- The harness replaces only the downloader with the checksum-verified local
  asset. Hugging Face and Transformers are offline during execution. Keep the
  `.safetensors` filename suffix: OpenCLIP uses it to select the loader.
- Baseline: frozen existing NIMA + SSD/YuNet CPU configuration and pinned assets
  from Phase 1. Candidate changes only the optional semantic profile.

## Synthetic integration comparison

`scripts/benchmark_mobileclip_candidate.py` runs independent baseline/candidate
processes through `run_local_benchmark`, three repetitions of the four maintained
fixtures. References are `model_generated`, not personal or human ground truth.
Raw reports: `.local/phase2-mobileclip/synthetic-run-2/`.

| Measurement | Result |
| --- | --- |
| Scene accuracy | Baseline 3/4; candidate 4/4 |
| Aggregate scores | Equal between profiles; candidate scores deterministic over repeats |
| Screenshot/photo score separation | Unchanged, -0.5625; no separation improvement established |
| Candidate warm classify p95 | 0.586 s, only 8 warm observations |
| Peak process RSS | Baseline 681,132,032 bytes; candidate 1,456,947,200 bytes |
| Incremental peak RSS | 775,815,168 bytes, about 0.723 GiB |
| Actual device evidence | Model parameters and observed visual input/output tensors on CPU |
| Model load time | 11.611 s, excluding package import time |

The proposed +2 GiB / 2 s warm p95 smoke budgets passed. The sample is too small
for quality acceptance; scene accuracy here is only an integration diagnostic.
The script compares aggregate scores, not every score-payload field. Its
determinism flag likewise covers the benchmark score contract.

## Standard dataset protocol

Selected [Stanford40 Actions](http://vision.stanford.edu/Datasets/40actions.html):
40 human action categories and 9,532 images, with official per-class training
and test splits and XML person annotations. This is relevant to the action
semantic hypothesis; it does not supply burst substitutability or personal
preference labels. The original paper is
[Human Action Recognition by Learning Bases of Action Attributes and Parts](https://svl.stanford.edu/assets/publications/pdfs/YaoJiangKhoslaLinGuibasFei-Fei_ICCV2011.pdf),
ICCV 2011.

Local root: `.local/datasets/stanford40/`. The publisher page supplies the HTTP
archive links and requests citation for research use; it does not state a
standalone license. Data remains local and is not redistributed. ZIP CRC checks
and locally recorded SHA-256 values detect extraction/local-copy corruption;
the publisher supplies no digest, so these are not authenticated upstream
checksum verification. The source page and provenance are retained locally.

Download/extraction verification completed: all **9,532 JPEGs** passed Pillow
verification and matched their XML filenames, action labels and dimensions;
**4,000 train / 5,532 test** filenames cover the full image set with zero
overlap. Per-class split lists match the global lists. `inventory.json` records
each image's SHA-256; `provenance.json` records source archive sizes and digests.

`scripts/benchmark_stanford40_actions.py` freezes five images per class from the
official test split using SHA-256 ordering with the fixed namespace
`stanford40-diagnostic-v1`. It checks train/test filename disjointness and writes
the 200-item protocol, image hashes and 40 prompts before model execution.
The single prompt template is `a photograph of a person {action}` with
underscores replaced by spaces; no result-driven prompt tuning is performed.
Official action labels are `human_reference` for this classification task only.
The runtime receives all 40 prompts for each image through its existing
classification method. No action label enters the application's scene schema.

Official train/test separation is not proof of event independence. Web-derived
pretraining overlap is unknown. Any confidence interval is descriptive and
does not account for correlated images or contamination. Uniform random top-1
chance is 1/40 (2.5%); the existing scene baseline has no comparable 40-class
action output, so this is a candidate-only action diagnostic.

The first run stopped after 11 images (only three reference classes) because
warm p95 reached 6.165 s. Full-dataset verification was still running during
that measurement, so it is retained as a potentially contended run rather than
accepted as an isolated latency result. A second run uses identical selection,
prompts and stop budgets after verification finished; no prompt/model tuning.

The isolated repeat also stopped after **11/200** images: **2.475 s warm p95**
(10 measured warm calls), **1,013,366,784 bytes peak RSS**, four Torch threads,
and CPU model parameters. It remained under the memory limit but exceeded the
unchanged 2 s latency limit. `completed=false`; its three observed action
classes do not provide a 40-class accuracy estimate. Both protocols are kept
under `.local/phase2-mobileclip/stanford40-run-{1,2}/`.

The original `_OpenClipRuntime.classify` tokenized and encoded the entire prompt
bank on every image. The follow-up below profiles and removes that repeated work.

## Completed 200-image comparison and text-cache fix

After the user requested continued testing/debugging, a 12-image stage profile
measured warm medians of 0.232 s for text encoding, 0.105 s for image encoding,
and about 0.001 s each for preprocessing/tokenization. This identifies avoidable
repeated work; it does not fully explain the earlier latency spikes.

A fresh **uncached** run completed all 200 images under the same 2 s stop budget.
Thus the previous stopped runs are evidence of timing variability, not proof
that the uncached model consistently exceeds the budget. The subsequent cached
run used the same images, prompts, model weights, CPU and four Torch threads.
No dataset verification ran alongside these measured comparisons; the full
regression suite started after both completed.

| Measurement, 200 images / 40 classes | Uncached | Cached |
| --- | --- | --- |
| Top-1 accuracy | 169/200 (84.5%) | 169/200 (84.5%) |
| Top-5 accuracy | 194/200 (97.0%) | 194/200 (97.0%) |
| Warm p95, 199 observations | 0.393470 s | 0.119584 s |
| Warm median | 0.347223 s | 0.106153 s |
| Peak process RSS | 1,013,088,256 bytes | 1,013,383,168 bytes |
| Stop reason | None | None |

Observed p95 improvement is **3.29x**. The 294,912-byte peak-RSS difference is a
process measurement, not a precise estimate of cache allocation. These are
sequential runs on this Mac, not a guarantee for Intel hardware or a statistical
performance study. The descriptive top-1 Wilson 95% interval is 78.84–88.86%,
subject to the sampling and pretraining limitations above.

The implementation retains one ordered prompt bank of normalized features,
bounded to 256 prompts / 65,536 characters; larger banks execute without being
retained. A runtime owns its model and cache. Model-object/device/prompt changes
miss the cache, and failed encodes never publish a new entry. Inference and
lazy runtime creation use locks to avoid concurrent duplicate work. Weights,
transforms, image features, normalization and probability scaling are unchanged.

All 200 predicted labels, Top-5 lists and top-1 probabilities matched exactly.
A separate comparison invoked the saved original classifier and the new
classifier against the same actual model for **all 8,000 probabilities**:
maximum absolute difference **0.0** (required tolerance `1e-6`). Evidence:

- `.local/phase2-mobileclip/stanford40-uncached-3/`
- `.local/phase2-mobileclip/stanford40-cached-1/`
- `.local/phase2-mobileclip/profile-before.json`
- `.local/phase2-mobileclip/text-cache-comparison.json`
- `.local/phase2-mobileclip/text-cache-parity.json` (includes source SHA-256 values)

Error inspection found all five `cutting_vegetables` samples predicted as
`cooking`; the reference action remained in Top-5 in all five cases. Two original
images were visually checked and show food preparation; one wrong coarse label
had 0.93 softmax confidence. This is a concrete failure to preserve fine action
distinctions, not grounds to change labels or tune prompts on this test subset.
`waving_hands` scored 2/5. With only five examples per class, neither result is a
stable per-class estimate. Coarse semantic agreement must not authorize merging
distinct actions or dropping subject/action coverage.

Reproduction from the repository root, after obtaining the pinned assets:

```sh
UV_PROJECT_ENVIRONMENT=.local/phase2-mobileclip-env uv run --no-sync python \
  scripts/benchmark_stanford40_actions.py \
  --dataset .local/datasets/stanford40 \
  --checkpoint-record .local/phase2-mobileclip/checkpoint.json \
  --output-dir .local/phase2-mobileclip/stanford40-new-run \
  --baseline-peak-rss-bytes 681132032
```

Output must be new or empty. The memory baseline is the measured value for this
host/run; remeasure it when evaluating another host or environment. A failed
budget produces a partial report with a stop reason; do not present its partial
accuracy as the planned 200-item benchmark result.

## Decision and verification

Promotion remains **not ready**. Real event-disjoint same-subject/different-action
groups, independent coverage/wrong-merge labels, personal preferences and Intel
target execution are still missing. A standard action dataset does not replace
those requirements. The frozen 200-image action diagnostic now completes within
its unchanged runtime budget. It establishes classification/runtime evidence,
not production grouping acceptance.

Checks for the added harnesses: `make check` passed; focused guarded tests
(`test_mobileclip_experiment`, `test_openclip_semantic`,
`test_repository_boundary`, `test_local_benchmark`) gave **15 passed, 6 skipped**.
The skips retain the no-existing-media/XMP-write boundary. The 15 pre-existing
dirty tracked paths still match their captured patch byte for byte.

After the text-cache fix, full guarded regression gave **653 passed, 102 skipped
in 27.31 s** (`.local/phase2-mobileclip/full-regression.log`). Four of these skips
are the new real-Torch cache tests in the main environment without Torch; those
tests were executed in the isolated model environment. The combined cache,
semantic and experiment tests there gave **15 passed**. Coverage includes bank
order/replacement, oversized-bank bypass, failed encoding retry, model-object
replacement, concurrent inference and one-time lazy initialization. `make check`
and `git diff --check` passed.

Final actual-model integration through `run_local_benchmark` also passed on the
four maintained fixtures, three repeats: baseline/candidate scenes remained
3/4 versus 4/4, aggregate scores matched, candidate scores were deterministic,
and the cached candidate's warm classify p95 was 0.110 s (eight observations).
Its incremental peak RSS was 765,362,176 bytes. Raw evidence is in
`.local/phase2-mobileclip/synthetic-cached-1/`. The 200 evaluated source image
hashes and the 15 originally dirty tracked paths were verified unchanged.
