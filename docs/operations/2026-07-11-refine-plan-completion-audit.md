# Refine Plan Completion Audit

> Historical snapshot: the implementation and test counts below reflect the
> 2026-07-11 audit. The 2026-07-13 whole-project repair pass supersedes its
> runtime-state, Docker, CI, and benchmark-cache conclusions; see
> `2026-07-13-whole-project-review-fixes.md`. In particular, do not use the old
> OpenVINO synthetic v1 0.07-second warm timing as inference evidence.

This audit maps the acceptance conditions in
`2026-07-01-local-runtime-migration-plan.md` to current evidence. A milestone is
not marked complete from implementation intent alone.

## Milestone 0: Runtime Guardrails

Status: complete.

Evidence:

- local runtime preflight records package/device capability and heuristic state;
- strict availability raises before scoring;
- local commentary is rejected during config validation;
- configured runtime and actual runtime are recorded separately;
- full test suite covers preflight and config propagation.

## Milestone 1: Benchmark Foundation

Status: complete for regression infrastructure and initial real-camera coverage;
broader promotion coverage is intentionally carried into Milestone 5.

Evidence:

- `benchmark-local` uses a versioned manifest and explicit output directory;
- the benchmark never creates production runtime/processed repositories or XMP;
- maintained synthetic fixtures cover a sharp face-positive portrait, same-shot
  motion blur, severe low light, and a non-photo UI screenshot;
- repeated runs write JSON and Markdown with manifest digest, actual runtime,
  per-block provenance, cold/warm timings, and deterministic-score checks;
- durable reports live under `docs/operations/benchmarks/`.
- the harness decodes proprietary RAW inputs through the same embedded-preview
  path used by production and records preview source and dimensions without
  writing to the source directories;
- the first private real-camera set contains ten Sony A7C II ARW concert frames,
  split five calibration/five holdout.

## Milestone 2: Semantic Scene Slice

Status: implementation complete and CPU-verified; production promotion pending.

Evidence:

- MobileCLIP2-S0 loads lazily through OpenCLIP;
- missing dependencies/weights produce explicit fallback or strict failure;
- scene accuracy on synthetic v1 changes from 1/4 to 4/4;
- `other` rate changes from 4/4 to 1/4;
- actual runtime is reported as `open_clip:cpu`, not configured OpenVINO.
- the original prompt set classified all ten concert frames as `other`;
- adding a specific live-concert prompt produced 5/5 calibration and 5/5
  holdout scene accuracy while the maintained synthetic set remained 4/4.

Missing promotion evidence:

- broader independent scenes, cameras, and lighting conditions. The current
  holdout is temporally interleaved with the calibration burst and proves prompt
  transfer within that event, not general production accuracy.

## Milestone 3: Small-Model Stack

Status: model blocks and grouping integration complete; default score-fusion
promotion not achieved.

Evidence:

- BRISQUE/NIQE, MUSIQ, NIMA, CLIPIQA+, DINOv2-small, and MediaPipe Face
  Landmarker run through optional lazy adapters;
- reject priors, quality, and aesthetic roles use separate normalized outputs;
- DINOv2 same-group nearest-neighbor is 2/2 on synthetic v1;
- MediaPipe face recall is 2/2 and accuracy is 4/4;
- opt-in production grouping uses embedding boundary comparison after pHash miss;
- embedding vectors are cached by model key in SQLite and shared in memory with
  scoring, but are not persisted in reports or score metadata.

Contradicting promotion evidence:

- the UI fixture scores 65.8 with MUSIQ and 0.597 with CLIPIQA+;
- quality and aesthetic pairwise preference are only 2/3;
- reject-prior recall is 2/3 at the recorded benchmark threshold;
- enabling default fusion from this evidence would violate the reject-safety
  gate.
- on the real concert burst, DINOv2 finds a same-group nearest neighbour for
  10/10 frames, but MediaPipe detects 0/10 small, oblique, hair-occluded faces;
  the face block therefore remains unsuitable as a default portrait gate.

