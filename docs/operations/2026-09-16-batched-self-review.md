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

## Continuation batch: readable-group coverage

Reviewed the selection boundary separately from quality scoring. Replaced the
reason-free reject-to-review fallback with explicit keep coverage, including
all-defect and review-only groups. Numeric scores and stars remain untouched;
versioned quality/selection records persist in existing score metadata. Decode
errors and invalid scores cannot become fallback candidates. Stable tie breaking
and cached refinalization preserve the original quality decision.

Self-review found two integration needs: scene-filtered rescore must reconcile
selection against unchanged group members, and old terminal output caches must
be invalidated. Both are addressed; nonselected scenes retain scores/stars/ranks.
Read legacy metadata through tolerant JSON decoders and preserve existing runtime
provenance. Grouping and the compatibility fallback switch remain respected.

Verification: full guarded regression **710 passed, 102 skipped in 22.34 s**;
after adding processed-cache round-trip coverage and tolerant legacy reads,
focused scoring/job/pipeline/state tests **59 passed, 14 skipped**. `make check`
passed. Evidence: `.local/review-2026-09-16-coverage/tests.log` and original dirty
patch beside it. All-error and mixed-error group tests use virtual paths; cache
fingerprinting uses a text placeholder. No photo/XMP files were written.


## Continuation batch: XMP projection attempt ledger

Added versioned import/proposal/effective field snapshots and read-only preview,
with unknown source authorship. Only successful atomic replacement produces a
committed receipt. Review and rewrite persist attempts independently of processed
status; rewrite updates scalar ownership without claiming preserved ratings.
Self-review distinguished post-replacement persistence failure from filesystem
failure. No cross-resource transactional crash-recovery claim is made.

Verification: full guarded regression **718 passed, 102 skipped in 24.05 s**;
after one additional review failure/dry-run integration test, the focused XMP
suite reports **46 passed**. `make check` passed. Tests intercept copy/replace and
writer calls or use in-memory packets; the only filesystem test state is SQLite.
Log: `.local/review-2026-09-16-coverage/ledger-tests.log`. Professional-app and
physical-sidecar verification remains pending separately.

## Continuation batch: applicability and opt-in refinement

Eye evidence now distinguishes observed, unknown and context-supported
not-applicable. Generic low clarity is no longer an eye usability measurement,
including legacy rescore signals. One-pass refinement records triggers, original
scores/signals, attempt/time/size bounds, unresolved review requirements and
failure outcomes. Defaults remain disabled pending quality/latency acceptance.

The real-data self-review read six existing public RAW fixtures without writing
media: half-size RAW focus images were all smaller than or equal to the baseline
observation, while scores changed. Added a no-resolution-gain guard instead of
replacing evidence merely because its source says RAW. Source SHA-256 values were
unchanged. Decode-only timings were 0.014–0.069 seconds for the alternative path;
this is not end-to-end model latency or selection accuracy. Local report:
`.local/review-2026-09-16-coverage/raw-refinement.json`.

Full guarded suite: **736 passed, 102 skipped in 18.71 s**. After requiring an
explicit visual context evidence type, **17 focused tests passed**. `make check`
passed. Log: `.local/review-2026-09-16-coverage/evidence-final-tests.log`.

GPT acceptance preflight found no independent completion connector, supported API
credential/base URL environment, or local .env file. Existing data is either
single-image RAW format coverage, synthetic diagnostics, or action labels, not
burst preference truth. Do not present these tests as independent GPT acceptance.


## Acceptance preparation record

Frozen [rubric v1](evaluation/preselection-rubric-v1.json) and recorded
[data/channel preflight](2026-09-16-preselection-acceptance-preflight.md).
Reviewed against the current time/hash rule, separate quality/coverage, explicit
unknowns, event-disjoint holdout and independent order reversal. JSON parses and
its SHA-256 is recorded. No frozen image manifest or GPT result is claimed.
Photo Triage's official project page is task-relevant; its linked download host
failed both HTTPS and HTTP access. No remote image evaluation or download occurred.
The 15 original unrelated dirty files still match the starting patch byte for byte.
