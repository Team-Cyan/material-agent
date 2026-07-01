# AI Collaboration Decisions

This file stores long-lived decisions about how AI assistants should work in this repository.

Do not use it for temporary task notes.

## Current Decisions

### `docs/ai/` is the canonical AI workspace

- Repository-level AI guidance should be centralized in `docs/ai/`
- Entry-point files such as `AGENTS.md` and `.agents/` routing files should stay thin and point here
- If instructions drift, prefer updating `docs/ai/` and keeping entry points minimal

### Prefer module-scoped work over repo-wide context

- Agents should identify one owning module before making a narrow change
- Module contracts are the first stop for focused implementation work
- Cross-module tasks are allowed, but the boundary crossing should be explicit

### The AI documentation stack is layered

The intended order of use is:

1. entry and shared context
2. architecture boundaries
3. module contracts
4. task playbooks
5. module checklists
6. concrete examples

This layering exists to reduce context size, improve delegation quality, and avoid unnecessary repo-wide reads.

### English for AI-facing docs, Chinese for human-oriented guidance

- AI-facing files under `docs/ai/` should stay in English
- Human-oriented summary docs may be written in Chinese when that better matches the working style of the repository owner
- Commands, identifiers, paths, and config keys should remain in their original language/form

### Human-readable overview should stay centralized

- The Chinese overview document is intended for readers who may not inspect code directly
- Prefer one central human-oriented overview before splitting into many human-facing files
- Add more human-facing files only when the overview becomes meaningfully hard to navigate

## Maintenance Rules

- Update this file only for durable collaboration decisions
- Do not add per-task status here
- If a new decision affects task execution, also update `docs/ai/README.md` or `docs/ai/shared-context.md`
