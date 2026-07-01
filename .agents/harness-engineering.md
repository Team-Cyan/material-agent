# Harness Engineering Entry

Use this entry when the task is specifically about OMLX harness work instead of general repository changes.

Read in this order:

1. `docs/ai/shared-context.md`
2. `docs/ai/architecture/module-boundaries.md`
3. `docs/ai/modules/omlx-runtime.md`
4. `docs/ai/modules/omlx-harness.md`
5. `docs/ai/playbooks/tune-omlx-harness.md`
6. `docs/ai/checklists/omlx-harness-checklist.md`
7. `docs/harness-runbook.md`

Working rules:

- keep benchmark and harness responsibilities separate
- use `omlx-benchmark` for request-layer stability, schema, and latency tuning
- use `omlx-harness` for real-sample output quality, commentary quality, and default-model decisions
- prefer small fixed sample sets so before/after comparisons stay meaningful
- avoid broad refactors while tuning harness behavior; edit the owning module and the thinnest wiring layer only

If this file conflicts with `docs/ai/`, prefer `docs/ai/`.
