# Batched self-review and local commit record

The user authorized recording, reviewing, refining and committing the current
implementation in batches. This authorization does not include push, deployment,
production review or photo/XMP filesystem writes.

## Starting evidence and scope

Before staging, `.local/review-2026-09-16/` captured the starting HEAD/status,
complete tracked patch and copies of untracked files. The index was empty.
The 15 pre-existing guidance-file changes recorded by the original inference
session are excluded from these commits and preserved byte for byte.
Datasets, model weights, virtual environments and generated raw reports remain
ignored local data. Shared wiring files were staged by functional patch hunk.

## Batch review

| Batch | Review focus / refinement | Commit |
| --- | --- | --- |
| Native inference | Shared compile/request lifecycle, partial batches, output association, fallback/device provenance, cache identity and timing. Found that a missing XML companion installed later could leave an unchanged graph's asset snapshot stale; unavailable snapshots now retry discovery, with a regression test. | `1d76f1e` |
| MobileCLIP | One ordered text bank, bounded retention, concurrent initialization/inference, failed-encode retry and exact probability parity. Reviewed benchmark isolation, fixed inputs/prompts and stop-budget reporting. No further model/prompt change. | `f9143b2` |
| Grouping | Reviewed both entrypoints, adjacent time AND hash, zero bypass, missing evidence, legacy normalization, CLI override, caches and removal of embedding/cross-gap merges. Updated the review checklist to the superseding user design. | `1d6832e` |
| XMP projection | Reviewed rating preservation, malformed/duplicate declarations, exact keyword ownership, new/existing paths and ordinary-write ownership receipts. Added conflicting-decision coverage and real ExifTool readback from stdin; no sidecar was written. | `a6dace5` |
| Documentation | Record current contracts, completed gates, measured model evidence, superseded grouping requirements and the unfinished broader product plan. Do not promote local tests into professional-software or production acceptance. | This documentation commit |

## Verification after refinement

- `make check`: passed.
- Full guarded regression: **706 passed, 102 skipped in 21.18 s**.
  Command: `PYTHONPATH="$PWD/tests" PYTEST_PLUGINS=inference_readonly_guard uv run --no-sync pytest -q tests --tb=short`.
  Log: `.local/review-2026-09-16/final-tests.log`.
- Isolated model environment: **15 passed in 0.82 s** for OpenCLIP cache,
  semantic integration and experiment safeguards.
- Focused inference lifecycle tests: **14 passed**; XMP in-memory/command/readback
  tests: **38 passed**.
- Each staged batch passed `git diff --cached --check` before commit.
- The ExifTool test used read-only `-j -Rating -Subject -Identifier -` with an
  in-memory packet supplied through stdin. It verifies packet readability,
  not an existing-file mutation or a professional-software round trip.

Skipped tests remain unverified through their media/XMP writes; optional missing
dependencies also account for skips. No repeated benchmark tuning or production
run was used to clear this review. Existing actual-weight parity and fixed
200-image MobileCLIP comparison remain the numerical evidence for those paths.

## Remaining work

See [the audited plan status](2026-09-16-plan-status.md). These commits do not
complete per-group fallback/persistence, the full metadata import/rewrite ledger,
selective refinement, blinded GPT acceptance, other candidate model experiments
or professional-software/target-host validation. No push or release is implied.
