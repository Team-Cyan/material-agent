# Harness Workflow

Use this document when the task is about OMLX benchmark or harness engineering.

## Goal

Keep request-layer tuning and end-to-end output evaluation separate.

- `omlx-benchmark` answers: is the request path stable, compatible, and reasonably fast?
- `omlx-harness` answers: does the real review pipeline produce believable output on real sample photos?

## Task Routing

Follow `AGENTS.md` for repository rules. For request-layer work, read `docs/ai/modules/omlx-runtime.md`; for pipeline output evaluation, read `docs/ai/modules/omlx-harness.md`. Use the matching command in `docs/harness-runbook.md`, and consult the playbook or checklist only for relevant risks.

This is the legacy OMLX comparison path. Local production evaluation uses `docs/ai/modules/local-benchmark.md`; do not select OMLX merely because a task mentions model tuning or a harness.

## When To Use Benchmark

Use `omlx-benchmark` first when changing:

- transport or schema behavior
- contract mode
- prompt preset shape
- image resize or JPEG settings
- token caps or sampling behavior

## When To Use Harness

Use `omlx-harness` when changing:

- model choice
- model profiles
- commentary quality guards
- prompt wording that affects real outputs
- runtime alignment for the explicitly selected OMLX comparison path

## Working Rules

- Keep sample sets small and stable.
- Compare before and after on the same sample set.
- Do not treat harness work as a broad refactor invitation.
- Edit the owning module and the thinnest required wiring layer only.
