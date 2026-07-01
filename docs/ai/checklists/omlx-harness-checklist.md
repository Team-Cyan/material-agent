# Checklist: OMLX Harness Changes

Use this checklist before finalizing a change in the live OMLX harness, model-comparison flow, or harness reporting.

## Scope Check

- Is the change really about live-sample comparison rather than request-level benchmark behavior?
- Did the change stay primarily inside `app/omlx_harness_service.py` and its thin CLI wiring unless a broader boundary crossing was intentional?

## Behavior Check

- Does the harness still reuse the real `material-agent run` path instead of a fake shortcut?
- If model selection changed, does the harness still force a same-model comparison across fast vision, full vision, and commentary?
- If reporting changed, are the meanings of warnings, verdicts, and ranking still explicit for humans?

## Artifact Check

- Are `summary.json`, `report.md`, request snapshot, config snapshot, and sample manifest still written?
- Are per-model `runtime_status.before.json` and `runtime_status.after.json` still written when runtime capture is enabled?
- If new report fields were added, are they serializable and reflected in both machine-readable and human-readable outputs?
- If config snapshots changed, are secrets still redacted?

## Quality Check

- Does the harness still distinguish structural failures from style/repetition issues?
- Are repetition checks and invalid commentary checks still easy to interpret from the report?
- Is shared-runtime drift observable from warnings or runtime snapshot fields instead of only terminal logs?
- If runtime-report wording changed, does `report.md` still explain shared desktop alignment without forcing humans to open raw runtime JSON?
- If ranking logic changed, is the ordering rationale still stated clearly in the comparison report?

## Verification Check

- Run `pytest tests/test_omlx_harness.py tests/test_main.py`
- If commentary heuristics changed, also run `pytest tests/test_architecture_refine.py tests/test_pipeline.py`

## Docs Check

- Update `README.md` if harness usage, outputs, or interpretation changed
- Update `docs/module-map.md` or any human-facing runbook if the report-reading workflow changed
- Update `docs/ai/modules/omlx-harness.md` or the harness playbook if ownership or tuning flow changed
