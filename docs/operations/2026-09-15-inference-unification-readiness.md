> Design update 2026-09-16: grouping now uses adjacent time AND hash proximity, with hash threshold 0 selecting time-only grouping. Semantic/action classification is not a grouping prerequisite or veto. Earlier promotion criteria below are historical; see [current grouping contract](../ai/modules/grouping.md).

# Phase 1 inference unification and Phase 2 readiness

The user approved the [Gate 0/1 proposal](2026-09-15-inference-unification-gates-0-1.md)
after the checkout inventory. This report describes local implementation only.
No default model, grouping rule, score threshold, XMP policy, deployment, or
persisted database location was changed.

## Before and after

| Area | Before | After |
| --- | --- | --- |
| Native execution | NIMA, embedding and SSD each compile and schedule separately | All three subclass `OpenVinoSession` and execute through its compile/cache/request/normalization lifecycle |
| Model semantics | Adapter-specific transforms and output rules | Same rules; `preprocessing_spec` supplies declarations used by execution and result identity; typed outputs retained |
| Batching | NIMA/embedding async, SSD synchronous | Shared ordered AsyncInferQueue; SSD remains batch 1/request 1/LATENCY; NIMA reshape and embedding reshape/BATCH/single strategies retained |
| Bounds | Individual request limits, no disk quota | At most 32 decoded inputs per public adapter/client chunk; declared batches/requests retain existing 1..64 limits; final batches repeat last input and discard padding |
| Result cache | Duplicated JPEG-only LRUs | Shared deep-copy LRU keyed by image, model assets/config, declared preprocessing, runtime versions and lifecycle revision; explicit hit/miss/bypass |
| Compile cache | Shared root without application quota | Owned `local-inference-v1` namespace, 16 entries / 2 GiB, serialized compilation/eviction; oversized entry bypasses persistence; old cache files untouched |
| Timing | Run dedupe but maximum compile duration across models | Distinct compilation IDs summed once; run IDs deduped; SSD postprocess timed; benchmark aggregates all model kinds |
| Persistence | JSON metadata version 1 | Additive nested execution facts within the same JSON format; cache revision invalidation; no DDL or data rewrite |
| Optional paths | Package-owned adapters | Retained with explicit `model_specific` execution and missing-evidence fields; no unsupported OpenVINO conversion implied |

A compiled object no longer reads its disk cache after compilation; the cache
lock protects disk entries during creation/readback. Eviction applies only to
inactive disk entries in the new namespace. Configuration roots and old cache
contents remain operator-owned. `LOADED_FROM_CACHE` is queried, with `unknown`
when unavailable; presence of a directory is not evidence of a hit.

Per-adapter locking protects lazy initialization and last-run metadata. Asset
snapshots cover graph, external data, IR companion and processor membership,
rehashing when file metadata changes. A changed asset invalidates the adapter
session and client result identity. Custom injected adapters must declare
`result_cache_revision` to opt into reuse when no verified local asset exists.

`execution` records have their own `local-inference-v1` schema, model identity,
preprocessing contract, requested/submitted/actual devices, explicit fallback
kind, compile-cache identity/status, batch/request settings and missing evidence.
Legacy flat fields and `status=model|fallback` remain available. Unknown
execution devices never become the requested device. Raw embedding vectors stay
out of ordinary persisted score metadata.

Window priming now respects optional-model fallback: a non-strict failure falls
through to per-image scoring and its fallback record; strict availability still
raises. No score-fusion or group-selection policy was changed.

## Verification and limits

Pre-change focused baseline: 14 tests passed, including a generated ONNX graph
executed on real OpenVINO CPU with explicit fallback and a partial batch.
Post-change focused runs include real ordered batches, concurrent calls,
identity invalidation, bounded eviction, malformed output handling, tensor
parity, compilation accounting and version-1 SQLite JSON compatibility.

