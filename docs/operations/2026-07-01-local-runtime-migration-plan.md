# Local Runtime Migration Execution Plan

This is the execution roadmap for moving `material-agent` from a service-free
heuristic baseline to a benchmarked local-model production path.

## Outcome

The target is a NAS-first scoring pipeline that:

- runs without an HTTP model service;
- produces useful group ranking, rejection, scene, and portrait signals;
- uses native OpenVINO on supported Intel hosts and a tested CPU fallback;
- keeps XMP and SQLite output compatible across upgrades;
- treats the old `material-judge` VLM as an optional teacher and comparison
  baseline, not a production dependency.

The current heuristic client remains the fallback until a learned stack clears
the quality and operational gates below. Declaring `inference.runtime` is not
equivalent to running model inference; score payloads and runtime events must
identify the implementation that actually produced a result.

## Delivery Principles

- Benchmark before changing the default score policy.
- Add one independently measurable model block at a time.
- Keep model loading, inference, score calibration, and orchestration behind
  separate boundaries.
- Preserve CPU execution and clean model-skip behavior at every milestone.
- Keep destructive writes out of benchmark workflows.
- Promote models from fixed-fixture evidence, not isolated score examples.
- Do not delete legacy code until equivalent diagnostics and rollback paths
  exist.

## Success Measures

Every benchmark report must record:

- group top-1 accuracy or agreement;
- pairwise preference accuracy;
- reject false-negative rate;
- screenshot/non-photo rejection;
- scene/category calibration and `other` rate;
- face-positive recall on the maintained fixture set;
- p50 and p95 latency, images per minute, and peak RSS;
- model load time, fallback rate, and per-model failure count;
- runtime, device, model version, configuration digest, and fixture-set version.

Initial promotion thresholds should be recorded with the fixture labels rather
than hard-coded prematurely. The non-negotiable gates are no XMP regression,
no increase in destructive false rejects, deterministic report reproduction,
and a working CPU fallback.

## Critical Path

```text
runtime guardrails
  -> repeatable benchmark and labeled fixtures
  -> semantic scene vertical slice
  -> quality and aesthetic stack
  -> calibrated score policy
  -> native OpenVINO execution
  -> read-only comparison and isolated write pilot
  -> default-path promotion
  -> legacy quarantine
```

High-resolution ROI focus, GUI work, teacher-student training, and commentary
generation are not on this critical path.

## Milestone 0: Runtime Guardrails

Status: substantially complete in the current working tree.

Deliverables:

- report-only local runtime preflight;
- explicit local commentary rejection during config validation;
- accurate backend validation messages;
- normalized `inference.*` passed into local backend construction;
- score provenance that states when heuristic scoring remains active.

Exit gate:

- the default config runs without optional model packages or HTTP services;
- runtime events report package and device availability;
- tests cover config propagation and unavailable-runtime behavior;
- documentation does not describe a configured provider as active inference.

## Milestone 1: Repeatable Benchmark Foundation

Goal: make scoring changes measurable before changing production behavior.

Status: complete for the maintained synthetic regression foundation. A broader
real-camera set remains a promotion requirement in Milestone 5.

Deliverables:

- a report-only benchmark command or script with no XMP writes;
- versioned fixture manifests covering near-duplicate groups, low light,
  obvious blur, screenshots, face-positive portraits, and ordinary photos;
- human labels for group top-1, pairwise preference, reject safety, scene, and
  face presence;
- JSON results as the machine-readable source and a generated Markdown summary;
- heuristic baseline results on CPU;
- optional `material-judge` VLM comparison results stored separately as teacher
  evidence.

Important semantics:

- the existing `--dry-run` prevents XMP and processed-result writes, but still
  records sessions, jobs, job files, artifacts, and events in runtime SQLite;
- the benchmark harness should use an isolated work directory or an explicit
  report database so repeated experiments cannot affect production resumability;
- fixture images and derived reports must follow repository privacy and Git
  size rules.

Exit gate:

- one command reproduces a report on a CPU-only machine;
- reports contain provenance and all required success measures;
- fixture labels are reviewed and versioned;
- two consecutive runs with the same inputs produce equivalent decisions and
  rankings within documented numerical tolerance.

## Milestone 2: Semantic Scene Vertical Slice

Goal: remove the largest structural weakness of the heuristic path: every image
being reported as `scene=other`.

Status: implemented and CPU-verified with MobileCLIP2-S0/OpenCLIP on the
synthetic v1 fixtures. It remains opt-in pending broader scene calibration.

Deliverables:

- a local model port and model lifecycle boundary independent of the client;
- MobileCLIP2-S0 as the preferred semantic candidate, with MobileCLIP-S1 as the
  documented fallback candidate;
- bounded preview preprocessing shared by benchmark and production adapters;
- scene labels, confidence, model identity, runtime, and fallback reason in the
  score payload;
- a clean heuristic fallback when weights or runtime packages are unavailable;
- benchmark comparison against the Milestone 1 baseline.

Exit gate:

- maintained fixtures no longer collapse to `other`;
- scene errors do not cause a batch failure when fallback is allowed;
- scene-aware scoring improves the accepted benchmark measures without a reject
  safety regression;
- cold-load and warm-inference costs are reported separately.

## Milestone 3: Quality And Aesthetic Stack

Goal: replace pseudo-precision derived from one heuristic feature set with
independently measured quality signals.

