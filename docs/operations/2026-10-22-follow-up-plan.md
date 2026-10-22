# Follow-up plan after the October 22 repository review

This page owns the next executable work queue. The [status ledger](2026-09-16-plan-status.md)
owns current status; the [repository review](2026-10-22-repository-review.md)
records findings and coverage. The [September plan](2026-09-26-culling-improvement-plan.md)
retains the completed A1–A4 specifications and future coverage admission gates.
Historical next-step statements do not reopen completed work.

## Review and product baseline

- Review baseline: `973c11631198648d156b20dbc8a7196ae724d03d`.
- Independent review and controller reproductions establish two P2 operational
  defects and two P3 preview/diagnostic defects. None is fixed by this document.
  The known exposure-bracket limitation remains deferred rather than a new bug.
- The product remains a local photo-culling pipeline and admin dashboard.
  Adjacent time AND pHash grouping, threshold-zero time-only bypass, CPU fallback,
  separate quality and selection, protected ratings, and Web dry-run behavior
  remain the current contract.
- A1–A4 and the bounded native/recovery/Bridge stage are complete. Their reports
  retain failed attempts, negative results, immutable identities and exclusions.
  Successful CI, image publication, deployment and photographic acceptance are
  separate claims.
- No new grouping/scoring mode, production-library XMP write, model acquisition
  or live deployment is selected by this planning update.

## Executable queue

Each item has a bounded owner, an evidence checkpoint and an explicit exit.
Execution follows executor self-review, controller review, appropriate checks,
then one scoped commit/push under the existing authorization. Save findings,
commands, identities and unfinished work before expensive steps or handoff;
reuse verified outputs after interruption rather than replaying completed writes.

### R0 — Reconcile review and planning entrypoints

Owner: controller; documentation only.

- [x] Complete independent review, reviewer self-review and controller assessment.
- [x] Replace stale README/roadmap next steps and label historical ledger rows.
- [x] Verify links, repository boundaries and scoped diff.

This item does not require another native inference, GUI edit or recovery test.

### R1 — Reconcile Web tasks with surviving workers after restart

Owner: Web operations (`app/web_service.py`, its tests and module contract).

- [ ] Define safe reconciliation for a Web manager restart while a scoring
  subprocess survives. Do not mark a live worker terminal and then report no
  active task. Preserve the shared runtime lock as a second line of protection.
- [ ] Keep start/cancel/status consistent with the reconciled worker. Validate
  ownership and process identity before signaling; a saved PID alone is
  insufficient because it may have been reused.
- [ ] Cover a surviving owned worker, an exited worker, queued/no-process state,
  stale/reused PID and cancellation during reconciliation. An uncertain identity
  must not cause an unrelated process to be signaled or another worker launched
  into a known occupied work directory.

Acceptance: a temporary owned process group can hold the runtime lock across
manager reconstruction; the dashboard/API truthfully report its state and do not
accept a conflicting task. Verified cancellation/exit releases the lock and
permits a new task, with durable terminal state. Preserve logs and dry-run-only
Web commands. Test without production jobs; do not infer that every container
restart leaves a child alive. The current lock prevents concurrent writes, so
this review establishes a control/status defect, not observed data corruption.

### R2 — Protect model assets referenced by active tasks

Owner: model management (`app/model_catalog_service.py`, the Web task/model
coordination seam, model/Web tests and contracts).

- [ ] Protect effective model A while a task using A is active, even after the
  operator selects B for later work. Current-selection protection alone is
  insufficient; an existing process may still hold A's path before lazy loading.
- [ ] Choose the smallest safe exclusion or task reference mechanism. Account
  for the start/delete race and R1's surviving workers; a check of `active()`
  without shared coordination is not sufficient.
- [ ] Cover managed/bundled paths, forced deletion, task failure/cancellation,
  restart reconciliation and reference release. Do not let force bypass a live
  task's safety boundary without an explicit coordinated stop.

Acceptance: with two checksum-pinned fixture assets, capture A in an effective
task config, select B, attempt to delete A and delay its first load. A remains
available until the task releases it, or deletion is rejected/deferred. Later
tasks resolve B. Default fallback must not silently become the substitute for
this ownership guarantee; `enforce_available` failures also remain explicit.
No actual inference or download is needed to test asset lifetime.

### R3 — Generate output previews for unchanged cached dry-run results

Owner: review pipeline (`app/jobs/review_photos.py`, the smallest necessary
`app/review_runtime.py` projection seam, relevant tests and contracts).

- [ ] Ensure an unchanged cached `done` group in dry-run gets a complete current
  `output_preview` and appropriate projection evidence before its artifact is
  persisted. Preserve its truthful `skipped` outcome.
- [ ] Retain cache reuse and quality/selection/provenance; do not decode or infer
  again solely to construct metadata output. Keep source XMP and processed-state
  writes disabled, including error paths.
- [ ] Cover all-cached groups, mixed cached/new groups, changed membership/ranks,
  protected user ratings and malformed/read-only sidecars, fresh simulation and
  real-write regression behavior. Assert persisted artifacts, not only the
  in-memory return value.

Acceptance: cached and fresh equivalent dry-run inputs expose equivalent current
preview fields to the library API, with accurate group/rank/selection and rating
ownership. No source or processed-row mutation occurs; normal incremental writes
still skip unchanged output. Avoid a broad finalization refactor.

### R4 — Distinguish XMP commit from receipt persistence failure

Owner: XMP rewrite (`app/rewrite_xmp_service.py`, affected CLI/report consumers,
writer/state tests and the writer contract).

- [ ] Keep a committed sidecar result distinct from subsequent SQLite receipt
  or progress-report failure. Preserve the committed receipt and failed-stage
  error context even when the ledger is unavailable.
