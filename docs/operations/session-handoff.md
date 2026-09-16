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
time/hash grouping are implemented. Automatic-preselection closure, evidence
applicability/refinement, metadata import/ledger and external acceptance are
not all complete. XMP protection/projection has local in-memory verification;
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
