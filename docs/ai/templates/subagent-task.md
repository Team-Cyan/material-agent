# Sub-Agent Task Template

Use this template when delegating a narrow task to a sub-agent.

Keep the task module-scoped. Do not send the whole repository unless the change genuinely crosses boundaries.

## Template

```md
# Task

<one-sentence change request>

## Target Module

<module name>

## Read First

- <path 1>
- <path 2>
- <path 3>

## Goal

- <expected behavior change>

## Inputs / Outputs To Respect

- inputs: <contract assumptions>
- outputs: <required output shape or side effects>

## Allowed Files

- <file path>
- <file path>

## Avoid Editing

- <file path or module>
- <file path or module>

## Constraints

- preserve existing architecture style
- keep the change additive and minimal
- do not refactor unrelated modules

## Acceptance Checks

- <test command>
- <manual check>

## Out Of Scope

- <explicitly excluded change>
- <explicitly excluded change>
```

## Example

```md
# Task

Adjust fast-screening rejection behavior so failed fast-screening calls fall back to full scoring instead of rejecting the file.

## Target Module

scoring-engine

## Read First

- src/material_agent/domain/scoring_engine.py
- docs/ai/modules/scoring-engine.md
- tests/test_scorers.py

## Goal

- preserve current fast-screening success behavior
- skip rejection when the fast-screening adapter raises an exception

## Inputs / Outputs To Respect

- inputs: `compute_scores()` still accepts the same config and optional `fast_screening`
- outputs: returned `ScoreBundle` shape must stay unchanged

## Allowed Files

- src/material_agent/domain/scoring_engine.py
- tests/test_scorers.py

## Avoid Editing

- src/material_agent/app/review_runtime.py
- src/material_agent/adapters/state/processed_sqlite.py

## Constraints

- keep score field names unchanged
- do not change decision policy outside the fast-screening error path

## Acceptance Checks

- pytest tests/test_scorers.py

## Out Of Scope

- OMLX transport changes
- config schema redesign
```
