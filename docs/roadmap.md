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
- implemented a real learned aesthetic path with pinned NIMA MobileNet/AVA,
  OpenVINO CPU/GPU execution provenance, batched review-window priming, and
  direct ownership of the layered policy's aesthetic total; disabled the
  unused default DINO execution while keeping embedding grouping opt-in
- added a lightweight target-first focus path: OpenVINO SSD MobileNet V1 object
  detection, OpenCV YuNet face/eye landmarks, a catastrophic global-blur guard,
  subject/eye ROI focus scoring, and spectral-residual saliency fallback without
  YOLO, CLIP, Torch, TensorFlow, or MediaPipe in the Intel image
- added versioned target/scene NIMA calibration with human-label affine fitting,
  minimum-label no-op safeguards, detector-confidence blending, raw/effective
  score provenance, and scene-safe rescore support
- added checksum-pinned model catalog operations, appdata-backed install/select/
  delete state, CLI plus authenticated HTTP management endpoints, and immutable
  bundled-model protection
- added an appdata-only human aesthetic label store with idempotent import,
  deterministic train/holdout splits, export, and coverage statistics without
  creating synthetic preference labels
- completed the target Unraid NIMA CPU/GPU batch 1/4/8 matrix on 128 read-only
  RAW files, verified actual `GPU.0` execution and no fallback, and retained CPU
  batch 1 as the production default because neither device had a stable material
  throughput advantage while GPU startup and memory costs were substantially
  higher
- added the built-in bearer-protected Web operator surface for configuration,
  checksum-pinned model lifecycle, full-library indexing, dry-run task control,
  logs, thumbnail browsing, filtering, and complete score/tag/description
  payload inspection without source-library writes
- persisted DB-only `output_preview` fields after group ranking so dry-run
  library details include the exact proposed rating, machine tags,
  instructions, description, and group metadata without invoking an XMP write
- added a generation-based full-library index in the appdata runtime database;
  validation is no longer structurally limited to the earlier 128/512-file
  performance samples
- integrated opt-in embedding similarity into adjacent-group merging with a
  content-addressed dedicated vector cache, pHash-first evaluation, shared
  client result reuse, and no raw vectors in ordinary score artifacts
- completed MobileCLIP2 as an optional semantic profile and retained the
  lightweight SSD/YuNet/NIMA Intel stack as the production default; broader
  prompt promotion is evidence-gated rather than an unfinished runtime feature
- completed the staged local-runtime migration and retained legacy OMLX/Ollama
  only behind the explicit teacher/compatibility gate
- replaced per-file SQLite commits and per-singleton stage churn with bounded
  transaction batching, indexed artifact aggregation, and commentary-disabled
  coroutine elision for whole-library result persistence
- completed the post-fix 40,620-file Unraid dry-run in 5,683 seconds
  (7.148 files/second): task exit code 0, 40,620 scored, zero errors, zero
  source XMP/state writes, DB/log state under `/config`, and `/photos` read-only
- normalized the 1,455 Mac-imported ARWs from private `0700/gid20` metadata to
  `users` group-readable access using the checksum-verified import receipt;
  non-root rawpy decoding and the subsequent full-library run both passed

## In Progress

- none outside the explicitly deferred human-review and XMP promotion gates

## Next

- none outside the explicitly deferred human-review and XMP promotion gates

## Later

- optionally add true sensor-resolution RAW ROI decoding for ambiguous
  candidates; the current subject/eye pass uses a bounded 2048-edge preview
- remove copied OMLX/Ollama modules after the remaining deprecation inventory
  and teacher-tool retention decision
- use the old VLM as optional teacher data for a small ranking/regression head
- add NVIDIA CUDA image tag
- investigate AMD MIGraphX image tag on supported ROCm hardware
- add native Apple Silicon install profile using CoreML, MLX, or MPS
- evaluate Docker Model Runner as an optional Apple host-service bridge
- extend the local label store to keep/review/reject and pairwise group
  preferences when a real review workflow is available
- compare whole-frame NIMA against subject-crop fusion only after target labels
  can support an independent holdout ablation
- train a small ranking/regression head on frozen embeddings only after enough
  reviewed labels exist

Hardware-specific CUDA, ROCm/MIGraphX, and native Apple profiles may be
implemented and CI-smoked without target devices, but cannot be marked
production-verified until matching hardware is available. XMP promotion also
remains separately authorized and is not part of Web-triggered tasks.

## Deferred Or Not In Scope

- collect independent human aesthetic labels, review whole-share outliers, and
  fit non-identity target calibration profiles; generic AVA NIMA is accepted
  for phase one at the user's direction
- promote XMP writes on the primary Unraid library; Web tasks remain dry-run
  and the photo mount remains read-only until separately authorized
- making Ollama or OMLX a required dependency again
- building one giant Docker image that includes every vendor runtime
- training a full visual backbone from scratch
- depending on Apple Metal GPU passthrough inside a normal Linux container
