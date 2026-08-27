# Session Handoff

## Repository State

- `material-agent` is a public, application-focused repository.
- `docs/ai/` is the canonical AI knowledge base.
- `.agents/` contains thin repository-local navigation and harness assets.
- Runtime secrets, host profiles, deployment receipts, and operator snapshots
  must remain in ignored local storage or an external operations repository.

## Current Focus

The local scoring runtime, grouping pipeline, Web operator, model management,
and full-library dry-run path are implemented. The remaining product work is
limited to real preference-label calibration, Capture One interoperability,
and separately authorized XMP promotion.

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

1. Review grouping-enabled score/photo outliers with `review-scores`.
2. Compare group-size and rank distributions with the singleton baseline.
3. Keep deployment and NAS mutations outside this repository and require
   separate operator authorization.
