# Whole-Project Review and Repair Record

Date: 2026-07-13

## Objective

Review the complete production surface, turn every reproducible finding into a
bounded repair, and leave a release path that protects the photo source, runtime
state, model provenance, and Intel deployment contract.

The review covered CLI/config validation, orchestration, incremental grouping,
processed/runtime SQLite, XMP ownership, cancellation, model/cache identity,
OpenVINO execution, Docker entrypoints, dependency shape, and image publication.
Historical OMLX code was reviewed where it can still be invoked as an explicit
teacher/compatibility path; it remains outside the default runtime.

## Repair Plan

| Phase | Acceptance condition | Status |
| --- | --- | --- |
| 1. Source and state safety | Dry-run cannot write XMP/rating or new processed results; AI reset cannot erase user-owned scalar metadata | Complete |
| 2. Incremental correctness | Complete current source set participates in grouping; score reuse preserves provenance; group/rank changes refresh terminal output | Complete |
| 3. Controller lifecycle | One mutating controller per work directory; abandoned work reconciles; SIGTERM becomes durable cancellation | Complete |
| 4. Runtime and model identity | Cache keys cover effective policy, package/model/preprocess identity; OpenVINO reports actual execution and explicit fallback | Complete |
| 5. Container and publication | Non-root scoring, appdata-only writable state, safe PUID/PGID migration, immutable smoke-before-promotion workflow | Complete in code and workflow |
| 6. Verification and handoff | Full local gate, corrected benchmark, risk re-audit, roadmap/runbook updates | Complete locally |

GitHub's immutable-image build/smoke gate remains the publication acceptance
test after push. A controlled Unraid read-only rerun remains target-host
validation, not unfinished source repair.

## Findings and Resolutions

### State, dry-run, and XMP

| ID | Risk | Finding | Resolution |
| --- | --- | --- | --- |
| F-01 | P1 | Dry-run could blur simulated work, processed cache writes, and real terminal writes | Dry-run now records runtime observability only. New score/`done` rows and XMP/rating writes are suppressed; unchanged cached `done` rows are `skipped`, newly simulated results are `simulated` |
| F-02 | P1 | Cached score reconstruction could lose model/commentary/group provenance or survive an incompatible policy change | Processed payloads now preserve full score metadata and validate size+mtime plus a versioned score/output cache key; `reprocess` bypasses reuse |
| F-03 | P1 | Filtering completed files before grouping made later burst additions produce inconsistent group membership/rank | Grouping receives the complete source set; stable group IDs derive from sorted members; cached scores are reused while changed group/rank terminal output is refreshed |
| F-04 | P1 | Reset could treat current user-visible XMP scalar fields as AI-owned | XMP is preserved unless `--clear-xmp` is explicit. Machine tags are removable, while rating/instructions/description clear only when they still match the exact last AI payload; legacy rows preserve scalars |
| F-05 | P2 | File and model cache identity was incomplete, and raw embedding vectors could leak into ordinary metadata | Processed cache keys now cover effective scoring/grouping/preview/XMP/model configuration and enabled package versions; embedding identity covers every bundle asset and preprocessing revision; raw vectors are stripped from normal metadata |

### Lifecycle, CLI, and security

| ID | Risk | Finding | Resolution |
| --- | --- | --- | --- |
| F-06 | P1 | Concurrent mutating commands and interrupted runs could leave conflicting writers or misleading active state | `run`, the legacy pipeline, and mutating maintenance commands share a hardened exclusive lock; startup reconciles abandoned session/job states; SIGTERM raises a cancellation type outside normal exception handling and persists `cancelled` |
| F-07 | P2 | Empty/missing inputs, malformed or abbreviated CLI/config input, extension abuse, partial failures, and rewrite errors were not consistently fatal | Input discovery happens before runtime writes, long-option abbreviation is disabled, empty input requires `--allow-empty`, mappings/extensions/prefetch bounds are validated, and failed/partial/cancelled maintenance or run outcomes return nonzero |
| F-08 | P1 | Runtime and legacy-harness config snapshots plus dedicated compatibility processes could expose sensitive material | Runtime DB sidecars/log/lock files use private modes; both snapshot paths share recursive credential redaction; the run lock and container appdata paths reject symlinks; dedicated OMLX startup refuses an auth configuration that would expose a key in process arguments |
| F-09 | P2 | External helper work could hang, and the legacy `Pipeline` path had drifted from the main controller contract | MUSIQ helper calls are bounded by timeout; the legacy path now uses the same complete-source, cache-key, lock, reconciliation, cancellation, close, and partial-result semantics |

