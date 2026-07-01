# Playbook: Add Or Adjust A Scorer

Use this playbook when the task changes one scoring dimension, one weighting rule, or one score-related field.

## Read First

- `docs/ai/modules/scoring-engine.md`
- `docs/ai/architecture/module-boundaries.md`
- `src/material_agent/domain/scoring_engine.py`
- the scorer implementation under `src/material_agent/scorers/`

## Typical Scope

- add a new local scorer
- adjust an existing scorer calculation
- enable or disable one scorer through config
- expose one additional scoring field to downstream consumers

## When Not To Use

- when the request is mainly about runtime orchestration
- when the real change is an XMP formatting change
- when the task is purely about DB schema without score computation changes

## Usual Files

- `src/material_agent/domain/scoring_engine.py`
- `src/material_agent/scorers/*.py`
- `src/material_agent/utils/constants.py`
- `src/material_agent/utils/config_validator.py`
- `config.yaml`
- related tests in `tests/test_scorers.py`, `tests/test_rescore.py`, or `tests/test_review_job.py`

## Checklist

1. Decide whether the change affects:
   - score computation only
   - config schema
   - downstream persistence
   - user-facing XMP instructions
2. Keep the scorer change inside the scoring layer unless persistence or config must also change.
3. Preserve numeric bounds and existing field names unless the task explicitly requires a schema change.
4. If adding a new score dimension, check constants, labels, visible breakdown behavior, and rescore compatibility.
5. Verify whether XMP instructions or commentary fallbacks depend on the changed dimension.

## Acceptance Checks

- `pytest tests/test_scorers.py`
- `pytest tests/test_rescore.py tests/test_review_job.py`
- if config changed: `pytest tests/test_config_validator.py`

## Common Failure Modes

- forgetting to update constants or labels
- changing score shape without updating persistence or rewrite flows
- changing signals in a way that silently breaks `rescore`