Actual-weight comparison used the existing local DINOv3 standard-operator
quantized export and the three checksum-pinned NIMA/SSD/YuNet assets from
`Dockerfile.intel-openvino`. Model downloads and caches were confined to ignored
local storage. The reference code was loaded from Git HEAD; application source
was not checked out or reverted. Input images were the four maintained
synthetic fixtures. NIMA/SSD additionally used a repeated fifth image.

| Comparison | Observed result |
| --- | --- |
| Heuristic score payload, excluding elapsed time | Equal on all four fixtures |
| DINO CPU vectors | Maximum absolute difference 0.0 |
| NIMA CPU, batch 1 and batch 4, scores and distributions | Equal; maximum score difference 0.0, including partial batch |
| SSD + YuNet CPU objects, faces, primary subject, scene | Equal on all five inputs; includes positive object/face detections |

These establish local baseline parity for covered fixtures, not photographic
quality improvement, complete operator/export coverage, Intel GPU performance,
or subjective acceptance. Tiny-graph order tests allow normal CPU precision
rounding against NumPy; actual-weight before/after comparisons used `1e-6`
absolute/relative tolerance and observed zero differences.

Reproducible repository checks:

```sh
# The optional guard skips a test before any media/XMP filesystem write.
PYTHONPATH="$PWD/tests" PYTEST_PLUGINS=inference_readonly_guard make test
make check
uv run pytest -q tests/test_repository_boundary.py
git diff --check
```

The guard also blocks source-media fixture creation, XMP temporary files, media
renames/removal and metadata-writer subprocesses. It is opt-in and does not
change normal CI policy. Skipped XMP/media tests are not claimed as passed;
XMP compatibility remains a separate slice. New lifecycle tests use in-memory
images and temporary model/cache/database files only.

Verification results:

- Full suite with the read-only guard: **650 passed, 98 skipped in 89.39s**.
  The skipped tests were not executed through their media/XMP writes.
- Final focused lifecycle/adapter/architecture checks after provenance
  compatibility adjustments: **102 passed in 5.81s**.
- Isolated `run_local_benchmark` smoke using
  `tests/fixtures/local_benchmark/manifest.yaml`, two repeats and an ignored
  output directory: **4 items, deterministic_scores=true**. No production
  repository or writer was constructed.
- `make check`: passed. Repository-boundary tests: **2 passed**.
- `git diff --check`: passed; existing dirty guidance patch preserved byte for byte.
- Local real-weight commands: `uv run --no-sync python
  .local/inference-unification/parity.py` and `uv run --no-sync python
  .local/inference-unification/model_parity.py`; their ignored JSON reports are
  `parity.json` and `model-parity.json` in the same local directory. These scripts
  read fixed fixtures and write only reports/model caches. Model fetches used
  the Dockerfile revisions and verified all three pinned SHA-256 values.

No production review or external photo evaluation was run.

## Phase 2 candidate matrix

This is an experiment plan, not additional model implementation. Each row runs
alone against the frozen Phase 1 baseline before any fusion experiment. All
rows require asset digest, export revision, preprocessing/output revision,
runtime version, actual execution evidence (or unknown), failure counts and
stage timings. The budgets below are proposed experiment stop limits, not
measured performance or production commitments. Freeze them before holdout use.

