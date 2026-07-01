# Checklist: OMLX Runtime Changes

Use this checklist before finalizing a change in OMLX transport, probing, or instance management.

## Scope Check

- Is the issue in transport, probe logic, contract handling, or instance management?
- Did the change stay in the smallest owning part of the OMLX module?

## Behavior Check

- Is fail-fast behavior preserved unless the task explicitly changes it?
- If probe fields changed, do runtime events and artifacts still reflect the new shape?
- If transport changed, are timeout and header assumptions still explicit?
- If failure guidance changed, is it more actionable without hiding the real problem?

## Contract Check

- Did the change avoid moving policy logic into the thin transport helper?
- Are config expectations still aligned with runtime management and preflight checks?

## Verification Check

- Run `pytest tests/test_omlx_probe.py tests/test_omlx_instance.py tests/test_omlx_instance_service.py`

## Docs Check

- Update `docs/ai/modules/omlx-runtime.md` if ownership or failure modes changed
- Update the OMLX debug playbook if the debugging flow changed
