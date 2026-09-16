# Agent Assets

This folder contains repo-local assets for coding agents.

Keep durable project knowledge in `docs/`. Use `.agents/` only for thin agent-facing assets such as Codex fast paths, local prompts, or routing helpers that are useful inside this repository.

## Contents

- `codex.md`: Codex task routing and repository navigation.
- `harness-engineering.md`: route for explicitly requested OMLX comparison work; local production evaluation follows `docs/ai/modules/local-benchmark.md`.

## Boundaries

- Do not turn `.agents/` into a second knowledge base.
- Do not store secrets, local credentials, run logs, or scratch notes here.
- Keep project state, module knowledge, specs, plans, and operations notes under `docs/`.
- `docs/ai/` owns reusable guidance. Resolve conflicting claims against the relevant contract and current evidence without silently weakening safety boundaries.
