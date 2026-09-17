# Session Handoff

## Repository State

- `material-agent` is a public, application-focused repository.
- `docs/ai/` is the canonical AI knowledge base.
- `.agents/` contains thin repository-local navigation and harness assets.
- Runtime secrets, host profiles, deployment receipts, and operator snapshots
  must remain in ignored local storage or an external operations repository.

## Current Focus

The current local work is tracked in [the audited full-plan status](2026-09-16-plan-status.md).
Phase 1 inference unification, the first MobileCLIP comparison and the revised
time/hash grouping are implemented. Continuation batches implement readable-group
keep coverage with separate quality/selection persistence, XMP projection-attempt
ledger/rewrite receipts, and explicit evidence applicability plus opt-in bounded
refinement. The expanded [100-frame holdout](benchmarks/2026-09-17-hdrplus-holdout/report.md)
ran TOPIQ, MUSIQ, MediaPipe and optional refinement without promotion. A completed
20/20 blind groups; B completed 17/20 and hit quota again on the replacement
agent. Resume B groups 18–20 without reading A/score evidence. Only seven strict
pairs are currently order-stable, below the frozen minimum of 30. Do not fit
thresholds to these unstable proxy judgments. Refinement has 18 completed
larger-focus observations but no proven ranking benefit; it remains disabled.
RAW hashing without embedded thumbnails is fixed in accad08. Latest guarded
suite: 745 passed, 102 skipped. Context-supported not_applicable still lacks a
local producer. The [real exposure counterexample](benchmarks/2026-09-17-exposure-brackets/report.md)
shows a 0.34-second pair splitting at default hash threshold 10 (distance 24),
then singleton coverage keeps a quality-reject. No threshold/exception change
was made; an exposure-specific policy choice and a balanced negative control
set remain outstanding. The external acceptance plan is prepared separately.
XMP protection/projection has local in-memory verification;
no actual XMP write, deployment or production review is authorized in this session.

## Maintained Runtime Boundary

- The production path is local inference with CPU fallback and optional Intel
  OpenVINO acceleration.
- Web-started scoring remains dry-run and keeps runtime state outside the
  read-only photo mount.
- Generic Docker and Unraid deployment templates may live here because they
  define the application's container contract.
- Host discovery, SSH, DockerMan or ComposeMan control, image deployment,
  backup and restore, Home Assistant, router, and proxy operations do not
  belong here. Those workflows must be owned by a separate private controller.

## Durable Verification Evidence

- The repository test suite covers scoring, grouping, SQLite state, Web path
  confinement, model identity, XMP preservation, and local runtime fallback.
- Sanitized benchmark reports under `docs/operations/benchmarks/` record the
  CPU/GPU selection evidence without requiring a specific private host profile.
- Full-library dry-run validation completed on a 40k-plus photo corpus with no
  source XMP or runtime-state writes.
- The application-owned `review-scores` command reads SQLite in read-only mode,
  reconstructs bounded scoring previews, and writes private review artifacts
  outside the photo input tree.

## Next Work

Follow the ordered backlog in the audited status. Preserve the user's latest
adjacent time AND hash grouping rule (threshold 0 means time only). Historical
semantic substitutability rules no longer gate grouping. Keep source photos and
XMP read-only, and do not resume the historical production review/deployment
workflow merely because older evidence below or elsewhere mentions it.

Exposure ablation: grayscale histogram-equalized pHash reduces the known bracket
distance 24 -> 4; all 200 same-event pairs pass at threshold 10 and no matches
occur in 450 easy different-event controls (only 18 distinct event pairs).
Current pHash at threshold 24 matches 50/450 negatives. Do not raise the default
from this fixture. Before implementing normalized hashing, obtain labeled rapid
same-background/different-action or dish negatives and clipped controls; version
the persisted hash-cache identity and preserve zero-threshold no-read behavior.
The candidate remains offline only; see the exposure report and raw ablation.

The new [synthetic hard-case report](benchmarks/2026-09-17-hash-hardcases/report.md)
and runnable script cover 192 derived pairs with final keep/reject. Equalized
pHash improves holdout brightness splits (16 -> 12 of 48) but still merges 11/24
central-content changes and loses one distinct original through reject. Uniform
detail-loss cases all split and receive singleton coverage keep. Keep production
unchanged; natural same-background action/dish changes and more real exposure
sequences remain missing. Synthetic origin labels are not photographic truth.
