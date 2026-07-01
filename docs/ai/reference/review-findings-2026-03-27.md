# Repository Review Findings (2026-03-27)

This note captures repository-level findings from the latest static review.

It is intentionally separate from `omlx-structured-output.md`:

- `omlx-structured-output.md` is for external guidance, runtime tuning, and verified integration behavior
- this file is for code-level findings that should stay visible while follow-up fixes are planned

## Scope Of This Review

The review focused on the currently modified scoring / OMLX / commentary path:

- `src/material_agent/core/scoring_engine.py`
- `src/material_agent/scorers/exposure.py`
- `src/material_agent/clients/omlx.py`
- related config and tests

Regression status at review time:

- `uv run pytest -q` -> passing
- `uv run ruff check` -> passing

Passing tests do not invalidate the findings below; these are logic and behavior mismatches that can still survive the current test suite.

## Findings

### 1. Scene-aware exposure is not used in the final aggregate

Severity: high

`compute_scores()` first computes `pixel_results` before the scene is known.
Later, after the vision model returns `scene`, the code recomputes `exposure` with the scene-aware profile and replaces the `exposure` entry inside `results`.

However, the final aggregate still uses the original `pixel_results` list captured before that replacement.

Practical impact:

- metadata and XMP can show the new scene-aware exposure score
- the final `total_score` can still be using the old default-scene exposure score
- ranking behavior can therefore disagree with the per-dimension score that users see

Relevant code at review time:

- `src/material_agent/core/scoring_engine.py`

### 2. The old exposure tuning keys in config are now dead

Severity: medium

The new exposure scorer no longer reads:

- `overexpose_threshold`
- `overexpose_hard_limit`
- `underexpose_threshold`
- `underexpose_hard_limit`

Instead, it uses built-in scene profiles.

Practical impact:

- users can still edit these keys in `config.yaml`
- README / comments still describe them as active controls
- changing them currently has no runtime effect

This is especially risky because exposure is one of the areas users are actively tuning with real photo sets.

Relevant files at review time:

- `src/material_agent/scorers/exposure.py`
- `config.yaml`
- `README.md`

### 3. OMLX fast parse failures do not honor `vision_retries`

Severity: medium

In `AsyncOMLXClient.score_image_fast()`, a `ValueError` caused by parse failure logs the invalid payload and then breaks out of the retry loop immediately.

That means:

- transient HTTP failures can still retry
- schema drift / prose output / parse failures do not actually retry

Practical impact:

- `vision_retries` does not match its documented behavior for the most common fast-path failure mode
- the pipeline escalates to the more expensive full path sooner than operators expect
- this increases load and makes throughput tuning harder

Relevant file at review time:

- `src/material_agent/clients/omlx.py`

## Suggested Follow-up Order

1. Fix the scene-aware exposure aggregate bug first.
   This is the most user-visible scoring correctness problem.

2. Decide whether exposure should remain config-driven or become fully profile-driven.
   Then align code, comments, and README so operators do not tune dead keys.

3. Revisit fast retry behavior after measuring whether one more parse retry improves real-photo throughput enough to justify the extra load.

## Status

These findings were recorded after review.

Follow-up implementation status:

- 2026-03-27: fixed `compute_scores()` so the scene-aware `exposure` result is recomputed before final aggregation and actually affects `total_score`
- 2026-03-27: fixed OMLX fast-path parse failures so `vision_retries` is honored instead of aborting after the first `ValueError`
- 2026-03-27: restored operator-visible exposure tuning by wiring legacy threshold / hard-limit config keys into the scene-aware profile scaling

Verification after the fixes:

- `uv run pytest -q`
- `uv run ruff check`
