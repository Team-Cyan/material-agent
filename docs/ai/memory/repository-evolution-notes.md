# Repository Evolution Notes

This file records durable observations about how the repository has been organized for AI collaboration.

It is not a changelog and not a task tracker.

## Current Notes

### The project has moved from generic prompts to layered AI guidance

The repository originally had a lighter AI setup centered on:

- shared context
- debug prompt
- feature prompt

It now uses a more explicit layered structure:

- architecture boundaries
- module contracts
- task playbooks
- module checklists
- concrete examples
- long-lived memory

This shift was made to support smaller context windows, cleaner sub-agent delegation, and more reliable module-scoped edits.

### Module contracts are designed around ownership, not code inventory

The goal of `modules/` is not to describe every file.

The goal is to let an agent quickly answer:

- what this module owns
- what it should not touch
- what inputs and outputs it must preserve
- how to verify a narrow change

### Playbooks encode repeated task shapes

Playbooks exist because many repository tasks repeat:

- scoring adjustments
- DB-backed field changes
- XMP output changes
- OMLX runtime debugging

Encoding these patterns reduces improvisation and makes sub-agent tasks more consistent.

### Checklists are meant for closure, not planning

Checklists should be consulted near the end of a task to reduce regressions and forgotten verifications.

They should not replace module contracts or playbooks.

### Examples teach framing quality

Examples are included because agents often benefit from concrete demonstrations of:

- good task scoping
- safe allowed-file lists
- explicit out-of-scope boundaries
- justified cross-module work

## When To Update

Update this file when the repository changes how AI collaboration is structured.

Do not update it for ordinary feature work or one-off bug fixes.
