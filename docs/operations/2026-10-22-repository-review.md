# Repository Review (2026-10-22)

## Scope and checkpoint

Review target: repository `material-agent`, requested baseline `973c11631198648d156b20dbc8a7196ae724d03d`. Initial inspection confirmed `HEAD` matched the baseline and the worktree was clean. The independent reviewer changed only this report; the controller subsequently updated planning documents. Code, tests, configuration, and evidence documents were inspected read-only. Selected boundary tests and synthetic temporary-directory reproductions ran; no production media/metadata, service deployment, runtime state outside test fixtures, expensive experiment, or production-library operation was touched.

The bounded Bridge/native/recovery acceptances were treated as completed evidence within their published limits. This review does not reopen those gates or infer acceptance for untested formats. The WebUI was reviewed as an admin/operator dashboard, not as an offline-labeling product branch.

## Actionable findings

### P2 — Web task restart can orphan a live scoring subprocess and misstate its status

**Trigger:** the Web manager process is restarted while a task subprocess created with `start_new_session=True` is still alive. The child may survive a manager-only restart; this finding does not assume that it survives destruction of the whole container.

**Impact and reproduction:** `WebTaskManager.__init__` reloads `tasks.json`, changes `queued`/`running`/`cancelling` records to `interrupted`, and persists the snapshot without checking or stopping the saved PID (`src/material_agent/app/web_service.py:443-450`). A temporary-directory reproduction using a real child process and the shared run lock observed the old task as `interrupted` while its PID remained alive and the lock remained held. `active()` then returns no task (`:482-487`); a new Web task starts, but the CLI's `exclusive_run_lock` refuses the existing lock, so the new task fails. There is no observed concurrent write or data corruption because the shared lock prevents two mutating controllers.

**Related terminal-status mismatch:** if the child receives SIGTERM outside `/api/tasks/{id}/cancel`, the CLI persists a cancelled job/session and returns exit code 130 (`src/material_agent/shells/cli/main.py:419-424`), while `_wait_for_process` maps any nonzero exit from a task still marked `running` to Web status `failed` (`src/material_agent/app/web_service.py:568-580`). The Web cancel route avoids that mismatch by setting `cancelling` before signaling (`:582-600`). Existing cancellation tests verify the CLI/SQLite state, but `tests/test_web_service.py` has no restart or out-of-band signal consistency case.

**Recommended next step:** reconcile managed subprocess identity and state on Web startup/shutdown, and map the CLI's durable cancellation result into the Web snapshot. Do not kill a process solely from a persisted PID: guard against PID reuse and confirm executable/process-group identity before signaling. Preserve the shared run lock as the final mutation exclusion.

**Acceptance:** with temporary directories and controlled child processes, test manager-only restart with a live child, child exit after restart, `/api/tasks/{id}/cancel`, and out-of-band SIGTERM. The snapshot must not claim a terminal state inconsistent with the child/runtime DB; a recovered live child must remain controllable or be safely stopped; a subsequent run must start only after lock release. Keep an explicit test for stale/reused PID rejection.

### P2 — Model deletion can invalidate a model path captured by an active Web task

**Trigger:** model selection is enabled and a Web-started scoring subprocess has resolved managed model A into its effective config; while that task is active, an operator selects an installed B of the same role and deletes now-unselected A. A catalog with alternative models for that role, such as a custom catalog, enables this sequence; the built-in catalog currently has one model per role.

**Impact:** model operations run in the Web process under `ModelCatalogService._lock` (`src/material_agent/app/model_catalog_service.py:144-174`), while scoring runs in a separate subprocess and has no shared lease or active-task exclusion. `apply_model_selections` resolves a model path into the child config (`:240-275`). The OpenVINO NIMA/SSD adapters lazily compile/load the path on scoring demand; if A is deleted before that first load, an `enforce_available: true` task fails, while default non-enforcing configuration may fall back and complete without the selected model signal. Either outcome violates that task's captured model choice. The Web model DELETE handler does not check active tasks (`src/material_agent/app/web_service.py:757-769`). Existing tests cover active-selection protection and selection application independently (`tests/test_model_catalog_service.py:59-97`), not mutation during a run.

