# Harness Workflow

Use this document when the task is about OMLX benchmark or harness engineering.

## Goal

Keep request-layer tuning and end-to-end output evaluation separate.

- `omlx-benchmark` answers: is the request path stable, compatible, and reasonably fast?
- `omlx-harness` answers: does the real review pipeline produce believable output on real sample photos?

## Read Order

1. `docs/ai/project-overview.md`
2. `docs/ai/modules/omlx-runtime.md`
3. `docs/ai/modules/omlx-harness.md`
4. `docs/ai/playbooks/tune-omlx-harness.md`
5. `docs/ai/checklists/omlx-harness-checklist.md`
6. `docs/harness-runbook.md`

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
- runtime alignment for the default production path

## Working Rules

- Keep sample sets small and stable.
- Compare before and after on the same sample set.
- Do not treat harness work as a broad refactor invitation.
- Edit the owning module and the thinnest required wiring layer only.