### OpenVINO, Docker, and release engineering

| ID | Risk | Finding | Resolution |
| --- | --- | --- | --- |
| F-10 | P1 | ONNX external-data references and incomplete bundle hashing allowed unsafe paths or stale compiled artifacts | External-data paths must stay inside the bundle; graph, all external files, processor assets, runtime settings, and preprocessing identity participate in the digest/cache key |
| F-11 | P1 | Requested device could be mistaken for actual execution, and fallback behavior was underspecified | Strict compile/readback records requested, compiled, fallback, fallback reason, and actual execution devices. OpenVINO AUTO selection is distinct from application-level fallback; unknown readback stays unknown |
| F-12 | P2 | Benchmark repetitions reused per-image embedding results, making the old warm timing invalid | The result cache is bounded and explicitly cleared before each repetition. The corrected v2 CPU report executes real inference on every repetition |
| F-13 | P1 | The Intel container could score as root, rely on an operator-supplied model config, leave mutable state in its ephemeral writable layer, or misidentify an option-ordered run/maintenance target before root-side preparation | The image bakes the checksum-pinned DINOv3 OpenVINO profile, uses `/config` for DB/log/cache, accepts PUID/PGID and `/dev/dri` groups, migrates only allowlisted appdata, fails closed on malformed run and `--dir` arguments, rejects unsafe work paths/symlinks, and drops to `material-agent` before scoring |
| F-14 | P1 | A mutable image could be promoted before the actual built artifact and entrypoint contract were tested | Actions/base/artifacts are pinned; quality uses the Intel dependency extra; the immutable digest is built and smoked through the real entrypoint, ownership migration, lean dependency, bundled model, AUTO execution, and forced GPU-to-CPU fallback before mutable-tag promotion |

## Verification Snapshot

Local gate after all repairs:

- `uv run pytest -q -rs`: **593 passed, 6 skipped**;
- the six skips are explicit opt-in live OMLX integration tests;
- `uv run ruff check .`: passed;
- `uv lock --check`: passed;
- `python -m compileall -q src`: passed;
- `git diff --check`: passed;
- `sh -n docker/entrypoint.sh`: passed;
- base config, Intel config, and workflow YAML parse: passed;
- main/run/reset/benchmark CLI help contracts: passed;
- source distribution and wheel build: passed;
- final independent blocker-level risk audit: no remaining reproducible P0/P1/P2 finding.

Docker is not installed on the local Apple verification host. The checked-in
workflow therefore owns the real Linux image build and immutable-image smoke;
the mutable tag cannot be promoted if either fails.

## Corrected OpenVINO CPU Benchmark

Report:
`docs/operations/benchmarks/2026-07-13-openvino-dinov3-quantized-cpu-synthetic-v2/`

- OpenVINO: 2026.2.1;
- actual execution: CPU;
- model bundle: DINOv3 ViT-S quantized ONNX, 384 dimensions;
- four synthetic fixtures, three repetitions, deterministic scores;
- cold four-image run: 1.561 seconds;
- warm p50 four-image run with real inference: 0.530 seconds;
- aggregate: 4.577 images/second.

The old v1 0.07-second warm result measured embedding result-cache hits and is
retained only as historical evidence of the benchmark defect.

## Remaining External Gates

These are deliberately not described as fixed or complete by the source patch:

1. Run the GitHub immutable-image build/smoke and promote only on success.
2. Redeploy the verified digest to Unraid and repeat the bounded read-only,
   dry-run audit with UID/GID, modes, appdata location, actual device, and zero
   source-write checks.
3. Measure warm CPU/GPU parity and Intel device utilization. The existing cold
   ten-file sample was CPU 28 seconds versus GPU 43 seconds and is too small and
   initialization-heavy for an acceleration conclusion.
4. Perform target-host sidecar writing only in an isolated copy and only after
   separate operator authorization. The primary photo share remains read-only.
5. Keep learned score fusion opt-in until broader independent photo labels and
   operator-reviewed thresholds meet the promotion gates.
