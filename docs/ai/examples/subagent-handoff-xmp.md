# Example: Sub-Agent Handoff For An XMP Change

Use this as a concrete example of a well-scoped XMP output task.

```md
# Task

Preserve an additional class of user-authored XMP subject tags while keeping generated `pj:*` tags deterministic and unchanged.

## Target Module

xmp-writer

## Read First

- docs/ai/modules/xmp-writer.md
- docs/ai/playbooks/adjust-xmp-output.md
- src/material_agent/adapters/metadata/exiftool_xmp.py
- src/material_agent/app/rewrite_xmp_service.py
- tests/test_writer.py

## Goal

- preserve more non-`pj:` subject tags
- keep generated score, rank, group, scene, and decision tags unchanged
- keep rewrite behavior aligned with normal review writes

## Inputs / Outputs To Respect

- inputs: score payload already contains ranking and decision info
- outputs: `.xmp` sidecar content remains readable and deterministic

## Allowed Files

- src/material_agent/adapters/metadata/exiftool_xmp.py
- src/material_agent/app/rewrite_xmp_service.py
- tests/test_writer.py

## Avoid Editing

- src/material_agent/domain/scoring_engine.py
- src/material_agent/app/review_service.py
- src/material_agent/adapters/state/processed_sqlite.py

## Constraints

- do not remove preservation of existing user keywords
- do not rename `pj:*` tags
- do not redesign description formatting unless required by the task

## Acceptance Checks

- pytest tests/test_writer.py
- pytest tests/test_state.py

## Out Of Scope

- ranking logic changes
- commentary policy changes
```

## Why This Is A Good Example

- it covers both normal write and rewrite paths
- it makes preservation behavior explicit
- it blocks accidental spread into scoring and state layers