## Milestone 4: Native OpenVINO

Status: native CPU and target Intel GPU vertical slices complete; parity and
utilization acceptance incomplete.

Evidence:

- `prepare-openvino-model` materializes ONNX external data beside the graph;
- the bundle records a graph+data digest;
- native OpenVINO 2026.2.1 compiles and infers the standard-operator quantized
  DINOv3 ViT-S export;
- actual execution-device readback is `CPU` on the local verification host;
- compiled cache identity includes model digest, requested device, and OpenVINO
  version;
- a persistent compiled blob is produced and cross-process cold load improves;
- MHA Q4 is explicitly rejected because OpenVINO cannot convert
  `com.microsoft.MultiHeadAttention`.
- the published `intel-openvino` image at revision `54e7654` exposes the target
  Unraid host's `/dev/dri`, and OpenVINO 2026.2.1 reports `CPU` and `GPU`;
- a fresh ten-file run recorded ten model embeddings, ten native OpenVINO
  embeddings, and ten actual execution-device results on `GPU.0`.

Missing acceptance evidence:

- CPU/GPU parity and target-host utilization measurements.

## Milestone 5: Production Pilot

Status: isolated local pilot and target-host read-only pilot complete;
target-host sidecar-write validation remains intentionally incomplete.

Available evidence:

- XMP sidecar writer behavior, preservation, and ExifTool readability have unit
  and integration coverage;
- current live Unraid safe-read confirms host `OMNI` on an i7-11700T;
- the host has Docker but no host Python/uv, so validation must run in a
  purpose-built container;
- `material-agent` is installed as a DockerMan-managed one-shot container using
  `ghcr.io/team-cyan/material-agent:intel-openvino` at revision `54e7654`;
- the bounded target-host run finished 10/10 files with zero errors and stored
  its fresh database at `/config/state.db` under the appdata bind mount;
- `/mnt/user/material/photos` was mounted at `/photos` with `RW=false`, dry-run
  remained enabled, and the post-run audit found zero source-side XMP files and
  zero source-side `.material-agent` directories;
- runtime state and `run.log` stay in the writable `/config` appdata mount, not
  in the photo library;
- a five-file holdout copy completed both dry-run and real sidecar-write passes;
- all five copied ARWs were scored and ranked in one group, five XMP sidecars
  were ExifTool-readable, and SQLite recorded five successful rows;
- SHA-256 verification confirmed the source RAW files were unchanged and the
  original holdout directory still contained zero XMP files.

Required external inputs/actions:

- a target-host isolated sidecar-write run only after separate operator
  authorization; the current deployment must remain dry-run and read-only;
- CPU/GPU parity and utilization measurements;
- operator review of benchmark thresholds before default-model promotion.

## Milestone 6: Legacy Quarantine

Status: operational quarantine complete; physical deletion deferred by design.

Evidence:

- legacy backends require `legacy.enabled: true` during production config
  validation;
- OMLX/Ollama commands are absent from the CLI;
- the commands package no longer re-exports OMLX runtime helpers;
- legacy module docs identify teacher/compatibility scope and forbid fallback
  from local model failure.

Remaining decision:

- retain the teacher harness or delete the copied modules after a reviewed
  deprecation inventory.

## Verification Snapshot

- full suite: 469 passed and 13 skipped after the target-host pilot changes;
- focused RAW benchmark and semantic tests pass, including a mocked RAW decode
  regression and the maintained synthetic semantic gate;
- `uv run ruff check src tests`: passed;
- `git diff --check`: passed;
- real RAW heuristic repeat count 2 is deterministic at 6.88 images/second on
  the local Apple host; learned semantic+embedding+face repeat count 1 runs at
  0.95 images/second and records actual component runtimes.

The refine plan must remain active. Real-camera, isolated XMP, and target Intel
GPU read-only gates now have initial evidence, but missing CPU/GPU parity,
target-host sidecar-write evidence, and operator-approved score thresholds
prevent a defensible completion claim.
