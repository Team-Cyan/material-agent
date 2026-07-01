# Example: When A Task Legitimately Crosses Modules

Use this example when the task truly requires more than one module.

## Situation

Add a new visible breakdown field that must be:

- computed in scoring
- stored in processed state
- written into XMP instructions

## Good Framing

```md
Goal: add one new visible breakdown field and thread it through scoring, processed persistence, and XMP instruction output.

Primary owner:
- scoring-engine

Secondary modules:
- runtime-state
- xmp-writer

Read first:
- docs/ai/modules/scoring-engine.md
- docs/ai/modules/runtime-state.md
- docs/ai/modules/xmp-writer.md
- docs/ai/playbooks/add-scorer.md
- docs/ai/playbooks/change-db-schema.md
- docs/ai/playbooks/adjust-xmp-output.md

Boundary crossing:
- scoring computes the field
- processed state stores the field
- writer renders the field
- no change to grouping or OMLX transport

Acceptance:
- pytest tests/test_scorers.py tests/test_state.py tests/test_writer.py
```

## Why This Is Acceptable

- it still identifies a primary owner
- it lists the exact secondary modules instead of expanding to the whole repo
- it explains why the boundary crossing is necessary

## Warning

If a task crosses modules, the handoff must say so explicitly. Do not hide a broad change inside a “small fix” description.
