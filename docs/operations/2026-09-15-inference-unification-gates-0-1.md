# Local inference unification: Gate 0 inventory and Gate 1 proposal

Status: Gate 0 complete; Gate 1 ready for user confirmation. No implementation
or Phase 2 promotion is claimed. Scope follows the
[session prompt](2026-09-14-inference-unification-session-prompt.md) and
[confirmed decisions](2026-09-14-design-review-decisions.zh-CN.md).

## Gate 0: checkout and evidence

At entry, 15 tracked guidance files were modified and two operation documents
were untracked. No source, configuration, or test changes were present.
Preserve all of them. This report is the only added deliverable at this gate.

Existing tracked changes: `.agents/{README,codex,harness-engineering}.md`,
`AGENTS.md`, `docs/README.md`, and under `docs/ai/`: `README.md`,
`architecture/module-boundaries.md`, `harness-workflow.md`,
`memory/{ai-collaboration-decisions,repository-evolution-notes}.md`,
`project-overview.md`, `prompts/{debug,feature}.md`, `shared-context.md`,
`templates/subagent-task.md`. Existing untracked documents are the two
2026-09-14 operation documents linked above.

Local interpreter: Python 3.14.3, Darwin arm64. Installed distributions include
OpenVINO 2026.2.1 and ONNX 1.22.0. ONNX Runtime, Torch, OpenCLIP, PyIQA,
Transformers, and MediaPipe are absent in this interpreter. This is local
package evidence, not target Intel deployment validation.

Actual wiring: `clients/base.py` -> `clients/local.py` -> model adapters;
`app/review_runtime.py::prime_prepared` primes NIMA and embeddings over prepared
windows, except when screening is enabled. Per-image scoring then consumes the
client caches. Grouping has a separate embedding callback and SQLite vector
cache. The review constructor creates writers and repositories; it was not run.

`config.yaml` disables learned local blocks and screening. The baked
`docker/config.intel-openvino.yaml` enables SSD/YuNet and NIMA on CPU with strict
availability, while embeddings and screening remain disabled. These are checked
in profiles, not a statement about any running container.

| Path and owning file under `src/material_agent/` | Actual preprocessing and execution | Batching, caching, fallback and provenance |
| --- | --- | --- |
| Heuristics: `clients/local.py`, `domain/scoring_engine.py` | CPU NumPy/OpenCV; bounded previews, exposure/sharpness, subject/eye or saliency ROI | No compiled model; default service-free baseline. Pixel scores and local dimension heuristics must remain equivalent. |
| NIMA: `adapters/models/openvino_nima_aesthetic.py` | Native OpenVINO; RGB, bilinear 224x224, float32 NHWC, `x/127.5-1`; ten-bin normalized distribution and expected rating | Reshaped batches, repeat-last padding, async request pool and ordered reconstruction. Client JPEG-hash LRU; persistent OpenVINO cache without application capacity bound. Explicit device fallback and actual readback. |
| Embedding: `adapters/models/openvino_embedding.py` | Native OpenVINO; processor JSON controls RGB resize/crop/rescale/normalization/layout; output selection, CLS extraction where applicable, L2 normalization | Reshape -> native BATCH plugin -> optional batch-1 fallback; bounded async requests and partial padding. Client JPEG-hash LRU plus separate persisted grouping cache. Bundle digest includes ONNX external data and processor JSON. Device/batch fallback and actual readback recorded. |
| SSD: `adapters/models/openvino_ssd_detection.py` | Native OpenVINO; RGB, OpenCV INTER_AREA resize (default 320x320), uint8 NHWC; named box/class/score/count outputs | Synchronous batch 1, LATENCY compile, lazy-init lock; no per-model result cache. Persistent compiled cache without capacity bound. Explicit device fallback; adapter omits readback error/status and runtime version, although runtime captures them. |
| YuNet: same detector adapter | OpenCV DNN `FaceDetectorYN`; RGB -> BGR, INTER_AREA max-edge 640 without upscale, variable input size | Serial detector protected by lock; in-memory detector reuse, no result or persistent compiled cache. Missing asset silently returns empty faces; only face digest/name and combined detection timing are emitted. |
| Semantic: `adapters/models/openclip_semantic.py` | OpenCLIP/Torch, package-owned image transform/tokenizer; normalized image/text similarity and softmax | Lazy model, single-image calls, no application result/compiled cache. Client fallback or strict exception. Tag-based model identity and configured Torch device, not OpenVINO execution. |
| IQA: `adapters/models/pyiqa_quality.py` | PyIQA/Torch; RGB float32 NCHW `[0,1]`, metric-specific internal processing, configured normalization and roles | Lazy metric instances, serial metrics per image; no application result/compiled cache. Client fallback or strict exception; metric names/policy/device, incomplete asset and timing evidence. |
| Alternate embedding: `adapters/models/dinov2_embedding.py` | Transformers/Torch AutoImageProcessor + pinned model revision, pooled normalized vector | Single-image adapter; client LRU also applies. Lazy model, package asset cache, no application compiled cache. Client fallback or strict exception; no immutable local asset digest in result. |
| Face structure: `adapters/models/mediapipe_face.py` | MediaPipe Tasks IMAGE mode, RGB uint8; face landmarks -> counts/area | Lazy CPU landmarker, single image; no application result/compiled cache. Client fallback or strict exception. Asset filename used as version; no digest or stage timings. |
| Fast screening: `adapters/screening/musiq.py` | Separate PyIQA/Torch path, RGB float32 NCHW, divisor normalization | Lazy in-process metric; missing imports can start a configured helper interpreter per call with timeout. Separate lifecycle, scalar result, no shared provenance/cache. Disabled in both profiles. |
| `adapters/models/local_runtime.py` | Package/provider preflight only | `inference.runtime=onnxruntime` does not construct an ONNX Runtime inference session. No active plain ORT model adapter was found. |

