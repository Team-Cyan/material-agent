# Roadmap

## Completed

- forked `material-agent` from `material-judge`
- renamed the Python package, CLI, launcher names, and runtime work directory
- switched the default config to `backend: local`
- removed Ollama and OMLX from the default user-facing setup path
- added a local heuristic backend so the pipeline can run without a model server
- moved the project to Python 3.14 and the shared Python 3.14 + uv Docker base
- added CPU and Intel OpenVINO Dockerfile entrypoints
- documented the default local model stack and candidate backlog
- added a report-only local runtime preflight and local commentary guardrails
- completed a fixed-sample screening pass for DINOv3 ONNX, MobileCLIP2-S2,
  SigLIP2, CLIPIQA+, BRISQUE/NIQE, PAQ2PIQ, TOPIQ_NR, and heavier IQA
  candidates
- changed RAW preview scoring to prefer camera-embedded previews and avoid
  copying full RAW pixel buffers in the default path
- hardened XMP sidecar rating output for Lightroom/Photomator-style workflows:
  sidecar-only writes, ExifTool-readable `xmp:Rating`, `.xmp`/`.XMP` update
  preservation, and machine tags stored outside normal user keywords
- added an isolated, versioned `benchmark-local` harness with maintained
  synthetic fixtures and durable heuristic/MobileCLIP2 CPU reports
- implemented the first learned semantic vertical slice with MobileCLIP2-S0,
  lazy OpenCLIP loading, clean fallback, and actual-runtime provenance
- implemented and CPU-verified optional BRISQUE/NIQE, MUSIQ, NIMA, CLIPIQA+,
  DINOv2-small, and MediaPipe Face Landmarker signal blocks
- implemented native OpenVINO ONNX embedding, self-contained model bundle
  materialization, compiled cache identity, and actual execution-device readback
- deployed the Intel OpenVINO image through Unraid DockerMan and completed a
  bounded ten-file read-only pilot with ten OpenVINO embeddings executed on
  `GPU.0`, appdata-backed SQLite/log state, and zero source-side XMP writes
- quarantined OMLX/Ollama behind an explicit compatibility gate and removed
  legacy runtime helpers from the default command surface
- added RAW input support to the isolated benchmark and completed the first
  five-calibration/five-holdout Sony A7C II concert-burst evaluation
- completed an isolated five-file XMP pilot with source hash verification and
  no writes to the original holdout directory
- completed a whole-project correctness and deployment hardening pass covering
  dry-run isolation, provenance-safe score reuse, stable incremental grouping,
  cancellation/recovery, and one mutating controller per work directory
- made AI reset provenance-safe: source XMP is preserved by default, explicit
  cleanup removes machine tags, and user-modified scalar fields are retained
- made score and embedding cache identity content-addressed across policy,
  grouping, preview/preprocessing, model bundle assets, optional package
  versions, and explicit semantic revision markers
- shipped a non-root PUID/PGID Intel image contract with a baked DINOv3
  OpenVINO profile, appdata-only runtime state, `/dev/dri` group handling, and
  explicit AUTO-versus-manual-fallback provenance
- hardened immutable image publication so quality checks and built-image smoke
  tests pass before the mutable Intel tag is promoted
- corrected the local benchmark to clear per-image result cache between
  repetitions and recorded a replacement OpenVINO CPU synthetic report
- replaced one-image synchronous OpenVINO embedding with bounded review-window
  priming across original group boundaries, `AsyncInferQueue`, configurable
  batch 1/4/8 and request pools,
  fixed-reshape plus native auto-batch strategies, throughput hints,
  optimal-request readback, batch fallback provenance, and
  RAW/heuristic/preprocess/inference/postprocess/compile stage timing
- completed the target Unraid 128-RAW CPU/GPU batch 1/4/8 cold/warm matrix and
  a 512-RAW sustained run; selected CPU batch 1 with eight asynchronous requests
  because it delivered 6.737 warm files/second versus 0.496 on `GPU.0`

## In Progress

- expand the initial private concert-burst RAW gate with independent scenes,
  cameras, and lighting before production model promotion
- keep MobileCLIP2 semantic scoring opt-in while scene prompts and confidence
  are calibrated on broader real-photo coverage
- keep quality/aesthetic signals out of default fusion after the maintained UI
  fixture exposed a non-photo false positive
- integrate benchmarked embeddings into grouping without duplicating model
  inference or persisting raw vectors in ordinary score artifacts
- keep XMP sidecar and SQLite persistence compatible with Lightroom-style RAW
  workflows while avoiding direct proprietary RAW mutation
- follow `docs/operations/2026-07-01-local-runtime-migration-plan.md` for the staged local-runtime migration

## Next

- calibrate a versioned score policy only after per-block benchmark reports exist
- add optional target-host utilization sampling to future model benchmarks;
  CPU/GPU parity, steady-state throughput, fallback provenance, and the
  deployment default are now resolved for the bundled DINOv3 model
- publish the hardened image, then repeat the bounded Unraid read-only pilot
  with non-root UID/GID and appdata ownership checks
- run a separately authorized target-host isolated-XMP pilot before changing
  the default learned scoring policy; keep the primary photo share read-only

## Later

- add a candidate-only high-resolution ROI focus pass for group top-N or
  ambiguous images, then promote `portrait_face_eye` from experimental config
- remove copied OMLX/Ollama modules after the remaining deprecation inventory
  and teacher-tool retention decision
- use the old VLM as optional teacher data for a small ranking/regression head
- add NVIDIA CUDA image tag
- investigate AMD MIGraphX image tag on supported ROCm hardware
- add native Apple Silicon install profile using CoreML, MLX, or MPS
- evaluate Docker Model Runner as an optional Apple host-service bridge
- add a local label store for keep/review/reject and pairwise group preferences
- train a small ranking/regression head on frozen embeddings only after enough
  reviewed labels exist

## Deferred Or Not In Scope

- making Ollama or OMLX a required dependency again
- building one giant Docker image that includes every vendor runtime
- training a full visual backbone from scratch
- depending on Apple Metal GPU passthrough inside a normal Linux container