| Candidate / business hypothesis | Runtime and input contract | Fixtures / baseline | Budget and failure behavior | Promotion metric |
| --- | --- | --- | --- | --- |
| MobileCLIP2-S0: improve scene/action context tags (never override time/hash grouping) | Existing OpenCLIP/Torch adapter; RGB preview, pinned package transform, tokenizer and prompt bank. ONNX/OpenVINO export remains unverified; do not force conversion. | Independent multi-dish/multi-action events, screenshots and ambiguous context; compare current SSD scene + heuristics and independent action labels. | CPU batch 1 initially; stop above +2 GiB RSS or +2 s/image warm p95; unavailable retains baseline and unknown semantic evidence. | Higher independent scene/action accuracy with documented confusion; no grouping-policy change. |
| DINOv2-small: optional within-group similarity diagnostic; not an active grouping requirement | Existing Transformers adapter with immutable revision; pin RGB processor resize/crop/normalization and pooled L2 vector. OpenVINO requires a separately verified export. | Event-isolated near duplicates, same background/different action and distinct dishes; compare current DINOv3 export and existing visual hashes. | Same CPU stop limits; no vector on failure; retain baseline grouping evidence. | Better diagnostic pairwise discrimination; no embedding-based merges under the current user-defined grouping rule. |
| TOPIQ_NR: detect technical defects missed by simple pixel metrics | PyIQA/Torch candidate; RGB float32 NCHW `[0,1]` outer input plus pinned metric-specific transforms. No verified native OpenVINO export in this checkout. | Independently labeled blur/noise/exposure examples, clean controls and small subjects; compare technical/focus signals, not NIMA aesthetics alone. | One metric, CPU batch 1; +2 GiB / +2 s per image warm p95 stop limit; unavailable leaves technical baseline unchanged. | Defect discrimination improves at a fixed false-reject ceiling; no coverage regression. |
| MUSIQ: independent perceptual-quality comparison | Existing PyIQA adapter, RGB tensor plus metric-owned multiscale preprocessing; do not equate the separate helper-based fast-screening lifecycle with shared OpenVINO execution. | Same frozen technical holdout plus screenshots and low-light photos; compare baseline and TOPIQ in separate runs. | Same limits; helper disabled for this experiment unless separately declared; fail to baseline, never a zero-quality surrogate. | Better defect/preference metrics on the fixed holdout with no extra false rejects. |
| MediaPipe Face Landmarker: reliable small-face/occlusion evidence | Existing Tasks IMAGE adapter, pinned `.task` digest, RGB uint8 and package-owned face ROI transforms; explicit CPU adapter, OpenVINO conversion unverified. | Positive small/side/occluded/multiple faces plus backs/silhouettes; compare YuNet landmarks and unknown-evidence behavior. | +1 GiB / +1 s per image warm p95 stop limit; no detection remains unknown, not closed eyes. | Higher applicable-landmark coverage at fixed false-positive rate; no penalty from absent evidence. |
| Simple ranker, then LightGBM Ranker: learn personal within-group preferences | CPU tabular ranking after real personal labels exist; versioned feature ordering/scaling and missingness; no image preprocessing or VLM default. | Real personal pairwise/group preferences split by event; compare current ordering and a simple linear/pairwise baseline. GPT labels do not establish personal preference. | +256 MiB / +50 ms per group p95 stop limit; missing features/model retains baseline order. | Holdout pairwise/top-choice agreement improves with no coverage regression; do not start from proxy-only labels. |

