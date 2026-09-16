# AGENTS.md

Repository entrypoint for coding agents. Keep reusable guidance in `docs/ai/` and `.agents/` as thin routing helpers.

## Task Routing

- Read `docs/ai/shared-context.md` once for repository working rules, then the smallest relevant contract in `docs/ai/modules/` and its code/tests.
- New to the product: `docs/ai/project-overview.md`; setup and commands: `README.md`.
- Unclear ownership or a cross-module change: `docs/ai/architecture/module-boundaries.md`.
- Hardware providers, Docker, or inference: `docs/ai/inference-runtime.md`; local scoring/embedding model choices: `docs/ai/model-selection.md`.
- Planning or project status: `docs/roadmap.md`. Resume unfinished work from `docs/operations/session-handoff.md` only when relevant.
- Repeated workflows and review aids: `docs/ai/README.md`. Select a matching playbook or checklist; do not load every layer for every task.

Retain relevant instructions, findings, and authorization already in context. Read plans and historical specs only when the task depends on their decisions.

## Project Boundaries

- The default backend is local. Preserve CPU fallback and prioritize Intel OpenVINO / ONNX Runtime for acceleration; do not reintroduce Ollama or OMLX as a default dependency.
- Keep secrets in ignored local files. The public repository owns application code and generic deployment contracts; private-machine control belongs outside it, as defined in `docs/ai/project-overview.md`.
- Preserve unrelated worktree changes and user photo metadata. Use dry-run defaults for destructive or external operations, checking each command's actual side effects: `run --dry-run` still writes runtime job state.
- Editing does not authorize committing, pushing, publishing, or operating live services. Follow the user's existing scope and applicable operator workflow.

`docs/ai/` owns reusable AI guidance. Resolve documentation conflicts by checking the relevant contract and current code; fix stale guidance without silently weakening a safety invariant.
