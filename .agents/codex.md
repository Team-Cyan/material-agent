# Codex Entry

This file is the Codex-specific entrypoint for this repository.

Keep it short. Use it as a navigation layer into `docs/ai/` and `docs/`, not as the full knowledge base.

## Read Order

For most Codex tasks, read in this order:

1. `docs/ai/project-overview.md`
2. `docs/roadmap.md`
3. The smallest relevant file under `docs/ai/modules/`
4. `docs/operations/session-handoff.md` only if recent unfinished work matters
5. A matching playbook or checklist only when the task shape clearly needs it

For harness engineering, switch to:

1. `.agents/harness-engineering.md`
2. `docs/ai/harness-workflow.md`
3. `docs/ai/modules/omlx-runtime.md`
4. `docs/ai/modules/omlx-harness.md`
5. `docs/ai/playbooks/tune-omlx-harness.md`
6. `docs/ai/checklists/omlx-harness-checklist.md`
7. `docs/harness-runbook.md`

Do not start by reading every playbook, every example, or every historical spec.

## Repository Model

- `.agents/`: repo-local agent assets and Codex fast paths
- `docs/ai/`: OpenAI-aligned documentation entry layer
- `docs/roadmap.md`: current repository state and next work
- `docs/operations/`: operator workflows and handoff notes
- `docs/`: human-facing runbooks and architecture guides

## Working Rules

- Prefer `docs/ai/` over duplicated instructions elsewhere.
- Identify the owning module before editing.
- Prefer one-module changes plus the thinnest required wiring change.
- Keep context narrow unless the task clearly crosses boundaries.
- Use benchmark for request-layer stability questions and harness for end-to-end output-quality questions.

## Useful Docs

- `docs/ai/project-overview.md`
- `.agents/harness-engineering.md`
- `docs/ai/harness-workflow.md`
- `docs/ai/reference-repos.md`
- `docs/roadmap.md`
- `docs/operations/session-handoff.md`
- `docs/ai/prompts/debug.md`
- `docs/ai/prompts/feature.md`
- `docs/ai/modules/anti-patterns.md`
- `docs/ai/templates/subagent-task.md`
- `docs/module-map.md`
- `docs/harness-runbook.md`

If this file and `docs/ai/` ever conflict, prefer the files in `docs/ai/`.