### Verified gaps and documentation mismatches

1. NIMA, embedding and SSD own separate compile/scheduling implementations;
   importing private helpers from `openvino_embedding.py` is not a shared
   lifecycle. Lazy construction/run state is not uniformly synchronized.
2. NIMA/embedding in-memory cache keys contain only JPEG bytes. Client-instance
   isolation reduces immediate collisions but does not provide a declared,
   revision-safe identity. Hits copy old provenance without explicit hit status.
   Persisted score keys are stronger: `commands/scoring.py` fingerprints config,
   runtime packages, enabled local assets, external data and IR companions.
3. Reported compiled `cache_identity` hashes digest/device/runtime fields, but
   does not cover all graph-shape/compile controls or directly identify a bounded
   owned cache namespace. NIMA/SSD digest only the primary file; their missing
   assets yield a path hash, which is not an immutable asset digest.
4. Compile duration is repeated in per-run records. Existing aggregators dedupe
   `inference_run_id` and take maximum compile duration; maximum across multiple
   models is not the sum of distinct compilation events. SSD postprocessing is
   not separately timed.
5. Per-image client fallback retains heuristic output, but window priming calls
   adapters outside those catches. Optional-model failure handling must also be
   tested at the priming seam, not just in `score_image`.
6. `docs/ai/model-selection.md` describes a multi-model default stack that is not
   the baked Intel baseline. `scoring-engine.md` still names MUSIQ + VLM as the
   comparison baseline. `local-model-stack.md` broadly excludes learned signals
   from totals, while enabled NIMA already owns `overall_aesthetic`. These need
   targeted clarification during implementation.
7. The confirmed XMP nonzero-rating rule and strict subject/action coverage are
   future compatibility slices. This inference change must neither implement
   them incidentally nor claim current code satisfies them.

## Gate 1: smallest complete migration

### Shared execution seam

Add a model-neutral declaration/result contract and a shared native OpenVINO
session implementation under `adapters/models/`. Route all three existing
OpenVINO adapters through actual shared loading, compatibility validation,
compilation, scheduling, timing and provenance code. Keep model-specific output
normalizers and declarations in their owning adapters. No new inference engine
dependency, model download, or default profile switch is required.

Declarations include name/revision, verified asset bundle digest or explicit
missing evidence, preprocessing revision, input dtype/shape/layout/color,
resize/crop/normalization/ROI rules, output contract, and supported batch
strategies. They must drive validation and preprocessing, not merely describe
call-site behavior. Preserve the exact current tensor transformations, including
processor JSON behavior; processor corrections require a separate revision.

Preserve NIMA reshape/padding, embedding reshape/auto-batch/single fallback,
and SSD batch-1 execution as declared capabilities. Do not attempt SSD batching
or move YuNet into OpenVINO. Bound submissions and prepared tensors in chunks
(proposed default maximum 32 images), preserve duplicate/source positions,
validate output count/shape/finiteness, copy callback buffers, and synchronize
lazy compilation and per-session mutable execution state.

YuNet and the optional package-specific paths retain explicit adapters. Add
capability/status evidence at their boundary, including missing assets and
unknown digest/device evidence; do not advertise these paths as executing the
new OpenVINO lifecycle or as export-compatible. Keep missing face/eye evidence
unknown, without introducing new score penalties or inferred applicability.

### Cache and timing contract

- Separate model-result identity from compiled-session identity. Result keys
  include JPEG content digest, verified model assets, model/preprocess/output
  revisions, relevant runtime/numeric settings and model-specific policies.
  Keep raw NIMA predictions separate from downstream calibration. Preserve the
  existing CPU baseline and conservatively partition numerical settings unless
  parity proves a scheduling control safe to exclude.
