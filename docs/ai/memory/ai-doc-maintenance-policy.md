# AI Doc Maintenance Policy

This file defines how the AI documentation system in this repository should be maintained over time.

## Goals

- keep `docs/ai/` useful for real implementation work
- prevent drift between entry-point files and the canonical AI workspace
- preserve a small-context, module-oriented workflow
- avoid turning `docs/ai/` into a noisy archive of stale task notes

## Maintenance Principles

### Prefer updating an existing layer before adding a new one

Before creating a new directory or document type, check whether the change belongs in:

- `modules/`
- `playbooks/`
- `checklists/`
- `examples/`
- `memory/`

Add new layers only when the current structure cannot express the need cleanly.

### Keep long-lived guidance separate from task residue

- Put durable conventions in `memory/`
- Put reusable execution guidance in `playbooks/`
- Put module ownership and invariants in `modules/`
- Do not store temporary task notes in any of these places

### Keep entry points thin

- `AGENTS.md` and `.agents/` routing files should remain thin
- If logic grows in entry points, move it back into `docs/ai/`

### Optimize for the next focused edit

When updating `docs/ai/`, ask:

- will this help an agent make a smaller, safer change?
- will this reduce unnecessary repo-wide reading?
- will this improve sub-agent handoff quality?

If the answer is no, the update may not belong in `docs/ai/`.

## Update Triggers

Consider updating AI docs when:

- a module boundary changes
- a repeated task pattern appears more than once
- agents repeatedly miss the same verification or scoping step
- a durable collaboration decision is made
- a strong example emerges that would improve future task framing

## Anti-Patterns

- adding one-off task notes to `memory/`
- duplicating the same rule in many places
- letting entry-point files become full copies of `docs/ai/README.md`
- turning checklists into planning documents
- turning examples into vague theory instead of concrete framing
- using playbooks for repository-specific ownership that belongs in `modules/`

## Review Questions

Before finalizing an AI-doc change, ask:

- is this the smallest correct place for this information?
- will another agent know when to read this?
- is there an existing file that should be updated instead?
- does this increase clarity more than it increases surface area?