**Recommended next step:** prevent deletion of model assets pinned by active task snapshots, or establish an immutable per-task model reference/lease that remains valid through lazy initialization. Selection changes may apply to later tasks while an active task retains its captured model.

**Acceptance:** in a temporary registry with checksum-pinned fixture assets and a controlled delayed model load, start a task using A, select B, attempt to delete A, then allow A to load. The active task must complete using A or deletion must be rejected/deferred until release; later tasks must resolve B. No model download or production service is needed.

### P3 — Processed-cache hits omit the DB-only XMP output preview in Web dry-runs

**Trigger:** a Web dry-run encounters a valid processed `done` cache row whose group ID/rank/size are unchanged, so the cached payload has `skip_write=True`.

**Impact:** the normal cache key includes score, grouping, preview, XMP, commentary, and runtime identity inputs (`src/material_agent/commands/scoring.py:31-52,121-155`); cached quality evidence is loaded (`src/material_agent/app/review_runtime.py:138-159`) and previous group/rank/size is checked (`src/material_agent/app/jobs/review_photos.py:240-259`). An unchanged all-cached group can bypass finalization (`:524-528`). The dry-run `output_preview` and `xmp_projection` are only attached in `write_file` (`src/material_agent/app/review_runtime.py:329-351`). `ReviewPhotosJob.run` takes the already-processed dry-run shortcut at `src/material_agent/app/jobs/review_photos.py:543-576`, persists the cached score artifact without calling `write_file`, and the Web API chooses the newest job-file row (`src/material_agent/app/web_service.py:190-221`). An isolated SQLite reproduction confirmed `finished`/`skipped`, `write_file_called=False`, and no `output_preview` in the newest artifact. The admin detail page then renders “暂无 tag/描述/instructions” (`src/material_agent/web/app.js:58-61`) even though the Web operations contract says dry-run score artifacts carry the would-be writer preview (`docs/ai/modules/web-operations.md:40-45`).

**Recommended next step:** regenerate the output projection for a dry-run cache hit after group finalization, or retain an explicitly versioned preview only when its configuration and current sidecar basis are still valid. Keep this DB-only; do not rewrite source XMP.

**Acceptance:** add a temp-directory integration case for a matching `done` cache hit and an unchanged group, then assert the newest Web score artifact includes rating, tags, instructions, description, and projection status. Also assert source media/XMP hashes are unchanged. Existing `tests/test_review_job.py::test_dry_run_repersist_score_payload_after_output_preview_is_added` covers a newly scored payload, not this cache-hit branch; cache round-trip coverage in `tests/test_rescore.py:470-504` does not check Web previews.

### P3 — Rewrite reports a committed XMP replacement as a write failure when SQLite receipt persistence fails

**Trigger:** `_rewrite_xmp_atomically` returns a committed receipt, then `record_xmp_projection` fails (for example, a SQLite I/O error).

**Impact:** the XMP sidecar has already been atomically replaced (`src/material_agent/app/rewrite_xmp_service.py:65-89`), but the exception path adds `persistence_error`, tries to record the receipt again, prints `ERROR writing <sidecar>`, and increments `err` (`:92-109`). This conflicts with its own comment that a committed filesystem projection must not be relabeled as a write failure. A temp-directory failure-injection reproduction returned `{"ok":0,"err":1}` and emitted both `ERROR recording XMP receipt` and `ERROR writing ...` after a committed receipt. This is an operator-result/diagnostic defect; it does not establish corrupt XMP.

**Recommended next step:** keep the operation in error while reporting the filesystem projection as committed and receipt/DB persistence as a distinct failed stage. Preserve the committed receipt and persistence error in the per-file diagnostic when possible. Do not automatically replay the writer after it has already committed.

