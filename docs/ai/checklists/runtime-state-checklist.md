# Checklist: Runtime State Changes

Use this checklist before finalizing a change in SQLite-backed runtime or processed persistence.

## Scope Check

- Is the change about runtime state, processed state, or both?
- Is that split explicit in the implementation?

## Behavior Check

- Do lifecycle statuses still mean the same thing?
- Are read and write paths updated together?
- If a stored JSON shape changed, were all readers updated?
- If reconnect or recovery logic changed, is failure handling still explicit?

## Contract Check

- Are runtime and processed concepts still distinct even if they share one DB path?
- Is schema evolution additive where possible?
- Do rescore and rewrite consumers still receive the fields they expect?

## Verification Check

- Run `pytest tests/test_runtime_state.py tests/test_state.py tests/test_rescore.py`

## Docs Check

- Update `docs/ai/modules/runtime-state.md` if storage responsibilities or risks changed
- Update the DB schema playbook if the workflow changed