- [ ] Retain an overall bookkeeping failure indication; do not change the result
  to unconditional success merely because the filesystem commit succeeded.
- [ ] Test post-commit receipt failure, pre-commit write refusal, and progress
  callback failure. Preserve existing ownership and external-change guards.

Acceptance: failure injection after one committed writer call reports an XMP
commit plus failed persistence/reporting, not `ERROR writing` for that successful
commit. No automatic replay of the sidecar write is allowed as a receipt repair.
Existing callers must receive an explicit compatible failure signal or be updated
in the same bounded batch. This does not implement atomic DB/XMP transactions.

### R5 — Classify missing RAW model evidence from existing artifacts

Owner: review-pipeline/state diagnostics, with the private operator responsible
for any read-only retrieval of target artifacts.

- [ ] Reconcile the accepted RAW-v3 manifest, full score artifacts and job/log
  records by exact fixture/job identity. The published count is 15/20 serialized
  CPU-model records per adapter; the remaining five are unclassified.
- [ ] Trace each absent record through the actual scoring and serialization
  branches. Distinguish an intentional early rejection, cached evidence,
  fallback/error, projection omission and genuinely missing evidence. A possible
  code branch is not proof of which branch those five fixtures took.
- [ ] Publish sanitized counts and an explicit disposition: intended behavior,
  observability gap, confirmed defect, or insufficient retained evidence.

Acceptance: account for all 20 fixture identities for both adapters, preserve the
original report and hashes, and distinguish serialized records from unique model
calls. Use existing immutable artifacts first; no acquisition, full-library run,
model/threshold change or source metadata write is needed. If evidence cannot
classify a record, report that limit rather than rerunning the accepted stage.

R5 is a bounded diagnostic after the four confirmed product fixes. If the result
establishes another defect, specify a separate smallest-module correction and
regression before dispatch. Intended behavior, insufficient retained evidence
or a documented limitation can close the diagnostic without code. Do not
manufacture a refactor or new telemetry framework.

### Verification and release sequence

R1 uses `uv run pytest -q tests/test_web_service.py tests/test_run_control.py`
and affected CLI/state checks. Include out-of-band SIGTERM/CLI exit 130 so a
cancelled runtime job is not reported as an ordinary Web failure.
R2 uses model-catalog/Web tests with deterministic task/asset interleavings and
R1 restart cases. R3 uses the review-pipeline contract's
`tests/test_review_job.py`, `tests/test_app_services.py` and
`tests/test_runtime_state.py`, plus writer/state checks if projection changes.
R4 uses `tests/test_app_services.py`, `tests/test_writer.py`,
`tests/test_state.py` and affected CLI checks.
Runtime/cross-module batches require `make check` and `make test` for their impact.
Run the new regression first, then the required checks once they pass. Record
actual results rather than treating this command list as executed evidence.

Report exact-head CI separately. A target deployment/isolated acceptance is a
later private-operator step after the runtime fixes pass review and publication;
retain rollback and source read-only protections. This planning batch makes no
new deployment claim. Do not rerun old Bridge/recovery cohorts to validate an
unrelated Web lifecycle or cached-preview change.

## Conditional product research

These tracks are not release blockers or prerequisites for R1–R5.

| Track | Reopen only when | Required result / stop rule |
| --- | --- | --- |
| Within-series preference diagnostic | A suitable public release has verified label meaning/direction, usable media terms/access, official partitions and source-family lineage. Existing FGAesthetics metadata access alone does not establish these. | Freeze an existing-scorer comparison and uncertainty/tie accounting before prediction. Use its native preference target, record training exposure, and preserve a negative result; no new model or default promotion follows automatically. |
| Exposure-correction grouping | New independent positive and same-time/different-content negative evidence supports a specific new hypothesis. | The previous equalized/autocontrast/dHash comparisons and subsequent false merges are already complete. Do not repeat them on inspected examples or raise the threshold to fit one pair. Freeze holdout, tolerances and unknown handling before an experiment; keep the current contract if admission fails. |
| Directed important-content coverage | G1 has at least 24 qualifying pairs / 12 independent families and all existing split/category quotas. | G1 → G2 labeled oracle → frozen representation comparison, retaining direct final-keeper witnesses and unknown/unique-content protections. MOS, action labels and aesthetic preferences cannot replace this target. No production promotion before the remaining gates. |

Source investigation belongs to the agent within the existing bounded public-data
authorization. It is not a standing request for the user to annotate photos.
Author outreach/account interactions require their own applicable authorization;
no such action is selected here. Do not repeatedly poll unchanged source gaps.

## Deferred compatibility and maintenance

- Capture One and broader format/vendor-ID round trips need separately scoped
  disposable fixtures and actual reader results. Bounded Bridge closure stays
  accepted; JPEG adjacent-sidecar failure and DNG metadata-only scope stay visible.
- JPEG embedded metadata remains an optional opt-in design backlog, with no
  embedded-write implementation or write selected.
- Same-job resume, whole production-appdata restore and atomic DB/XMP crash
  consistency are unverified guarantees. Define a concrete product requirement
  and failure model before selecting implementation or acceptance work.
- Retain MUSIQ's failed resource admission and the A4 no-extraction decision.
  Reopen a lifecycle/refactoring seam only for a demonstrated maintenance or
  product benefit, with new experiment identities where semantics change.
- Additional hardware tags, legacy-teacher removal and personal ranker training
  remain backlog; they do not outrank a confirmed correctness issue or acquire
  acceptance from code-only smoke checks.

## Current human involvement

No immediate user action is required for this queue. Prior Mac lock and Bridge
binding failures were resolved. Ask only for a specific unavoidable interaction
or an action beyond existing authorization; preserve independent progress.