**Acceptance:** inject `record_xmp_projection` failure after a committed atomic writer result and assert the command distinguishes committed XMP from failed DB bookkeeping, preserves the receipt/error context, and does not report the sidecar write itself as failed. Existing `tests/test_app_services.py` covers atomic rewrite and external-change refusal (`:894-985`), but not a post-commit DB failure.

### Configuration versus active tasks

The config PUT path validates a private temporary file and atomically replaces the active file (`src/material_agent/app/web_service.py:688-716`). `WebTaskManager.start` reads the current file, writes a task-specific config snapshot, then starts the subprocess with that snapshot (`:489-560`). Thus a single config update during a running task does not mutate that task's config; it affects a later task. The Web model service is fixed to its startup registry directory, while the scoring subprocess resolves the registry path from its task config, so operators should keep CLI `--registry-dir` aligned with `model_management.registry_dir`. Concurrent config PUTs were not established as a reproducible defect in this review and are not counted as a finding.

## Known contract limitation, deferred

Adjacent exposure-bracket frames can split when their preview pHash distance
exceeds the configured threshold; a low-quality singleton can then be retained
by coverage. The [public CR2 counterexample](benchmarks/2026-09-17-exposure-brackets/report.md)
measured a 0.34-second / 4.06-stop pair with distance 24/64 at threshold 10:
the dark frame scored 3.53/reject but was kept for singleton coverage. The third
frame had a real 50-second gap. This is a research-scene example, not a
human-labeled correction/preference target.

The current adjacent-time AND hash code (`src/material_agent/domain/grouper.py:229-255`)
matches the declared contract. Equalized/autocontrast pHash and dHash follow-up
comparisons are already complete, including subsequent false merges and candidate
failures. This is a known product limitation, not a new regression or an active
fix. Do not repeat the old comparison, fit its threshold, or promote normalization;
reopen only for new independent qualifying data and an attribution hypothesis.

## Non-findings and project status

### Product scoring and selection

- Group coverage remains explicitly separate from per-photo quality: `src/material_agent/domain/layered_decision.py:162-199` preserves quality decisions/reasons and stores a separate selection decision. No evidence in the reviewed code contradicted the documented requirement to retain one readable representative per group.
- The historical missing-eye proxy concern is not present in the current evidence path: `src/material_agent/domain/evidence_refinement.py:13-51` returns `unknown` without an observed eye ROI or high-confidence contextual evidence. The scorer adds a portrait eye signal only when the evidence value is non-null (`src/material_agent/domain/scoring_engine.py:493-509`). G1/G2 human-reference coverage and real portrait utility remain scientific admission gates, not defects inferred from missing labels.
- The score policy and preference quality are not promoted by synthetic/public component metrics alone. Existing roadmap/status docs keep quality improvement, G1/G2, and resource acceptance separate. This review did not repeat model or threshold experiments.

### Cancellation, resume, SQLite, and XMP

The runtime contracts and code inspected distinguish cancellation from failure, persist bounded work in resumable batches, preserve prior committed batches, reconcile abandoned records, and serialize mutating controllers. The XMP writer uses atomic sidecar replacement and projection receipts; a batch can still partially complete, by design. Existing October 19 recovery and October 21 Bridge evidence is bounded and accepted as recorded. Atomic DB/XMP crash consistency, same-job resume, vendor-ID preservation, and broader application/format round trips remain unverified acceptance topics, not confirmed implementation defects from this review.

### Inference lifecycle

The shared OpenVINO session bounds execution and compiled-cache ownership, records requested/compiled/actual device separately, and leaves execution readback unknown when unavailable. Client result caches include runtime/model/preprocessing identity and bounded storage. CPU fallback remains the baseline. The known large composition seam in `review_runtime.py` is architecture/tooling debt; no lifecycle defect with a reproducible current trigger was established in this pass.

### API, admin WebUI, Docker, and security boundary

