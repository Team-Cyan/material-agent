# Shared AI Context

This file is the canonical AI guidance for `material-agent`.

## Read Order

1. `README.md` for setup, commands, and user-facing behavior
2. `AGENTS.md` or `.agents/codex.md` as entry points
3. this file for repository-specific working rules
4. `docs/ai/architecture/module-boundaries.md` for layer ownership and safe edit zones
5. the relevant file in `docs/ai/modules/` for narrow implementation work
6. the relevant file in `docs/ai/playbooks/` if the task matches a repeated pattern
7. the relevant file in `docs/ai/checklists/` before finalizing a module change
8. the relevant file in `docs/ai/examples/` if the task needs a concrete model to imitate
9. the relevant file in `docs/ai/memory/` if the task touches durable AI-collaboration conventions
10. `docs/ai/modules/anti-patterns.md` if the task is at risk of broadening or mixing responsibilities

## Communication

- Use English in AI-facing files and prompts.
- Match the user's preferred language in user-facing responses.
- Preserve original command names, paths, config keys, and code identifiers.

## Repository Snapshot

- `material-agent` is a NAS-first local photo culling and scoring tool for RAW image workflows.
- The core flow is: scan -> group -> score -> write XMP and SQLite state.
- The default runtime path is `backend: local`; it must not require Ollama, OMLX, or another HTTP model service.
- Intel OpenVINO / ONNX Runtime is the first accelerated runtime target.
- CPU fallback must remain valid on every NAS-class host.
- Main risk areas are scoring, grouping, writer behavior, local runtime provider selection, and XMP/state compatibility.

## Working Rules

- Prefer minimal, additive changes over broad refactors.
- Assume the worktree may contain active user edits; do not overwrite unrelated changes.
- If behavior changes in scoring, grouping, exporting, XMP writing, local inference, or persistence, review tests and docs together.
- Prefer repository verification commands such as `make test` and `make check`.
- Prefer module-scoped changes and the smallest useful context window.
- For narrow tasks, identify one owning module before reading unrelated code.
- For common task shapes, prefer following a playbook instead of improvising a new workflow.
- If delegating work to a sub-agent, pass only the owning module contract, the minimal file list, and explicit acceptance checks.
- When a task crosses module boundaries, document the boundary crossing explicitly instead of silently broadening scope.
- Before considering a narrow module task complete, review the corresponding checklist in `docs/ai/checklists/`.
- Prefer concrete examples over abstract wording when teaching an agent how to scope a task.
- Keep durable AI-collaboration decisions in `docs/ai/memory/`, not scattered across task documents.
- Use `docs/ai/modules/anti-patterns.md` as a guardrail when a task starts drifting across boundaries or hiding the real owning module.

## Commit Convention

- Use Conventional Commits with the format `type(scope): summary`.
- Keep the summary in English and imperative mood.
- Prefer these types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`.
- Prefer these scopes when relevant: `pipeline`, `writer`, `state`, `scorer`, `vision`, `cli`, `config`, `ai`, `git`, `tests`.
- Examples:
  - `feat(cli): add export command`
  - `fix(writer): preserve user keywords in XMP`
  - `docs(ai): unify shared project guidance`

### Commit Cheat Sheet

- Use `feat` for new user-facing or developer-facing behavior.
- Use `fix` for bug fixes or compatibility corrections.
- Use `refactor` for code structure changes without intended behavior change.
- Use `test` for test-only additions or updates.
- Use `docs` for documentation and AI-guidance changes.
- Use `chore` for repository maintenance, ignore rules, or non-feature tooling updates.
- Use `perf` for measurable efficiency or throughput improvements.

### Preferred Scopes

- `pipeline`: orchestration, scoring flow, async execution
- `vision`: local inference runtime, ONNX/OpenVINO adapters, model response handling
- `writer`: XMP output and write-back behavior
- `state`: SQLite persistence, status tracking, migrations
- `cli`: commands, flags, user entry points
- `config`: configuration schema, validation, weights
- `scorer`: individual scoring components
- `progress`: TUI or progress reporting
- `grouping`: scene grouping and merge logic
- `ai`: `docs/ai/`, prompt files, agent guidance
- `git`: `.gitignore`, git metadata, repository housekeeping

## Source Of Truth

- Do not duplicate large sections from `README.md` here.
- Keep this file focused on AI-specific guidance, not full project documentation.
