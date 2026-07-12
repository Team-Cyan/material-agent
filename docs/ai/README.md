# AI Workspace

This directory is the shared source of truth for AI assistants working in this repository.

## Files

- `shared-context.md`: repository context, commands, architecture, and working agreements
- `architecture/module-boundaries.md`: AI-oriented map of layer boundaries and safe edit zones
- `modules/`: module contracts for focused sub-agent work
- `playbooks/`: task-type execution guides for common changes
- `checklists/`: module-specific change checklists for safe edits and review
- `examples/`: example handoffs and concrete task patterns for agents to imitate
- `memory/`: long-lived AI collaboration memory and repository-level decisions
- `modules/anti-patterns.md`: quick warnings about common bad edits by module
- `prompts/debug.md`: reusable debugging prompt
- `prompts/feature.md`: reusable feature prompt
- `templates/subagent-task.md`: handoff template for narrow module-scoped tasks
- `reference/`: externally sourced implementation notes and compatibility findings
- `modules/omlx-harness.md`: legacy teacher/comparison harness contract
- `modules/local-benchmark.md`: isolated local benchmark and artifact contract
- `modules/local-model-stack.md`: optional local model blocks and runtime provenance
- `playbooks/tune-omlx-harness.md`: how to run and interpret the real-photo harness when tuning models or prompts
- `checklists/omlx-harness-checklist.md`: final review checklist for live-harness changes

## How To Use

- Prefer reading this directory first when an AI tool supports custom project instructions.
- If another AI-specific file exists elsewhere in the repo, treat it as a thin redirect to this directory.
- Keep AI-facing content in English so multiple tools can share the same knowledge base.
- For narrow implementation tasks, read `shared-context.md` first, then `architecture/module-boundaries.md`, then the relevant file in `modules/`.

## Recommended Read Paths

### For a narrow bug fix

1. `shared-context.md`
2. `architecture/module-boundaries.md`
3. `prompts/debug.md`
4. one relevant file in `modules/`
5. one relevant file in `playbooks/` if the task matches a known pattern

### For a narrow feature

1. `shared-context.md`
2. `architecture/module-boundaries.md`
3. `prompts/feature.md`
4. one relevant file in `modules/`
5. one relevant file in `playbooks/` if available
6. one relevant file in `checklists/` before finalizing the change

### For model tuning or harness work

1. `shared-context.md`
2. `architecture/module-boundaries.md`
3. `modules/omlx-runtime.md`
4. `modules/omlx-harness.md`
5. `playbooks/tune-omlx-harness.md`
6. `checklists/omlx-harness-checklist.md`
7. `reference/omlx-structured-output.md` if the change touches transport or structured output behavior

### For sub-agent delegation

1. `shared-context.md`
2. `architecture/module-boundaries.md`
3. one relevant file in `modules/`
4. `templates/subagent-task.md`
5. one relevant file in `checklists/` before handing back results
6. one relevant file in `examples/` if a concrete example would help tighten scope

### For long-lived repository guidance

1. `shared-context.md`
2. `memory/ai-collaboration-decisions.md`
3. `memory/repository-evolution-notes.md`
4. `memory/ai-doc-maintenance-policy.md`

## Directory Intent

- `architecture/` explains system boundaries and ownership
- `modules/` explains what each module owns and how to edit it safely
- `modules/anti-patterns.md` explains the most common bad edits to avoid
- `playbooks/` explains how to execute repeated task patterns
- `checklists/` explains what to double-check before considering a module change complete
- `examples/` shows what good module-scoped delegation and task framing look like in practice
- `memory/` preserves durable AI-collaboration decisions that should outlive one task
- `templates/` standardizes handoff and delegation
