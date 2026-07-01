# Module Editing Anti-Patterns

Use this file as a quick warning list for common bad edits in this repository.

## Review Pipeline

- Do not hide scoring policy changes inside runtime orchestration.
- Do not bypass resumability checks just to make a bug disappear.
- Do not add large amounts of module-specific logic directly into `review_runtime.py` if a domain or adapter layer owns it better.
- Do not reintroduce eager imports of scoring/runtime modules in CLI entry points when a lazy wrapper preserves the same behavior.

## Scoring Engine

- Do not change score field names casually.
- Do not mix new user-facing text concerns into score assembly without checking whether they belong in the writer or commentary boundary.
- Do not change signals without checking `rescore`.
- Do not force screening backends to import at module load time when screening may be disabled for the whole run.

## Grouping

- Do not add expensive global similarity work when the design expects adjacent-group merge only.
- Do not silently change group ordering semantics.
- Do not tie grouping behavior to downstream ranking logic.

## XMP Writer

- Do not fix only one write path when two paths exist.
- Do not drop non-machine tags unless the task explicitly permits it.
- Do not leak more writer internals into rewrite services unless there is no cleaner option.

## Runtime State

- Do not blur runtime-state and processed-state responsibilities just because they share one DB path.
- Do not rename stored fields without tracing every reader.
- Do not change status meanings in one place only.

## OMLX Runtime

- Do not relax fail-fast checks just to suppress an operational problem.
- Do not move policy logic into the tiny transport layer.
- Do not change probe payloads without checking preflight consumers and tests.
