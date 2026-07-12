# OMLX Harness Module Contract

## Purpose

This legacy module owns the optional live-sample teacher/comparison path for
OMLX-backed models. It is not a production scoring dependency.

Unlike `omlx-benchmark`, it is intentionally end-to-end and reuses the real review pipeline so the output reflects production behavior instead of a benchmark-only shortcut.

## Main Files

- `src/material_agent/app/omlx_harness_service.py`
- `src/material_agent/commands/omlx_harness.py`
- `src/material_agent/shells/cli/main.py`
- `tests/test_omlx_harness.py`

## Responsibilities

- resolve a small RAW sample set from files or directories
- materialize a temporary sample input directory for each candidate model
- run the normal `material-agent run` path against that sample set
- inspect the processed SQLite output after the run
- compute practical audit metrics such as repetition and invalid commentary leakage
- write machine-readable JSON plus human-readable Markdown reports
- translate runtime snapshot fields into a human-readable interpretation inside the Markdown report

## Non-Goals

- micro-benchmark latency sweeps
- transport-only schema testing
- scoring policy changes
- prompt contract definitions
- full pipeline orchestration logic outside the harness shell

## Inputs

- normalized `backend: omlx` config
- model list
- sample RAW paths or directories
- optional result root
- optional profile mode override
- optional `no_visual_merge` harness flag

## Outputs

- `artifacts/harnesses/omlx/<timestamp>/summary.json`
- `artifacts/harnesses/omlx/<timestamp>/report.md`
- `artifacts/harnesses/omlx/<timestamp>/run_request.json`
- `artifacts/harnesses/omlx/<timestamp>/config_snapshot.json`
- `artifacts/harnesses/omlx/<timestamp>/sample_manifest.json`
- per-model `summary.json` and `report.md`
- per-model `config_snapshot.json`
- per-model `runtime_status.before.json` and `runtime_status.after.json`
- per-model sample input folders and processed DBs

## Invariants

- the harness must use the real `run` path rather than a synthetic scoring stub
- each candidate model should be evaluated under the same-model fast/full/commentary configuration unless the command explicitly evolves
- the harness should preserve a small-sample workflow; it is not intended for full-directory production runs
- the harness report must stay human-readable enough for non-code users
- verdicts and warnings should remain interpretable by both humans and automation
- shared-runtime drift should be observable in the report instead of hidden in terminal logs
- shared desktop runtime nuances should be readable from the report without opening raw `runtime_status*.json`

## Typical Safe Changes

- add a new report metric
- tighten invalid-commentary detection
- improve sample materialization or naming
- add one CLI flag that clearly belongs to harness-only behavior

## Risky Changes

- bypassing the real `run` path for speed
- letting the harness mutate user source files directly
- mixing benchmark-only metrics into the live harness summary without clear labeling
- expanding the harness into a second full orchestration system

## Files Usually Safe To Edit Together

- `src/material_agent/app/omlx_harness_service.py`
- `src/material_agent/commands/omlx_harness.py`
- `src/material_agent/shells/cli/main.py`
- `README.md`
- `tests/test_omlx_harness.py`
- `tests/test_main.py`

## Minimal Verification

- `pytest tests/test_omlx_harness.py tests/test_main.py`

## Known Tensions / Technical Debt

- the harness depends on the normal review command, so review-pipeline changes can silently affect harness semantics
- invalid-commentary detection is heuristic rather than semantic
- per-model reports are useful for humans, but they also increase artifact volume
