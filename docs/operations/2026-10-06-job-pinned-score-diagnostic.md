# Job-pinned historical score diagnostics

This step implements the next bounded diagnostic after the
[persisted-score provenance audit](2026-10-06-persisted-score-audit-cache-validity.md).
The library API chooses each file's latest result; it cannot freeze two historical
cohorts or establish complete group membership from samples. The application-owned
`review-scores` command now has explicit job selection and comparison, with a
no-preview path. The admin WebUI and scoring/grouping policy are unchanged.

## Scope and contracts

The maintained CLI contract is in [Web operations](../ai/modules/web-operations.md).
Default v2 reconstructed-preview behavior is retained. An explicit job produces
v3 persisted facts; comparison requires two different IDs and `--no-previews`.
Jobs must be terminal `review_photos` records with retained sessions; missing,
wrong-type or nonterminal IDs fail rather than silently selecting a newer job.

One read-only transaction binds the jobs, full session configuration snapshots,
all file rows and score artifacts. Every member contributes to its group even
when unscored or in error. Numeric distributions use finite values only; missing
values do not become zero. Duplicate paths and artifacts remain explicit rather
than multiplying cohort members or producing an arbitrary pair. Quality and
selection v1 facts are retained separately from legacy decisions; missing,
malformed, ambiguous and unsupported-version evidence stays unresolved.

Reports expose complete group/rank counts, exact path intersections and
differences, finite paired values, and root/configuration/coverage differences.
Historical application revision is unknown if not recorded. An observed delta
is a difference in persisted values, not evidence of current-policy improvement.

The no-preview mode requires neither existing photographs nor decoding. It does
not start a model, rerun scoring, rescore, migrate metadata or reapply a selection
policy. Report directories/files are private and isolated from current/historical
photo trees and the runtime database. Raw cohort paths and operator receipts are
kept in ignored storage.

## Verification boundary

Regression fixtures bind selected jobs despite a newer unselected job, retain
partial/error and invalid-score rows, and distinguish missing/legacy facts from
accepted current facts. They cover complete groups, duplicate/out-of-range ranks,
ambiguous stored JSON and artifacts, different roots/configurations/paths, and
strict finite JSON. The decoder can be forced to fail while the no-preview audit
still succeeds; database and photograph bytes remain unchanged. Existing v2
preview checks remain required.

Full local checks pass 1,448 tests / ten skipped, 124 focused diagnostic/CLI
checks, three repository-boundary checks and lint. Independent source/contract
review found no actionable issue after the numeric, duplicate-key and actual
metadata routing regressions were fixed. The transport has 63 focused passing
checks; native execution is verified separately from fixture behavior.

The native target workflow pins an exact reviewed image and two approved
historical jobs, checks DockerMan management/idle state/source mounts, and guards
fixed database and configuration identities before and after the application
command. Only private diagnostic output is created. Volatile SQLite shared-memory
reader state is not presented as durable database mutation. Export is bounded,
identity checked and recoverable; it is not a photo or secret export workflow.

A target result belongs to its two historical jobs and image/source receipt. It
cannot substitute for current-policy photographic acceptance, independent human
directed-coverage references, actual RAW/MUSIQ input acceptance or resource
admission. Those gates remain unchanged.
