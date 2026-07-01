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
