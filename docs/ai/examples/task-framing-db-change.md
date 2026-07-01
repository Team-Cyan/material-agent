# Example: Task Framing For A DB-Backed Change

Use this example when a request touches stored data and could easily sprawl.

## Good Framing

```md
Goal: add one processed-state field that stores a new derived review summary, and expose it only to rewrite and inspection flows.

Owning module: runtime-state

Read first:
- docs/ai/modules/runtime-state.md
- docs/ai/playbooks/change-db-schema.md
- src/material_agent/adapters/state/processed_sqlite.py
- tests/test_state.py

Allowed files:
- src/material_agent/adapters/state/processed_sqlite.py
- src/material_agent/app/rewrite_xmp_service.py
- tests/test_state.py

Avoid:
- scoring policy changes
- runtime stage changes
- CLI redesign

Acceptance:
- pytest tests/test_state.py
- pytest tests/test_writer.py
```

## Bad Framing

```md
Add a better review summary field everywhere in the pipeline and clean up the DB while you are there.
```

## Why The Good Framing Is Better

- it names one owning module
- it limits file ownership
- it prevents opportunistic refactors
- it separates persistence concerns from policy concerns
