# Agent Assets

This folder contains repo-local assets for coding agents.

Keep durable project knowledge in `docs/`. Use `.agents/` only for thin agent-facing assets such as Codex fast paths, local prompts, or routing helpers that are useful inside this repository.

## Contents

- `codex.md`: Codex-specific read order and repository navigation.
- `harness-engineering.md`: fast path for OMLX benchmark and harness work.

## Boundaries

- Do not turn `.agents/` into a second knowledge base.
- Do not store secrets, local credentials, run logs, or scratch notes here.
- Keep project state, module knowledge, specs, plans, and operations notes under `docs/`.
- If an `.agents/` file conflicts with `docs/ai/`, prefer `docs/ai/`.
