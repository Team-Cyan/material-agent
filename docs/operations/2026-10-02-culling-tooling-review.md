# Culling tooling publication review — October 2, 2026

Scope: publish the completed reference tooling, constructed candidate-graph
diagnostics and controlled synthetic representation runner after review. The
user authorized continuing and pushing this batch. Application code, default
grouping, thresholds, dependencies, source-photo metadata and runtime services
are unchanged. No real-photo quality evaluation or new acquisition is included.

## Evaluation-gate correction

The reference validator previously included pairs whose two directions were
both abstentions in `eligible_pairs` and `independent_families`. A constructed
regression with 12 definite pairs from six families plus 20 unknown-only pairs
from ten more families met the per-split direction/category quotas and incorrectly
returned `quota_ready_pending_human_audit` with 32 pairs / 16 families.

The validator now excludes abstention-only pairs before counting eligible pairs
and families. The same input reports 12 pairs / six families and
`reference_insufficient`, preserving all raw judgments. One definite direction
still qualifies its pair once and contributes only that direction to the class
quota. New tests cover mixed quota padding, all three abstention labels and
one-direction eligibility. Synthetic fixtures do not become human evidence.

## Verification and publication

Before the correction, the full local suite passed 1,040 tests with ten skips
in 26.79 seconds. The corrected reference tests passed 50 tests in 0.12 seconds.
The independent read-only review confirmed two additional runner problems:

- Standard JSON `1e309` was accepted as an infinite time/RSS limit, disabling
  overrun detection. Limits now require positive finite numbers, reject booleans
  and wrong numeric types, and cannot exceed the frozen four-case / 90-second /
  2,000,000,000-byte ceilings. Smaller time/RSS limits remain usable.
- A protocol stored inside a resumed output directory could be overwritten by
  a case or summary result. The runner now rejects protocols anywhere in the
  output tree, before creating output or generating inputs.

Regression tests reproduce both failures without image evaluation and assert
that rejected inputs remain unchanged and no output is created. The original
synthetic runner and accepted evidence are preserved in commit `61d3b3f`.
Hardening changes its code digest, so the current runner intentionally refuses
resume of those older records; no result hash is rewritten or relabeled. The
relation algorithm, frozen protocol and published synthetic results are intact.

Final validation after all code fixes:

| Check | Result |
| --- | --- |
| `uv run --no-sync pytest -q` | 1,057 passed, ten skipped in 29.15 seconds |
| `uv run --no-sync pytest -q tests/test_representation_control.py` | 30 passed in 4.69 seconds |
| Reference, existing handler and staged public-boundary checks | 83 passed in 1.78 seconds |
| `make check` | Passed |
| Scoped JSON parsing, local Markdown links and private-identifier scan | 28 public files checked, no violations |
| `git diff --check` | Passed |

The independent review's two runner findings are resolved by the controller's
fixes and regression checks; the corrected G1 counting also passed its review.
The batch is reviewed for a normal fast-forward push to `main`. At this local
checkpoint remote CI/image publication has not yet run; its result must be
checked after push. Git push, image publication and deployment remain separate
outcomes. Deployment is outside this batch.

Controller and reviewer checkpoints are saved under ignored
`.local/task-handoffs/culling-2026-10-02/`. Current algorithm evidence remains
the [four-case synthetic report](benchmarks/2026-09-29-representation-control/report.md)
and [constructed graph report](benchmarks/2026-09-27-reference-tooling/candidate-graph/report.md).
Neither demonstrates accepted real-photo keeper sets or a production improvement.

## Next substantive work

The scoped inventory still has zero qualifying independent human still-photo
pairs/families. Resolve at least 24 labeled pairs / 12 independent families with
the existing split/category quotas, audit their provenance, then freeze real
inputs and add the minimal runner binding. G2 and the controlled development /
untouched-holdout sequence precede any G3/G4 promotion decision. No annotation
UI work, repeated synthetic experiment, model sweep or threshold tuning is
scheduled to substitute for missing evidence. See the
[continuation plan](2026-09-26-culling-improvement-plan.md#next-substantive-step-and-dispatch-boundary).
