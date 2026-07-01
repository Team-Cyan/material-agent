# Module Boundaries

This file is the AI-friendly map of the `material-agent` codebase.

Use it to decide which module to read, which files are safe to edit, and which layers should stay untouched during a focused change.

## Top-Level Flow

The primary review pipeline is:

`shells/cli -> commands -> app services/runtime -> domain rules -> adapters -> filesystem / SQLite / local inference backends`

The runtime path for `material-agent run` is:

1. CLI parses arguments in `shells/cli/main.py`
2. command wiring happens in `commands/scoring.py`
3. `ReviewRunService` creates session/job records
4. `build_review_job_executor()` wires runtime collaborators
5. `ReviewPhotosJob` executes `group -> score -> comment -> write`
6. adapters persist runtime state, processed results, XMP sidecars, and local inference artifacts

## Layer Rules

### `shells/cli`

- Responsibility: argument parsing and command dispatch only
- Safe changes: add parser flags, route to an existing command
- Avoid: embedding business logic or persistence details here
- Keep import cost low: do not eagerly import the full scoring stack when a thin wrapper or branch-local import is enough

### `commands`

- Responsibility: thin translation from CLI args to app services
- Safe changes: config overrides, preflight hooks, command-level orchestration
- Avoid: scoring logic, grouping rules, XMP formatting, direct model parsing
- Keep branch-specific imports local when that avoids loading heavy runtime modules for unrelated commands

### `app`

- Responsibility: orchestration, runtime lifecycle, service composition, resumability
- Safe changes: session/job flow, service interfaces, executor wiring
- Avoid: low-level image scoring math, raw SQL schema design unless the task is explicitly state-related

### `domain`

- Responsibility: pure or mostly-pure business rules
- Safe changes: grouping rules, scoring policy, commentary fallback rules, layered decision policy
- Avoid: CLI concerns, raw subprocess management, SQLite schema wiring

### `adapters`

- Responsibility: integration with external systems
- Safe changes: ExifTool interaction, SQLite repositories, local inference providers, progress sinks
- Avoid: changing domain policy here unless the task explicitly spans both layers

## Preferred Read Paths By Task

### Add or adjust review pipeline behavior

Read first:

- `src/material_agent/app/review_service.py`
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/app/jobs/review_photos.py`

### Change grouping behavior

Read first:

- `src/material_agent/domain/grouper.py`
- `src/material_agent/app/review_runtime.py`
- `tests/test_grouper.py`

### Change score computation or decision logic

Read first:

- `src/material_agent/domain/scoring_engine.py`
- `src/material_agent/domain/layered_decision.py`
- `src/material_agent/app/review_runtime.py`
- `tests/test_scorers.py`
- `tests/test_review_job.py`

### Change XMP write-back behavior

Read first:

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- `tests/test_writer.py`

### Change runtime / processed persistence

Read first:

- `src/material_agent/adapters/state/sqlite_runtime.py`
- `src/material_agent/adapters/state/processed_sqlite.py`
- `src/material_agent/app/review_service.py`
- `tests/test_runtime_state.py`
- `tests/test_state.py`

### Change local inference runtime or provider selection

Read first:

- `docs/ai/inference-runtime.md`
- `src/material_agent/clients/base.py`
- `src/material_agent/clients/local.py`
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/utils/config_validator.py`

### Change copied legacy OMLX behavior

Treat copied OMLX modules as migration debt unless the user explicitly asks to preserve or port them. Do not make them part of the default path.

## Safe Module-Scoped Delegation

Good sub-agent tasks usually have all of these properties:

- one primary module
- one clear behavior change
- a narrow allowed file list
- explicit verification commands
- explicit out-of-scope rules

Example safe delegation:

- "Adjust fast-screening rejection thresholds inside score computation only"
- "Preserve more user XMP tags without changing ranking logic"
- "Add one runtime event to job execution without touching scoring math"

Example unsafe delegation:

- "Refactor the entire review pipeline"
- "Clean up architecture while adding a feature"
- "Fix all SQLite and model issues together"

## Cross-Module Couplings To Watch

- `review_runtime.py` is the main composition seam; many changes appear local but actually need wiring updates here.
- `processed_sqlite.py` and `sqlite_runtime.py` share one runtime database path but represent different concepts.
- `domain/scoring_engine.py` depends on config structure, scorer definitions, backend client behavior, and decision summarization.
- `ExifToolXMPWriter` is coupled to both XMP output format and later rewrite flows.
- `commentary` behavior affects both user-facing XMP descriptions and DB commentary fields.
- CLI entry modules look thin but can accidentally become startup bottlenecks if they reintroduce eager imports of scoring, screening, or runtime modules.

## Default Editing Strategy

1. Identify the smallest owning module.
2. Read its contract document in `docs/ai/modules/`.
3. Edit only the owning module plus the thinnest required wiring layer.
4. Verify using the smallest relevant tests first.
5. Expand verification only if the change crosses a module boundary.
