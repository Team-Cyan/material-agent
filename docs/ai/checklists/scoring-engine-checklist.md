# Checklist: Scoring Engine Changes

Use this checklist before finalizing a change in score computation or decision summarization.

## Scope Check

- Did the change stay inside the scoring layer unless another layer truly needed updating?
- If a new score field or dimension was added, were constants and labels reviewed too?

## Behavior Check

- Are score values still bounded and numerically safe?
- Do rejection paths still return enough information for persistence and rescore?
- If scene handling changed, does scene-aware exposure behavior still make sense?
- If fast screening changed, is the fallback behavior still explicit?

## Contract Check

- Is `ScoreBundle` still compatible with runtime, persistence, and rewrite consumers?
- If signals changed, does `rescore` still work?
- If visible breakdown changed, do XMP instructions and downstream display still work?

## Verification Check

- Run `pytest tests/test_scorers.py tests/test_rescore.py tests/test_review_job.py`
- If config shape changed, also run `pytest tests/test_config_validator.py`

## Docs Check

- Update `docs/ai/modules/scoring-engine.md` if responsibilities or risks changed
- Update the relevant playbook if this change reveals a new common pattern
