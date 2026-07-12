# OMLX Runtime Module Contract

## Purpose

This legacy module owns the dedicated OMLX runtime compatibility integration.
It is not part of the default `material-agent` path.

It covers transport, capability probing, runtime instance management, and failure guidance.

## Main Files

- `src/material_agent/adapters/models/omlx/transport.py`
- `src/material_agent/adapters/models/omlx/contracts.py`
- `src/material_agent/adapters/models/omlx/probe.py`
- `src/material_agent/adapters/models/omlx/instance.py`
- `src/material_agent/app/omlx_instance_service.py`
- `src/material_agent/commands/omlx_runtime.py`

## Responsibilities

- send chat-completion requests to OMLX
- define request/response contract expectations
- probe server capabilities before a run
- manage the dedicated runtime instance lifecycle
- convert probe failures into actionable guidance

## Non-Goals

- photo grouping
- score aggregation math
- XMP writing
- processed-state persistence

## Inputs

- normalized OMLX config
- model/runtime settings
- request payloads from the client layer

## Outputs

- HTTP responses from OMLX
- runtime status summaries
- capability validation artifacts
- failure guidance for users and orchestration layers

## Invariants

- OMLX is treated as fail-fast only after compatibility use is explicitly enabled
- capability requirements must be checked before long review jobs when probing is enabled
- the dedicated active model set must cover every configured OMLX request model: fast vision, full vision, and commentary
- `response_format_json_schema` is the current default contract path for the local DMG runtime; `structured_outputs` and `xgrammar` remain observable capability fields and can be made hard requirements when the runtime supports them
- transport should stay minimal and not absorb higher-level policy
- on the shared desktop runtime, `/v1/models` may behave like an installed-model catalog superset; keep strict `instance_matches` for dedicated enforcement, but surface `effective_model_set_matches` and `served_models_catalog_superset` for diagnostics

## Typical Safe Changes

- refine probe checks
- improve failure guidance
- add one transport header or timeout adjustment
- improve status reporting for runtime management commands

## Risky Changes

- broadening contract leniency without checking downstream parsing assumptions
- weakening fail-fast checks in a way that allows broken long-running jobs
- mixing runtime management code with scoring policy code

## Files Usually Safe To Edit Together

- `src/material_agent/adapters/models/omlx/*.py`
- `src/material_agent/app/omlx_instance_service.py`
- `src/material_agent/commands/omlx_runtime.py`
- `tests/test_omlx_probe.py`
- `tests/test_omlx_instance.py`
- `tests/test_omlx_instance_service.py`

## Minimal Verification

- `pytest tests/test_omlx_probe.py tests/test_omlx_instance.py tests/test_omlx_instance_service.py`

## Known Tensions / Technical Debt

- The transport layer is intentionally tiny, but much of the effective contract lives across client, contract, and probe code rather than one obvious place.
- Runtime capability validation is strong, but that also means configuration drift can fail runs before useful work starts.
- OMLX remains a specialized legacy/teacher integration path that requires more
  operational knowledge than the supported local stack.
- Production `run` rejects OMLX unless `legacy.enabled: true` is set explicitly.
- Do not use OMLX or Ollama as a fallback from local model failure. Local blocks
  must use their documented CPU/heuristic fallback instead.