The dashboard contract intentionally exposes an unauthenticated trusted-LAN operator surface. Current library item resolution canonicalizes the indexed path and rejects paths outside the configured input root (`src/material_agent/app/web_service.py:365-378`); thumbnails are generated in private work storage; Web-started score runs use dry-run and expose persisted preview data. Config replacement validates a temporary file, preserves redacted secrets, keeps a backup, and atomically replaces the active file. The documented constraint remains material: do not expose port 8776 to the Internet or an untrusted VLAN. No additional API path or container-boundary defect was substantiated in the reviewed paths.

### Documentation drift

At the review baseline, `README.md:177-182` still called the isolated XMP pilot pending, despite the finite isolated recovery and Bridge stages recorded as accepted in `docs/operations/2026-10-15-native-runtime-acceptance.md` and `docs/operations/2026-10-20-bridge-roundtrip-review.md`. This planning drift is corrected by the controller's companion README/roadmap/status update; it is not a product defect or release gate.

## Priority recommendations

| Priority | Work | Dependency / exit condition |
| --- | --- | --- |
| Now | Fix Web task restart/status reconciliation and protect active model assets from deletion. These affect running jobs and have direct process/code-path evidence. | Safe process identity/ownership and model task snapshot semantics. |
| Next | Regenerate DB-only output previews for processed-cache dry-run hits; distinguish XMP commit from subsequent receipt/SQLite failure in operator diagnostics. | Temp-directory integration and failure-injection acceptance; no source-media writes. |
| Later | Keep exposure-correction grouping deferred until new qualifying independent data and a new attribution hypothesis exist. Revisit the `review_runtime.py` composition seam only when a bounded behavior change makes ownership or verification materially harder. Keep atomic DB/XMP crash consistency, same-job resume, Capture One, JPEG embedded opt-in, and broader format claims as explicit follow-up scopes if product priority warrants them. | Concrete product priority and isolated acceptance evidence for each scope. |

## Self-review and coverage limits

Each actionable finding was checked against source and existing boundary tests; the restart, preview-cache, and post-commit DB-failure outcomes were also reproduced with controlled temporary-directory fixtures. The exposure result remains a deferred contract limitation, not a new regression. The model deletion race is grounded in the cross-process config snapshot, lazy asset load, and unguarded Web DELETE path; no production model or download was used. No speculative findings were retained for unauthenticated trusted-LAN operation, unknown execution-device readback, absent G1/G2 labels, Capture One, JPEG embedded writing, or untested format paths.

Coverage included review/grouping/scoring, resumability/cancellation, SQLite and XMP writer boundaries, local inference lifecycle, Web/API path handling, Docker entrypoint/image contract, tests referenced by module contracts, roadmap/status, and recent acceptance reports. The exact selected pytest command and temporary reproduction steps/results are recorded below. No real camera media, model download, service deployment, target-host state, live admin UI or production metadata was used; synthetic temporary sidecars belong to the unit-test scope. The independent reviewer did not rerun full-suite CI or observe deployment; controller verification is recorded separately below.

## Verification record

Selected boundary tests ran from the repository root with temporary test fixtures only:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -q -p no:cacheprovider \
  tests/test_app_services.py tests/test_runtime_state.py tests/test_review_job.py \
  tests/test_state.py tests/test_rescore.py tests/test_writer.py \
  tests/test_web_service.py tests/test_model_catalog_service.py \
  -k 'marks_operator_interruption_cancelled or does_not_downgrade_sigterm_to_a_file_error or sigterm_persists_cancelled_state_without_waiting_for_prepare_worker or marks_job_failed_and_records_event or reconciles_abandoned_jobs_and_sessions or sets_finished_at_for_terminal_job_and_session_states or treats_finished_with_errors_as_terminal_for_job_and_session or resumes_written_and_scored_files_from_artifacts or dry_run_repersist_score_payload_after_output_preview_is_added or processed_cache_invalidates_when_file_changes or score_cache_key_invalidates_done_and_scored_rows or group_selection_survives_processed_cache_round_trip or writer_new_xmp_write_is_atomic or writer_refuses_concurrent_existing_sidecar_change or writer_refuses_sidecar_created_during_new_write or writer_refuses_existing_symbolic_link_sidecar or writer_clear_ai_tags_refuses_concurrent_sidecar_change or rewrite_xmp_refuses_concurrent_existing_sidecar_change or rewrite_xmp_refuses_sidecar_created_during_new_write or rewrite_xmp_refuses_symbolic_link_sidecar or rewrite_xmp_dry_run_fails_closed_on_malformed_sidecar or web_tasks_are_always_dry_run_and_can_remove_sample_limit or web_config_rejects_invalid_policy_without_replacing_active_config or active_model_requires_force_before_managed_copy_is_deleted or apply_model_selections_uses_default_catalog_bundled_path'