Status: all planned signal blocks are implemented and CPU-verified on the
synthetic v1 fixtures. Default score fusion is intentionally not promoted:
quality and aesthetic pairwise preference are only 2/3 because the UI fixture
outranks the low-light photo. Real-camera calibration remains open.

Delivery order:

1. BRISQUE/NIQE as fast reject priors, never sole final-rank signals.
2. MUSIQ as the primary no-reference quality baseline.
3. NIMA and CLIPIQA+ as measured aesthetic candidates.
4. DINOv2-small embeddings for similarity and group-ranking features.
5. MediaPipe Face Landmarker for portrait structure.

Each block must ship behind configuration and be benchmarked independently
before score fusion changes. Avoid adding all models to one release because it
would hide which model changed quality, memory, or throughput.

Exit gate:

- each signal records model/version/provenance and failure state;
- model failures degrade to a documented fallback instead of fabricating a
  learned score;
- score calibration is derived from fixtures and stored as a versioned policy;
- candidate promotion improves group-level metrics without increasing reject
  false negatives;
- peak memory and throughput remain within the selected NAS profile budget.

## Milestone 4: Native OpenVINO Runtime

Goal: make the Intel image execute real models rather than only report runtime
availability.

Status: native ONNX compile, inference, cache identity, model bundle
materialization, and actual CPU device readback are implemented and verified.
Target Intel GPU and `/dev/dri` validation remain open.

Deliverables:

- native OpenVINO model loader, compiled-model cache, and inference adapter;
- CPU and `AUTO:GPU,CPU` device selection with explicit readback;
- `/dev/dri` and OpenVINO device diagnostics in the Intel container;
- model-specific preprocessing and output parity tests across CPU and Intel;
- stable cache keys including model digest, precision, device, and OpenVINO
  version;
- diagnostic fallback events when GPU access or compilation fails.

Exit gate:

- Intel runs report the actual compiled device used;
- the same fixture report runs on CPU and Intel with decisions inside documented
  tolerance;
- missing Intel GPU access falls back or fails according to config, never
  silently masquerading as accelerated inference;
- cold start, warm throughput, peak RSS, and device utilization are recorded on
  the target NAS.

## Milestone 5: Production Pilot And Promotion

Goal: validate output safety and operational behavior before changing the
default scorer.

Rollout stages:

1. Run the benchmark harness against immutable fixtures.
2. Run read-only scoring on a copied real-world directory with an isolated DB.
3. Compare heuristic, learned local stack, and optional VLM teacher outputs.
4. Write XMP only into a copied sidecar directory and verify it with ExifTool
   and target applications.
5. Run a bounded real-directory pilot with sidecar and DB backups.
6. Promote the learned policy only after the acceptance report is approved.

Rollback points:

- restore sidecars for metadata rollback;
- restore the state database and config for state rollback;
- select heuristic mode for scoring rollback;
- return batch entrypoints to `material-judge` only as a temporary operational
  fallback during the migration window.

Exit gate:

- XMP compatibility checks pass with no proprietary RAW mutation;
- interrupted jobs resume without double writes or false `done` states;
- production pilot metrics meet the approved benchmark thresholds;
- operator documentation covers model installation, cache cleanup, diagnostics,
  backup, and rollback.

## Milestone 6: Legacy Quarantine

Goal: make the supported local path obvious and reduce maintenance cost.

Status: operational quarantine is complete. Legacy backends require an
explicit config gate, do not appear in the CLI, and are no longer re-exported
from the commands package. Physical module deletion remains deferred until the
teacher-tool retention decision and deprecation inventory are complete.

Deliverables:

- legacy OMLX/Ollama modules moved behind explicit compatibility or teacher
  tooling boundaries;
- default tests and docs no longer require legacy transports;
- retained teacher commands use isolated config and state;
- obsolete commands, tests, and runbooks removed only after a deprecation
  inventory is reviewed.

Exit gate:

- a new contributor can trace the default local scoring path without entering
  legacy modules;
- no default CLI or container depends on an HTTP model service;
- teacher tooling can be removed later without changing production interfaces.

## Parallel And Deferred Tracks

Safe to pursue in parallel after Milestone 1:

- XMP compatibility tests and fixture expansion;
- runtime schema and provenance improvements;
- target-NAS device inventory and container diagnostics;
- documentation and operator runbooks.

Deferred until the main stack is benchmarked:

- candidate-only high-resolution ROI focus confirmation;
- a GUI or multi-writer runtime;
- local commentary generation;
- teacher-student training or a learned ranking head;
- NVIDIA, AMD, and native Apple production profiles.

## Near-Term Work Packages

The next bounded sessions should be:

1. Define the benchmark artifact schema and fixture manifest format.
2. Implement the isolated report-only heuristic baseline command.
3. Add and label the minimum fixture set, including a true face-positive group.
4. Produce the first reproducible baseline report.
5. Write the semantic model port contract and MobileCLIP2 adapter spike.

Do not begin score fusion or OpenVINO model conversion before work packages 1-4
are complete.

The manifest contract starts at
`docs/ai/templates/local-benchmark-manifest.yaml`. Run the isolated heuristic
baseline with:

```bash
uv run material-agent benchmark-local \
  --manifest /path/to/fixture-set/manifest.yaml \
  --output-dir /path/to/benchmark-output \
  --repeat-count 2
```
