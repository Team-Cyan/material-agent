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

## Follow-up: review all remaining guidance edits

The user subsequently included all 15 remaining guidance edits in the review
and commit scope. Reviewed every diff across `AGENTS.md`, the three `.agents/`
entry files, `docs/README.md`, and the ten changed `docs/ai/` files. This
supersedes the exclusion above for this follow-up batch only.

No actionable defect was found. Task-specific routing replaces repeated reading
sequences while retaining module contracts, required verification, local runtime
and CPU fallback, metadata protection, private-operations separation, and explicit
Git/external-action authorization. Optional checklist formats do not waive
required checks. Delegation remains conditional on active runtime permission;
OMLX routing is limited to explicit comparison work.

Validation: all 131 path references in the 15 documents resolve using their
repository, document, source-package, or AI-documentation context; verification
commands agree with the Makefile; repository boundary tests passed (**2 passed**);
`git diff --check` passed. No application code changed, so the earlier guarded
738-test result was not rerun or represented as a new execution. The original
15 edits are accepted without modification and committed together with this
review record. No push, deployment, production review, or photo/XMP write.

## Second follow-up: preflight parity and refinement evidence

Three new regression cases failed before the fixes: dry-run accepted both a
malformed stored row and a valid row (`ok=2, err=0`); missing old focus dimensions
or missing new focus pixels replaced score 5 with score 1 instead of retaining
baseline. Rewrite now shares pure per-row preparation and the writer's projection
preview validation. Dry-run reports one failure and one success, calls no writer,
and creates no projection receipts. Execution retains per-file failure isolation.
Refinement requires both comparison inputs and strictly greater positive pixel
area; missing/no-gain inputs retain baseline with `no_resolution_gain`.

The normal decoder always supplies focus pixels, but `RawFrame` permits omission
and old/cached/custom metadata may lack dimensions. The guard deliberately handles
these boundaries without claiming they were observed on the six new DNGs.

Focused tests: **51 passed, 8 skipped**. Full guarded suite: **741 passed,
102 skipped in 19.91 s**; log `.local/hdrplus-evaluation/tests.log`. Ruff and
`git diff --check` passed. See the separate follow-up validation report for public
data evidence and remaining capability limits.
