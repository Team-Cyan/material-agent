# Checklist: Review Pipeline Changes

Use this checklist before finalizing a change in the review pipeline.

## Scope Check

- Is the change really owned by the pipeline, not by scoring, grouping, writer, or state modules?
- Did the change stay mostly inside `review_service.py`, `review_runtime.py`, or `review_photos.py`?
- If the change crossed into another module, is that boundary crossing explicit and justified?

## Behavior Check

- Does stage ordering still make sense?
- Does resumability still work for already scored or already written files?
- Are runtime events still emitted consistently for success, skip, and failure paths?
- Does `dry_run` still avoid write-side effects?

## Contract Check

- Did the score payload shape stay compatible with downstream readers?
- Did runtime services preserve session/job lifecycle expectations?
- Are new collaborators injected through runtime wiring instead of hard-coded deep in the flow?

## Verification Check

- Run `pytest tests/test_review_job.py tests/test_app_services.py tests/test_runtime_state.py`
- If the CLI path changed, also run `pytest tests/test_main.py`

## Docs Check

- If the module boundary shifted, update `docs/ai/modules/review-pipeline.md`
- If the task introduced a repeated workflow, consider updating a playbook
