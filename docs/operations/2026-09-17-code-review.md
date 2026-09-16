# Code review: scoring/refinement and projection failure boundaries

Scope: review the recently committed coverage, metadata ledger and optional
refinement code, then fix and commit confirmed defects. The worktree contained
15 pre-existing unrelated guidance edits and no uncommitted implementation files;
those guidance edits are excluded and preserved.

## Confirmed findings and fixes

1. **P2: invalid refinement could replace the baseline despite a failed status.**
   `refine_group` assigned the callback result before validating its evidence
   metadata. A subsequent exception recorded `failed` but left the candidate's
   score and evidence selected. Publishing the candidate now occurs only after
   metadata processing succeeds, using a shallow copy to avoid adding audit data
   to the callback's returned dictionary. The regression supplies a candidate
   with valid score but malformed evidence and confirms original score/evidence
   retention. It failed before the fix (1 rather than baseline 7).
2. **P2: a malformed stored rewrite payload aborted subsequent files.**
   Subject/instruction/description construction occurred outside the per-file
   exception boundary. Invalid `visible_breakdown_json` escaped the batch loop
   without a failure receipt. Construction now uses the same exception boundary
   as atomic writing. The regression uses SQLite fixtures and a mocked writer:
   malformed first row records failure, valid second row records success, and
   only the valid row reaches the writer. It raised JSONDecodeError before the fix.

Also inspected coverage/quality separation, filtered rescore context, runtime
finalization and successful/failed receipt persistence. No production operation
or actual photo/XMP write was performed. These targeted fixes do not establish
full real-burst or professional-software acceptance.

## Verification

- Both new regressions reproduced their failures before editing implementation.
- Focused refinement, ledger and app-service tests: **48 passed, 8 skipped**.
- `make check`: passed.
- Full guarded regression: **738 passed, 102 skipped in 22.31 s**.
  Source-media/XMP-writing tests remain skipped under the session boundary.
  Log: `.local/review-2026-09-17/tests.log`.
- `git diff --check` passed; only the two fixes, their tests and this review
  record are staged. The original unrelated worktree patch remains unchanged.
