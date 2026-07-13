# Review Pipeline Module Contract

## Purpose

This module owns the end-to-end execution flow for `material-agent run`.

It does not define image-quality policy itself. Instead, it orchestrates grouping, scoring, commentary, persistence, and write-back.

## Main Files

- `src/material_agent/app/review_service.py`
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/app/jobs/review_photos.py`
- `src/material_agent/app/job_executor.py`

## Responsibilities

- create runtime session and job records
- scan or receive target files
- wire the concrete collaborators for grouping, scoring, commentary, and writing
- run the ordered stages: discover, group, score, comment, write, finalize
- support resumability through runtime artifacts and processed-state lookups
- emit runtime events for progress and later GUI consumption
- preserve an import-light CLI and command entry path for non-review commands

## Non-Goals

- scoring formulas
- scene grouping heuristics
- XMP XML details
- low-level backend HTTP transport
- SQLite schema migrations beyond direct runtime needs

## Inputs

- `input_dir`
- validated and normalized config
- processed-state repository
- runtime repository
- progress sink
- `dry_run` flag

## Outputs

- session/job/job_file/event records in runtime SQLite
- score payload artifacts for resumability
- written XMP sidecars through the writer adapter
- processed-state rows through the processed repository

## Terminal Status Semantics

- `finished` means every targeted file reached the expected terminal write path without per-file failures
- `finished_with_errors` means the batch completed orchestration but one or more files failed during scoring or write-back
- `failed` means the pipeline itself broke before it could reach a valid terminal batch summary
- `cancelled` means SIGTERM or another controller cancellation interrupted the run; it must not be collapsed into `failed`

Runtime file states distinguish real writes from simulations and cache reuse:

- `written` means the configured terminal writer completed;
- `simulated` means a dry-run reached a terminal result without a source write;
- `skipped` means a valid unchanged `done` result was reused without pretending
  that a write occurred in the current run.

## Invariants

- pipeline stage ordering must remain stable
- `ReviewPhotosJob` is resumable at file level and partially at group level
- cached scored state may skip recomputation
- processed-state `done` finalization must persist commentary sections in the same terminal write
- a file must not be marked `done` before its terminal commentary payload is durable
- batch-level partial failures must not be reported as clean success
- already written files should not be rewritten unless the workflow explicitly requests it
- discovery and grouping receive the complete current source set, including
  valid `done` rows, so a new frame can change an existing burst's stable group
  membership and rank without rescoring unchanged pixels
- group IDs are membership-derived from sorted member paths rather than run order;
  cached scores may be reused, but group/rank metadata and terminal output must
  be refreshed when membership or rank changes
- dry-run may persist runtime observability but must not create processed score,
  `done`, XMP, or rating output
- one work directory has one mutating controller at a time; `run` and mutating
  maintenance commands share the same exclusive lock
- startup reconciles abandoned open/running/paused runtime records before a new
  run, and SIGTERM produces durable `cancelled` state with bounded shutdown
- orchestration code should remain thin and delegate real rules outward

## Typical Safe Changes

- add a new runtime event
- improve resumability behavior
- inject a new collaborator into runtime wiring
- adjust dry-run behavior
- tighten preflight validation or failure propagation

## Risky Changes

- changing when files are considered done or resumable
- splitting `mark_done` and commentary persistence back into separate write paths
- broadening `finished` to include partial per-file failures
- changing stage ordering
- mutating score payload shape without checking all consumers
- mixing domain logic into orchestration code
- filtering `done` files before grouping, which silently makes incremental rank
  and group metadata inconsistent
- bypassing the shared run lock from a new mutating command

## Files Usually Safe To Edit Together

- `src/material_agent/app/review_service.py`
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/app/jobs/review_photos.py`
- `tests/test_review_job.py`
- `tests/test_app_services.py`

## Minimal Verification

- `make test`
- or narrower:
- `pytest tests/test_review_job.py tests/test_app_services.py tests/test_runtime_state.py`

## Known Tensions / Technical Debt

- `review_runtime.py` is a large composition root and currently carries many responsibilities.
- Sync orchestration wraps async model work through `run_coro_sync`, which keeps the CLI path simple but couples runtime flow to sync boundaries.
- The resumability logic mixes runtime artifacts and processed-state reads, which is practical but conceptually dense for new contributors.
- Review-related code is heavy enough that CLI entry modules should keep lazy command loading intact, or light admin commands will regress in startup cost.
- Partial-success recovery now has explicit terminal status semantics, but any future GUI or automation layer must treat `finished_with_errors` as a first-class outcome rather than collapsing it into `finished`.
