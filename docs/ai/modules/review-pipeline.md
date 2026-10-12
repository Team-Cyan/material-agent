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

- explicit task/CLI `input_dir` (never sourced from durable configuration)
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
- commentary-disabled singleton runs emit each batch stage once and must not
  construct per-file async commentary wrappers
- runtime persistence is committed in bounded batches; cancellation may roll
  back only the current batch, while previously committed batches stay resumable
- one work directory has one mutating controller at a time; `run` and mutating
  maintenance commands share the same exclusive lock
- `input_dir` and `reprocess` are per-run inputs; legacy copies in durable
  configuration are stripped before explicit task/CLI overrides are applied
- the legacy Python `Pipeline(config)` wrapper may accept these fields only as
  in-memory invocation inputs and re-injects them after stable-config normalization
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

## Group Finalization Boundary

`review_runtime.py::finalize_group` keeps the sequence: empty short circuit,
domain-owned bounded refinement, optional commentary from refined quality,
shallow payload copies attaching commentary, then existing domain selection.
The same-file `_refine_candidate` helper supplies decode/scoring collaborators
and rejects a non-larger focus observation before scoring. `_build_group_commentary`
owns commentary input construction and its existing synchronous async boundary;
disabled commentary creates no coroutine. Refinement config is read per
finalization invocation, while commentary enablement is captured when the
executor is built. Selection config remains read after commentary.

Refinement retains unrelated payload keys and changes `skip_write` only after
successful decode/gain/scoring; domain validation can still retain the baseline
on candidate failure. Ordinary refinement failures remain auditable, while
interruptions propagate. Commentary and selection errors propagate. Commentary
uses quality decisions before coverage selection. Finalization preserves input
order and nested aliases according to the existing domain helpers; it does not
sort for writer ranks. `ReviewPhotosJob` owns ranking, cached/resumed handling and
the all-`skip_write` group bypass. The terminal writer still owns rating and
metadata protections.

Future relation and selection rules belong in the domain, feature/cache storage
in adapters, and collaborator scheduling in this application layer. Follow the
existing [Batch 5 production/cache design](../../operations/2026-09-26-culling-improvement-plan.md#batch-5--opt-in-production-design-and-cache-integration)
instead of adding a strategy framework here. Feature identity, ordered
directional relation identity, candidate-set identity and selection-result
identity have separate dependencies; a policy revision alone does not identify
graph contents. Preserve honest per-photo quality independently of content
coverage. Stable event/window identity is distinct from exact membership identity
and needs explicit insert/delete/split/merge semantics. Keep the legacy
membership-derived group ID. Incremental selection must equal full affected
component recomputation, including reverse witnesses; no fixed-radius bound is
assumed. These are future design seams, with no new cache, persistence or
production-mode integration in current finalization.

## Preparation Memory Observations

`ReviewPhotosJob` emits one best-effort `Preparation memory diagnostics` log per
score-consumption invocation, including interruption/failure exits. It adds no
runtime events, score fields, persistence or API output. The current prefetch cap
of 32, prepare/prime/score order, reference lifetimes and resume behavior remain
unchanged. The app-owned `preparation_memory.py` helper imports no image/model
stack and observes only the concrete runtime's already loaded `RawFrame` type.

Samples occur before/after consuming a prepared future, before/after an existing
prime call, after scoring and on per-file scoring failure. Each sample includes
the existing current preparation (which can still be the previous item), existing
prime-list aliases (which can retain older frames), and already completed,
successful pending futures. Unready/failed futures are counted without waiting;
telemetry introduces no completion callbacks, decode/model calls or GC. Samples
are not complete lifetime/allocation peaks and omit worker-local and client-owned
references. Aggregation retains only scalars, never frames or buffers.

The `material-agent.preparation-memory.v1` log contains per-stage `sample_count`,
`sampled_max` and `unknown_samples`. Maxima for different metrics may come from
different samples. `prepared_live_count` deduplicates preparation identities;
cached preparation dictionaries count but contribute no frame storage.
`frame_live_count` counts distinct supported frames. `unknown_component_count`
counts each distinct unsupported preparation or frame, or each unsupported
storage field in a supported frame; it can exceed the number of preparations.
Memory observations
inspect only `jpeg_bytes`, `gray`, `pixels` and `focus_gray`:

- `array_field_nbytes` sums logical NumPy `nbytes` across explicit fields of unique
  frames; aliases can repeat here. It is not resident memory.
- `array_storage_bytes` and `jpeg_storage_bytes` are supported unique-owner byte
  subtotals. NumPy view/base chains are bounded to 64 links; contiguous owned
  array roots and byte-backed buffers are supported. Object arrays, foreign or
  unrecognized owners stay unknown. JPEG identities deduplicate shared bytes.
- `known_payload_bytes` deduplicates the union of supported array and JPEG
  storage, including a JPEG also used as an array buffer. `prepared_payload_bytes`
  is this estimated total only when all inspected payloads are supported;
  otherwise it is unknown (absent from maxima, counted in `unknown_samples`).
  Bookkeeping, Python object overhead, cached score metadata, model tensors,
  decoder/native allocations and unsampled references are excluded.
- `current_rss_bytes` samples Linux `/proc/self/statm` resident pages multiplied
  by page size; other platforms or read failures stay unknown.
- `process_highwater_rss_bytes` uses `resource.getrusage(RUSAGE_SELF).ru_maxrss`:
  Linux KiB are converted to bytes, macOS reports bytes. Other platforms or
  failures stay unknown. This is the process-lifetime high-water mark, including
  work before the job; it is not a job's peak or a prepared-payload metric.

The log labels platform, sources, bytes units and sampling scope explicitly.
Its `status` describes the score-consumption exit, so a complete invocation can
still include per-file failures (observed at `score_failed`).
Ordinary sampler/log failures cannot fail successful scoring; operator
interruptions still propagate. An empty/all-resumed invocation has no samples
and makes no memory claim. Bounded synthetic instrumentation timing measures
observation overhead only; tuning and production/real-data savings require
separate evidence and scope.
