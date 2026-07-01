# Playbook: Debug OMLX Runtime

Use this playbook when OMLX requests fail, probing fails, the served model set mismatches config, or runtime management commands misbehave.

## Read First

- `docs/ai/modules/omlx-runtime.md`
- `docs/ai/prompts/debug.md`
- `src/material_agent/adapters/models/omlx/probe.py`
- `src/material_agent/app/omlx_instance_service.py`

## Typical Scope

- probe failure before `run`
- transport or timeout failures
- capability mismatch
- dedicated instance lifecycle issues
- request contract mismatches

## When Not To Use

- when the issue is in generic scoring policy rather than OMLX runtime behavior
- when the failure is clearly in XMP write-back or SQLite state
- when the task is about adding a new model-facing product feature rather than debugging runtime operations

## Usual Files

- `src/material_agent/adapters/models/omlx/*.py`
- `src/material_agent/app/omlx_instance_service.py`
- `src/material_agent/commands/omlx_runtime.py`
- tests in `tests/test_omlx_probe.py`, `tests/test_omlx_instance.py`, `tests/test_omlx_instance_service.py`

## Checklist

1. Separate these questions first:
   - Is the service reachable?
   - Does it satisfy capability requirements?
   - Does the served model set match config?
   - Is the bug in transport, probe logic, or instance management?
2. Keep fail-fast semantics unless the task explicitly requests a softer behavior.
3. Improve failure guidance before weakening validation.
4. Keep transport thin; do not move policy logic into the HTTP helper unless necessary.
5. If a probe field changes, update both event/artifact payloads and tests.

## Acceptance Checks

- `pytest tests/test_omlx_probe.py tests/test_omlx_instance.py tests/test_omlx_instance_service.py`

## Common Failure Modes

- masking a capability bug by relaxing checks too early
- fixing the user-visible error text while leaving event payloads stale
- changing probe assumptions without checking preflight behavior in `commands/scoring.py`