The candidate/runtime associations are grounded in the official
[MobileCLIP repository](https://github.com/apple-aiml-research/ml-mobileclip),
[DINOv2 repository](https://github.com/facebookresearch/dinov2),
[PyIQA repository](https://github.com/chaofengc/IQA-PyTorch),
[MediaPipe Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python),
and [LightGBM Ranker API](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRanker.html).
The business hypotheses, budgets and promotion criteria are project proposals.

Compatibility refreshed on 2026-09-15: local Python 3.14.3/OpenVINO 2026.2.1
executes the covered CPU models. OpenVINO's
[requirements](https://docs.openvino.ai/2026/about-openvino/release-notes-openvino/system-requirements.html)
list Python 3.10–3.14. The inspected
[ORT OpenVINO release](https://pypi.org/project/onnxruntime-openvino/) lists
cp313 wheels; this is not an argument to replace native OpenVINO. Optional
Torch/PyIQA/MediaPipe packages were not installed or revalidated during Phase 1.
The subsequent isolated [MobileCLIP experiment](2026-09-15-mobileclip-stanford40-experiment.md)
records its own package and CPU execution evidence. Each other candidate still
needs a Python/platform/package/export execution check.

## Evaluation protocol and readiness decision

1. Resolve accessible sample scope and the review channel; freeze pseudonymous
   item/event/reference-candidate IDs and licensing. Start with the proposed
   100–200 images / 20–40 groups only as a pilot, not statistical sufficiency.
2. Freeze baseline outputs, reference semantic units, rubric, budgets and
   numerical promotion thresholds before candidate evaluation. Split by event;
   file versions and bursts cannot cross tuning/holdout boundaries.
3. Label GPT observations `model_generated` and independently available human
   labels `human_reference`. Preserve source/version/rubric/preprocessing for
   every observation. Keep private image locations out of public artifacts.
4. Blind the evaluator to system/model identities and scores. Randomize pair
   order and reverse a subset; retain disagreements/unknowns and raw judgments.
5. Compare false rejects among reference keeps, independent-unit coverage,
   over-retention, pairwise/top-choice agreement, latency/RSS and fallback rate.
   Report sample counts and uncertainty. A fixed-case coverage loss is a stop
   condition; synthetic parity does not establish human acceptance.

Gate 0 and Gate 1 are complete. Gate 2 implements the shared lifecycle and
covered local parity; final repository check results qualify that evidence.
Gate 3 delivers this matrix/protocol. The next isolated single-model experiment
can be prepared from this baseline, but candidate promotion is not ready:
real event-isolated samples, review-channel execution and frozen quality
thresholds are still outstanding. Intel performance must be remeasured in a
separately authorized target-host session.

Unchanged follow-up work includes XMP professional-software fixtures, strict
candidate/coverage persistence, imported human/effective/write-result modeling,
and unsupported exports (including the historically incompatible DINO MHA
variant). The confirmed missing/zero-rating rule is not an unresolved decision.

## Changed files in this implementation

- `docs/ai/inference-runtime.md`
- `docs/ai/model-selection.md`
- `docs/ai/modules/local-model-stack.md`
- `docs/ai/modules/scoring-engine.md`
- `docs/operations/2026-09-15-inference-unification-readiness.md`
- `docs/roadmap.md`
- `src/material_agent/adapters/models/dinov2_embedding.py`
- `src/material_agent/adapters/models/inference_contract.py`
- `src/material_agent/adapters/models/mediapipe_face.py`
- `src/material_agent/adapters/models/openclip_semantic.py`
- `src/material_agent/adapters/models/openvino_embedding.py`
- `src/material_agent/adapters/models/openvino_nima_aesthetic.py`
- `src/material_agent/adapters/models/openvino_session.py`
- `src/material_agent/adapters/models/openvino_ssd_detection.py`
- `src/material_agent/adapters/models/pyiqa_quality.py`
- `src/material_agent/app/jobs/review_photos.py`
- `src/material_agent/app/local_benchmark_service.py`
- `src/material_agent/app/local_embedding_identity.py`
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/clients/local.py`
- `src/material_agent/commands/scoring.py`
- `tests/inference_readonly_guard.py`
- `tests/test_architecture_refine.py`
- `tests/test_dinov2_embedding.py`
- `tests/test_inference_lifecycle.py`
- `tests/test_local_benchmark.py`
- `tests/test_openclip_semantic.py`
- `tests/test_openvino_embedding.py`
- `tests/test_openvino_nima_aesthetic.py`
- `tests/test_pyiqa_quality.py`

## September 17 status correction

Coverage persistence and the projection-attempt ledger are now implemented; the
older follow-up list above records the Phase 1 handoff state. The current status
is maintained in [the audited plan](2026-09-16-plan-status.md). Independent
TOPIQ/MUSIQ/MediaPipe diagnostics and a 100-frame real-burst evaluation are in
the [holdout report](benchmarks/2026-09-17-hdrplus-holdout/report.md). No fusion
or default promotion follows from runtime success. Semantic/embedding grouping
hypotheses have been superseded by the user's adjacent time AND hash rule.
