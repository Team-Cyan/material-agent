# Tune OMLX Harness Playbook

Use this playbook when tuning model choice, prompt overrides, or commentary-quality guards with a real RAW sample set.

## Goal

Move from anecdotal one-off impressions to a repeatable local workflow:

1. request-level benchmark for stability and latency
2. live harness for real pipeline output quality
3. config or prompt adjustment
4. repeat on the same sample set

## When To Use This

- model comparison
- prompt refinement
- commentary repetition reduction
- checking whether a shared desktop OMLX setup still behaves correctly after configuration changes

## Recommended Order

### 1. Start from the normal user path

- prefer the shared desktop runtime unless the task explicitly requires a dedicated instance
- make sure `material-agent omlx-start --restart-shared` succeeds before comparing outputs

### 2. Use `omlx-benchmark` first for request-level tuning

Use benchmark when adjusting:

- `contract_mode`
- `prompt_preset`
- token caps
- temperatures
- image resize / JPEG quality

Goal: confirm that the request path is stable enough before caring about human-facing output quality.

### 3. Use `omlx-harness` second for live-sample evaluation

Use harness when adjusting:

- `omlx.model_profiles`
- commentary prompt extras
- commentary quality guards
- default model choice

Goal: inspect real outputs from the normal `run` path.

## Command Pattern

```bash
uv run material-agent omlx-harness \
  --config config.yaml \
  --models Qwen3-VL-4B-Instruct-4bit Qwen3-VL-8B-Instruct-4bit \
  --sample-set /path/to/photos \
  --limit 12
```

## What To Look For

### Good signs

- `done_count == sample_count`
- `invalid_post_count == 0`
- `invalid_group_issue_count == 0`
- `max_post_repeat` stays low for the sample size
- `verdict == ready_for_default_path`
- `Runtime interpretation` says the runtime looks aligned to the candidate model set
- the report examples are grounded in the actual scene and weak dimensions

### Bad signs

- `verdict == runtime_unstable`
- `verdict == needs_structural_fix`
- `shared_runtime_drift_detected == true`
- `Runtime interpretation` says the runtime did not effectively expose the expected candidate model set
- post commentary includes shooting advice
- group issues collapse into raw score dumps
- one exact post template dominates the whole sample
- repeated runtime errors or sample-count mismatch

## Edit Strategy

### If the output is structurally wrong

Edit:

- `src/material_agent/clients/prompts.py`
- `src/material_agent/clients/omlx.py`
- `src/material_agent/domain/commentary.py`

### If the output is structurally correct but too repetitive

Edit in this order:

1. `omlx.model_profiles.<model>.prompt_overrides`
2. `domain/commentary.py` quality guards or synthesis logic
3. prompt presets only if the issue is clearly cross-model

### If runtime behavior is unstable before scoring even starts

Edit:

- `src/material_agent/app/omlx_instance_service.py`
- `src/material_agent/adapters/models/omlx/probe.py`
- `src/material_agent/commands/scoring.py`

## Verification

- narrow tests:
  - `pytest tests/test_omlx_harness.py tests/test_main.py`
- module-crossing tests when prompt/runtime behavior changed:
  - `pytest tests/test_architecture_refine.py tests/test_omlx_instance_service.py tests/test_main.py`

## Notes

- keep harness sample sets small and stable so before/after comparisons remain meaningful
- do not treat harness ranking as absolute photo-quality truth; it is a regression and comparison aid
- preserve the difference between benchmark artifacts and harness artifacts in both code and docs
