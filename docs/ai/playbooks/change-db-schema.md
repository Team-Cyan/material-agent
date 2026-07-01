# Playbook: Change Runtime Or Processed DB Schema

Use this playbook when the task adds, renames, or changes SQLite-backed fields.

## Read First

- `docs/ai/modules/runtime-state.md`
- `docs/ai/architecture/module-boundaries.md`
- `src/material_agent/adapters/state/sqlite_runtime.py`
- `src/material_agent/adapters/state/processed_sqlite.py`

## Typical Scope

- add a processed result column
- add a runtime artifact or runtime event payload field
- support a new maintenance or rewrite query
- evolve stored rescore or commentary data

## When Not To Use

- when the request can be solved by changing only in-memory orchestration
- when the task is just an XMP formatting change
- when the change belongs entirely inside score computation and no stored field changes are needed

## Usual Files

- `src/material_agent/adapters/state/sqlite_runtime.py`
- `src/material_agent/adapters/state/processed_sqlite.py`
- `src/material_agent/app/rescore_service.py`
- runtime or rewrite consumers in `src/material_agent/app/`
- tests in `tests/test_runtime_state.py`, `tests/test_state.py`, `tests/test_rescore.py`

## Checklist

1. Decide whether the change belongs to runtime state, processed state, or both.
2. Keep status meanings stable unless the task explicitly asks for lifecycle changes.
3. If adding a column, check:
   - bootstrap DDL
   - read paths
   - write paths
   - rescore / rewrite consumers
4. If changing stored JSON shape, check all readers before changing one writer.
5. Prefer additive schema evolution over destructive changes.

## Acceptance Checks

- `pytest tests/test_runtime_state.py tests/test_state.py`
- if rescore is affected: `pytest tests/test_rescore.py`
- if review pipeline reads the new field: `pytest tests/test_review_job.py tests/test_app_services.py`

## Common Failure Modes

- updating write paths but not read paths
- changing status semantics in one repository only
- forgetting that runtime and processed concepts are separate even when they share one DB path
