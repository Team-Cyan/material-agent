# AGENTS.md

This file is the repository entrypoint for coding agents.

Keep this file short. Treat it as a table of contents, not the full knowledge base.

## Read Order

For most tasks, read in this order:

1. `docs/ai/project-overview.md`
2. `docs/roadmap.md`
3. The smallest relevant file under `docs/ai/modules/`
4. `docs/operations/session-handoff.md` only if the task depends on recent unfinished work
5. A matching playbook, checklist, spec, or plan only when the task shape clearly needs it
6. `docs/ai/inference-runtime.md` for hardware-provider, Docker, or model-runtime work

Do not start by reading every module doc, every playbook, or every historical plan.

## Repository Model

- `AGENTS.md`: thin agent entrypoint
- `docs/ai/`: OpenAI-aligned documentation entry layer
- `.agents/`: repo-local agent assets and harness navigation
- `docs/roadmap.md`: current repository state and next work
- `docs/operations/`: operator workflows and handoff notes
- `docs/`: human-facing runbooks and architecture guides

## Working Rules

- Keep AI-facing docs in English.
- Reply to the human user in their preferred language.
- Prefer small, well-bounded sessions.
- Work on one owning module at a time when possible.
- Keep `.agents/` thin; keep durable knowledge in `docs/`.
- Update the most relevant AI doc when repository behavior or safe-edit guidance materially changes.

## Safety

- Keep secrets in gitignored local files.
- Do not commit credentials, tokens, or cookies.
- Prefer dry-run defaults for destructive or external side-effect operations.

## Project-Specific Notes

- `docs/ai/` is the canonical AI workspace in this repository.
- `material-agent` is NAS-first and local-runtime-first.
- Do not reintroduce Ollama or OMLX as a default dependency.
- Prioritize Intel OpenVINO / ONNX Runtime for the first accelerated path.
- If another AI-specific file conflicts with `docs/ai/`, prefer `docs/ai/`.

## Useful Docs

- `docs/ai/project-overview.md`
- `docs/ai/inference-runtime.md`
- `docs/ai/reference-repos.md`
- `docs/roadmap.md`
- `docs/operations/session-handoff.md`
- `.agents/README.md`
- `.agents/codex.md`
- `.agents/harness-engineering.md`
- `docs/ai/README.md`
- `docs/ai/modules/*.md`
- `docs/ai/playbooks/*.md`
- `docs/ai/templates/*.md`
- `docs/module-map.md`
- `docs/harness-runbook.md`
