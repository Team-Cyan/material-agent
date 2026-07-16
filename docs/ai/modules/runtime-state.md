# Runtime State Module Contract

## Purpose

This module persists runtime progress and processed review results into SQLite.

It uses one runtime database path but models two different concerns:

- runtime execution state
- processed review results and caches

## Main Files

- `src/material_agent/adapters/state/sqlite_runtime.py`
- `src/material_agent/adapters/state/processed_sqlite.py`
- `tests/test_runtime_state.py`
- `tests/test_state.py`

## Responsibilities

### `SQLiteRuntimeRepository`

- store sessions, jobs, job files, artifacts, and events
- support resumability and GUI-ready runtime introspection

### `SQLiteProcessedRepository`

- store scored and done review results
- store EXIF cache
- store policy signals for later rescore
- store versioned file fingerprints, score/output cache identity, terminal
  commentary/group metadata, and the exact scalar XMP fields last written by AI
- support rewrite and maintenance flows

## Non-Goals

- scoring policy definition
- commentary text generation
- CLI dispatch
- model transport

## Inputs

- normalized score payloads
- runtime lifecycle transitions
- EXIF cache values
- rescore updates

## Outputs

- durable SQLite rows for runtime and processed-state consumers

## Invariants

- runtime tables and processed tables must remain readable across reruns
- write operations should be idempotent where practical
- resumability depends on stable status meanings such as `scored`, `done`, and `written`
- signal rows must stay compatible with rescore logic
- cached score reuse requires both a current size+mtime fingerprint and the
  current score/output cache key; `reprocess` bypasses score reuse explicitly
- a recovered score payload must retain runtime/model provenance, commentary,
  signals, and group metadata rather than reconstructing a lossy subset
- raw embedding vectors must not be serialized into ordinary score metadata or
  benchmark artifacts
- XMP cleanup may use the stored scalar payload only as an ownership guard: a
  scalar field changed by the user after AI write-back must be preserved
- runtime DB, sidecars, lock, and log files are private (`0600`); config
  snapshots recursively redact credentials and tokens
- startup reconciliation converts abandoned open/running sessions and
  queued/running/paused jobs into a durable cancelled terminal state
- review jobs coalesce chatty runtime commits into bounded batches, while
  non-job repository calls retain immediate commit semantics
- artifact lookups must keep indexes for both `(job_file_id, kind)` and
  `(job_id, kind)`; final timing aggregation reads one job-wide artifact batch
  instead of issuing one unindexed query per file
- when `MATERIAL_AGENT_WORK_DIR` is set, both repositories and logs stay in that
  directory; Docker deployments should bind `/config` to appdata and never put
  the main DB in the read-only photo source

## Typical Safe Changes

- add one new runtime artifact kind
- add one new payload metadata field
- improve reconnect or disk-I/O recovery behavior
- add a helper query used by one maintenance flow

## Risky Changes

- changing status meanings
- changing processed column names without updating rewrite/rescore paths
- changing bootstrapping DDL without checking existing migrations and tests
- mixing runtime-state concepts with processed-state concepts more than they already are
- weakening fingerprint/cache-key validation or dropping provenance fields from
  cached payload reconstruction
- clearing user-visible XMP scalar fields without a stored ownership match
- writing secrets or permissive runtime files into config snapshots/appdata

## Files Usually Safe To Edit Together

- `src/material_agent/adapters/state/sqlite_runtime.py`
- `src/material_agent/adapters/state/processed_sqlite.py`
- `src/material_agent/app/rescore_service.py`
- `tests/test_runtime_state.py`
- `tests/test_state.py`
- `tests/test_rescore.py`

## Minimal Verification

- `pytest tests/test_runtime_state.py tests/test_state.py tests/test_rescore.py`

## Known Tensions / Technical Debt

- Two repositories share the same underlying runtime database path while representing different abstractions, which is efficient but cognitively heavy.
- Schema evolution currently leans on bootstrap-time `ALTER TABLE` attempts instead of an explicit migration system.
- Status semantics are spread across orchestration, runtime state, and processed state, so bugs can hide in cross-repository assumptions.