```

Result: **26 passed, 134 deselected in 35.84s**. This includes CLI cancellation/failed-session and abandoned-run terminal states, fresh-score preview persistence, processed-cache input/config invalidation, selection round-trip, XMP concurrent-edit/created-sidecar/symlink refusal, single invalid Web config update, and model selection/delete guards. The selected tests do not cover Web manager restart, preview generation from a processed `done` cache hit, model deletion while a child is loading, concurrent config PUTs, or SQLite receipt persistence failure after XMP commit.

Additional isolated reproductions (all used temporary directories and synthetic files/processes):

1. **Web restart:** start a dummy child in a new process session which acquires the normal `run.lock` and waits; instantiate a second `WebTaskManager` on the same task snapshot/work directory. Observed old snapshot `interrupted`, old PID still alive, and new dummy task `failed` with exit code 9 because the old child retained the lock. Terminated and waited for both children afterward. This demonstrates manager-only restart behavior; it does not prove child survival across whole-container destruction.
2. **Cache preview:** create a temporary `SQLiteRuntimeRepository` job and a synthetic cache-hit payload with `skip_write=True` and matching previous group metadata; run `ReviewPhotosJob` in dry-run mode with a preview-writing callback. Observed `finished`, job-file `skipped`, callback not called, and latest `score_payload` without `output_preview`.
3. **XMP/DB ordering:** create a temporary runtime DB path, stub `_rewrite_xmp_atomically` to return `status=committed`, and inject an `OSError` from `record_xmp_projection`. Observed result `{"ok":0,"err":1}` and logs `ERROR recording XMP receipt` plus `ERROR writing ...` after the committed projection. No actual XMP file was touched.

## Controller assessment

The controller accepts the four scoped findings above and their P2/P3 priorities;
no P0/P1 issue was established by this review. Source checks and independent
temporary-fixture reproductions confirmed:

- restart: `interrupted`, no active task and a no-op cancel while the owned child
  remained alive holding `run.lock`; the controller terminated and waited for
  its own dummy child afterward;
- asset lifetime: an effective config retained managed A's path after B became
  selected and deletion of A succeeded without force; the captured path no
  longer existed. These were checksum-pinned synthetic bytes, not loaded models;
- cached preview: the matching-group cache payload produced one `skipped` result,
  zero preview callback calls and no persisted `output_preview`;
- receipt failure: one mocked committed writer result followed by injected
  persistence failure produced `ok=0/err=1` and both receipt/write error messages.
  No physical XMP write or corrupt-XMP claim follows from this injection.

The controller also ran `uv run pytest -q tests/test_grouper.py
tests/test_review_job.py::test_group_coverage_excludes_decode_errors_and_persists_in_artifacts`:
**79 passed in 0.71s**. These checks and the reviewer's 26 selected tests are
separate runs, not a new full-suite result. Baseline exact-head
[CI 39619203742](https://github.com/Team-Cyan/material-agent/actions/runs/39619203742)
was rechecked as successful for quality and publication. Live target state was
not re-observed.

The [follow-up plan](2026-10-22-follow-up-plan.md) maps the four fixes to R1–R4,
then R5's bounded attribution of existing RAW provenance gaps. The exposure
limitation, scientific gates and broader interoperability remain conditional.
This review/planning batch implements none of the four fixes.
