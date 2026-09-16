# Checklist: Grouping Changes

Use this checklist before finalizing a change in time/hash grouping or EXIF reading behavior.

## Scope Check

- Is the change really about grouping, not ranking or scoring?
- Did it stay mostly inside `domain/grouper.py`?

## Behavior Check

- Is group ordering still stable?
- Do missing EXIF timestamps degrade safely instead of failing the run?
- Do positive hash limits require both adjacent time and hash proximity?
- Does hash threshold 0 bypass all hash reads/cache access?
- Can neither embedding similarity nor hash similarity bridge a time mismatch?
- Did the change avoid adding disproportionate work to large dataset runs?

## Contract Check

- Does the output remain `list[list[str]]` with stable ordering?
- Is EXIF cache behavior still compatible with processed state?

## Verification Check

- Run `pytest tests/test_grouper.py tests/test_pipeline.py`

## Docs Check

- Update `docs/ai/modules/grouping.md` if grouping strategy or known tradeoffs changed
