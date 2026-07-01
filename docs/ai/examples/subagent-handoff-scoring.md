# Example: Sub-Agent Handoff For A Scoring Change

Use this as a concrete example of a well-scoped scoring task.

```md
# Task

Adjust fast-screening error handling so a temporary fast-screening adapter failure falls back to full scoring instead of degrading the file into an accidental reject path.

## Target Module

scoring-engine

## Read First

- docs/ai/modules/scoring-engine.md
- docs/ai/playbooks/add-scorer.md
- src/material_agent/domain/scoring_engine.py
- tests/test_scorers.py

## Goal

- keep existing successful fast-screening behavior
- keep explicit tier1 and tier2 rejection behavior
- when the fast-screening adapter raises, record the error in metadata and continue to full model scoring

## Inputs / Outputs To Respect

- inputs: `compute_scores(frame, client, config, fast_screening=...)`
- outputs: returned `ScoreBundle` shape must remain unchanged

## Allowed Files

- src/material_agent/domain/scoring_engine.py
- tests/test_scorers.py

## Avoid Editing

- src/material_agent/app/review_runtime.py
- src/material_agent/adapters/state/processed_sqlite.py
- src/material_agent/adapters/models/omlx/*

## Constraints

- preserve existing score field names
- do not change config schema
- do not alter rescore behavior

## Acceptance Checks

- pytest tests/test_scorers.py
- pytest tests/test_review_job.py

## Out Of Scope

- adding new score dimensions
- changing OMLX transport behavior
```

## Why This Is A Good Example

- one owning module
- narrow allowed file list
- explicit non-goals
- clear acceptance criteria
- no hidden cross-module expansion