- Replace duplicate client LRUs with one bounded cache helper while retaining
  public client methods. Report hit/miss/bypass and the original computation
  provenance separately from current lookup timing. Do not permanently cache
  transient failures or fabricated digests. Freeze model declaration per session;
  asset replacement invalidates the session/cache rather than mixing versions.
- Compile identity additionally includes graph input/batch strategy, target,
  fallback compilation target, runtime version and compile properties. Use a
  new application-owned namespace under the configured cache root. Proposed
  defaults: 16 entries and 2 GiB, with locked eviction of inactive owned entries;
  oversize entries bypass persistent caching. Never prune pre-existing unmanaged
  files or application data. Cache readback without evidence is `unknown`.
- Keep requested target, submitted compile target (including BATCH plugin), and
  actual execution devices distinct. Internal AUTO CPU selection is not explicit
  application fallback. Unknown readback stays unknown. Bound and sanitize
  failure reasons; preserve strict `enforce_available` behavior.
- Assign separate compile-event and inference-run IDs. Aggregate each once
  across model kinds and images, including cache reuse and repeated calls.
  Preserve per-stage preprocess/infer/postprocess times and explain concurrent
  wall-time overlap. Treat optional priming failures consistently with per-image
  fallback and retain error evidence.

### Payload/state compatibility and likely touched seams

Keep existing `score`, `distribution`, `vector`, object/face schemas,
`status=model|fallback`, scene values and policy inputs. Add a versioned nested
execution record with `success|unavailable|fallback` and adapt existing flat
provenance fields for consumers. Do not serialize vectors into ordinary metadata.

`processed_sqlite.py` already preserves generic `score_metadata_json` (version 1)
and runtime artifacts carry JSON. Prefer additive nested execution metadata;
no DDL or database relocation is expected. Legacy rows remain readable, missing
execution evidence stays unknown, and versioned cache-key invalidation prevents
old scores from masquerading as newly instrumented results. Read old metadata
without rewriting it; any necessary DDL discovery reopens this design gate.

Expected seams: three OpenVINO adapters, new shared execution/cache modules,
`clients/local.py`, `utils/config_validator.py`,
`app/local_embedding_identity.py`, `commands/scoring.py`,
`app/jobs/review_photos.py`, `app/local_benchmark_service.py`, and focused tests.
`app/review_runtime.py` may need narrow priming/fallback wiring. Optional
adapters need only truthful boundary records. Preserve dirty guidance files;
update only relevant clean model/runtime contracts after confirmation.

### Verification plan after confirmation

1. Golden tensors and typed outputs for each adapter; declaration, asset,
   preprocessing, output-policy and compile-setting cache partition tests.
2. Out-of-order callbacks, duplicates, concurrent calls, empty input, final
   partial batch, count mismatch, nonfinite output, unsupported export,
   initialization failure, optional fallback and strict failure tests.
3. Real generated ONNX CPU execution with partial batches and device fallback;
   fake-runtime AUTO selection/unknown readback cases; bounded cache eviction,
   active entry protection, no-evidence cache status and compile/run accounting.
4. Baseline score, NIMA distribution, detection, embedding, ranking and rescore
   compatibility; old SQLite payload reads and new metadata round trip in
   temporary databases. Writer calls must be blocked or mocked. Source fixtures
   remain read-only; no XMP output, including temporary sidecars, is needed.
5. Run focused tests, `make check`, `make test`, `git diff --check`, and
   `uv run pytest -q tests/test_repository_boundary.py`. Before the full suite,
   identify tests that deliberately create XMP and intercept their filesystem
   writes or exclude that separately owned slice with an explicit report;
   never report an excluded suite as a complete pass. Use only isolated
   `benchmark-local` for any later image evaluation.
6. Real NIMA/SSD weight parity and Intel performance remain separate evidence
   requirements if assets/hardware are unavailable. A tiny graph or injected
   runtime proves lifecycle behavior, not model-quality or target throughput.

## Executed checks and readiness

`uv run --no-sync pytest -q tests/test_openvino_embedding.py
tests/test_openvino_nima_aesthetic.py tests/test_openvino_ssd_detection.py`:
**14 passed in 6.20s**, including the real CPU fallback test (not skipped).
Its generated ONNX graph executed five images in batches of four. NIMA and SSD
coverage here uses injected runtimes; it does not establish real-weight parity.

`git diff --check` passed before adding this report. Final report validation is
recorded in the task response. No production review, source-media/XMP write,
commit, push or deployment was executed. Tests used in-memory synthetic images
and temporary model/cache files.

Gate 2 is pending user confirmation of this proposal. Gate 3 will then produce
the candidate-by-candidate hypothesis/runtime/input/provenance/holdout/baseline/
resource/failure/promotion matrix and an event-isolated evaluation protocol.
GPT observations must be `model_generated`, independent human labels
`human_reference`; sample scope and an available review channel still need to
be resolved before external evaluation. No Phase 2 model is ready for promotion
until the shared lifecycle and its parity baseline pass.
