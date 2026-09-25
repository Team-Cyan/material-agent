# Current implementation and acceptance status

Single status entrypoint, updated September 25, 2026. The dated filename is
retained for existing links. Historical reports preserve their original results;
this page, rather than appended handoff logs, defines current work and next steps.

## Rules and authorization

Grouping remains adjacent capture-time proximity AND adjacent pHash proximity;
`hash_threshold: 0` selects time only. Chains are allowed. No semantic/action
veto, all-pairs constraint, default hash replacement or severe-exposure exception
has been approved. Quality and selection remain separate; readable groups can
retain a quality-reject for coverage without score inflation.

Local experiments, fixes, verification and reviewed local commits are authorized.
The user now authorizes reviewed batch commits and normal pushes. The reviewed
reference and audit commits through `a2db712` have been pushed, with remote
quality and image publication successful. Git push, publication and deployment
remain distinct; no deployment occurred. Deployment, private-host operations,
production review and actual photo/XMP writes remain excluded. Synthetic, video,
real RAW, model proxy and human evidence must be distinguished. Historical external operations do not expand this scope.

## Task ledger

Status vocabulary: **Pending**, **In progress**, **Implemented**, **Accepted
locally**, **Blocked**. Local acceptance never implies target-machine deployment
or photographic product acceptance. The baseline and one attribution-driven hypothesis both failed admission. The bounded spatial reference collection is complete but its feasibility gate failed; no third algorithm is running.

| Item | Status | Commit / evidence / checks | Next action or blocker |
| --- | --- | --- | --- |
| Phase 1 Gate 0/1/2/3 | Accepted locally, bounded scope | [Actual-path gates](2026-09-15-inference-unification-gates-0-1.md), [readiness](2026-09-15-inference-unification-readiness.md); shared native lifecycle, CPU parity, compatibility and candidate matrix | No repeat migration. Target provider/hardware acceptance is separate |
| Adjacent time/hash and missing-thumbnail RAWs | Implemented; business acceptance incomplete | `accad08`; four RAW regressions; last guarded full suite 753 passed/102 skipped | Preserve rule. Full sequences expose action-coverage loss; see decision below |
| Group coverage / quality-selection persistence | Implemented | [Implementation audit history](2026-09-17-follow-up-validation.md); `2c6ec47` includes reviewed refinement/rewrite guards | Per-group keep works, but is not per-action coverage; no score inflation |
| XMP policy / projection-attempt ledger | Implemented locally | `2c6ec47` and linked audit; missing/zero rating rules, protected nonzero values, malformed/duplicate failures, rewrite preflight, append-only outcomes | External watching/crash reconciliation and professional software readback remain unverified |
| Evidence applicability / opt-in refinement | Implemented; not promoted | Observed/unknown contracts and conservative no-gain guard; 100-frame run had 18 completed/22 no-gain/60 untriggered observations | No demonstrated ranking gain; keep disabled. No automatic back-view/silhouette producer or accepted context dataset |
| TOPIQ / MUSIQ / MediaPipe experiments | Accepted locally as diagnostics only | `74998da`; [100-frame comparison](benchmarks/2026-09-17-hdrplus-holdout/report.md), [completed proxy results](benchmarks/2026-09-18-hdrplus-completed/report.md) | Freeze negative promotion conclusion; do not rerun/fuse by default |
| Independent HDR+ A/B proxy evaluation | Execution complete; acceptance gate failed | `4b76ce8`; both panels 20/20; prior responses unchanged; 1/20 preferred-set agreement, 7 stable strict pairs vs minimum 30 | Quota blocker resolved. References remain unstable; no human-accuracy or product-acceptance claim |
| Exposure and action hard negatives | Accepted locally as diagnostic evidence | `5caaacb`, `2811b9d`, `a90e3ef`; [real RAW](benchmarks/2026-09-17-exposure-brackets/report.md), [synthetic](benchmarks/2026-09-17-hash-hardcases/report.md), [video pairs](benchmarks/2026-09-18-cooking-hashes/report.md) | Current candidates fail some known controls. Do not tune these inspected inputs further |
| Whole-sequence closure / reproducible runner | Accepted locally | `4b76ce8`; [sequence report](benchmarks/2026-09-18-cooking-sequences/report.md); 29 focused tests, 2 boundary tests, Ruff, source hashes, 25-pair exact parity and runner/plan fingerprints | No algorithm promoted; decision boundary below |
| Direct coverage relation / conservative selector | Execution complete; admission failed | `7661372`; [40-case report](benchmarks/2026-09-18-direct-coverage/report.md), 32 focused guarded tests; 0 structural violations, 2 false cover edges, 1 selected unique-content loss; 94% abstention | Baseline rejected for promotion. Preserve frozen results; no automatic model rotation |
| Local residual observability hypothesis | Execution complete; holdout gate failed | `efcdbdd`; [attribution and fresh-burst report](benchmarks/2026-09-19-coverage-observability/report.md), 31 focused guarded tests; development false cover 4→0/8, positive cover 12→18/20; two fresh bursts both retain 3/3 | No retention improvement; no promotion or threshold tuning. Further hypotheses need independent local meaningful/nuisance-change references |
| Important-change / nuisance spatial references | Evidence complete; feasibility gate failed | `775b3f3`; [reference report](benchmarks/2026-09-19-spatial-reference/report.md); both panels 12/12, 9 scenes, one agreed important pair / zero nuisance pairs; 12 guarded checks | No third algorithm. U01 same-action preference awaiting user; spatial category gaps remain even after that answer |
| Final bounded spatial-reference supplement | Complete; reference gate still failed | [Final supplement](benchmarks/2026-09-19-spatial-supplement/report.md); four new fixed CDnet pairs, joint 16 pairs / 13 scenes; 2 important pairs, 1 nuisance pair; 15 direct spatial tests + 2 boundary tests after test-import portability correction | `reference_insufficient`, not `preference_blocked`; illumination and gesture categories missing. Search closed at conservative 29m12s cumulative, 3,797,249 dataset bytes downloaded; no further algorithm or collection in this batch |
| Complexity, efficiency and stability audit | Bounded audit complete; release-gate fixes verified locally | [Runtime audit](benchmarks/2026-09-19-runtime-audit/report.md), pre-unification `9de0e41` vs `09c5882`; runtime text +4.7%, dependencies unchanged, small learned-model warm latency +6.3% (corrected fresh-cache protocol); 797 guarded tests passed / 102 skipped | CI ownership and XMP error-contract fixes pass 53 focused guarded tests; `0e84b81` remote quality and image publication succeeded. Do not generalize small PNG results to RAW or target hardware |
| Bounded package-version lookup optimization | Implemented and published; single attempt gate passed | [Version snapshot follow-up](benchmarks/2026-09-20-runtime-version-cache/report.md); lazy client-lifetime snapshot, 4 paired trials, learned warm 779.595→762.427 ms (2.20%), 3/4 faster; heuristic 1.80% slower; exact score and identity parity; 803 guarded tests passed / 102 skipped; [quality, image smoke and publication succeeded after one CI retry](https://github.com/Team-Cyan/material-agent/actions/runs/35515765580) | No further optimization/RAW/hardware experiments in this batch. Changing installed packages requires a new client; target hardware acceptance remains separate |
| Personal ranker / automatic context acceptance | Blocked on reference data | Action labels and order-sensitive model proxies cannot establish personal preference or reliable back-view/silhouette applicability | Obtain suitable independent labels before model integration/training |
| Professional-software and target recovery acceptance | Blocked on external inputs/authorization | [Concrete execution plan](2026-09-17-external-acceptance-plan.md) | Identify scratch write scope/software and separately authorized target operator/appdata scope; do not execute now |

## Converged grouping result and required decisions

The real exposure pair is 0.34 seconds apart with pHash distance 24; threshold 10
splits it and singleton coverage retains the dark quality-reject. Equalization
reduces that pair to distance 4, but introduces a move-to-peel false merge in a
real video. Synthetic controls also show different-content false merges.

On the full 121-frame sampled video window, current pHash creates seven groups
and retains only 2/12 represented action classes; equalization retains 3/12,
dHash 1/12. Labels are metrics only. This demonstrates the difference between
correct implementation of adjacent links and the business wish to retain all
different actions. The wide, dark video's low quality scores and group-level
selection contribute to the losses; it is not camera-burst quality ground truth.

Existing candidates are **not promoted**. The subsequent authorized offline
experiment completed evaluation of direct content coverage separately from quality
and final selection. It does not change the adjacent grouping definition. The earlier
product-decision questions do not block this bounded experiment.

The frozen protocol requires independent false-coverage and unique-content-loss
measurements, conservative unknown retention, explicit candidate/resource caps,
full recomputation under mutations, and fresh still-photo events. There is no
permission to tune repeatedly on these inspected holdouts or promote a new rule.
The baseline failed its predeclared gates, including a small-content false cover
and all-retained fresh RAW events. Its bounded batch is complete; this is not a
product-decision blocker. Any production adoption remains a separate design and
acceptance decision.

## Verification limits

An earlier full guarded suite had **753 passed, 102 skipped**, run before the
earlier push through `a1ecf76`. A later explicit push through `7f2a367` completed
with 45 focused guarded tests and Ruff; the final reference-supplement batch
was subsequently pushed through `09c5882` under the new batch authorization.
`4b76ce8` changes isolated benchmark code/tests and evidence, with **29 focused
checks**, **2 repository-boundary checks**, Ruff and exact real-data parity.
Source photo/video bytes were verified unchanged. No actual XMP write, live
service operation or deployment occurred in these continuation batches. Push
status is recorded separately above.

The direct-coverage continuation adds **32 focused guarded checks** and a
40-case immutable-input experiment. Exact prior production-path parity holds for
25 video pairs and both full sequences (184 frames). No full-suite rerun is
claimed for these isolated scripts; source/application code is unchanged.

The September 19 attribution batch adds eleven independent A/B **model-generated**
video coverage references (no human labels). A frozen RGB/local-residual hypothesis
passed new development controls but failed untouched, correlated stream-burst
retention criteria. This completes one bounded follow-up; it does not authorize
production integration or automatic further model rotation.

The original spatial-reference quota recovery succeeded for both panels. That
twelve-pair package had only one agreed important spatial pair and no nuisance
pair under the frozen rubric; the supplement below supersedes its gap counts. The minimal U01 user example
is separate from the twelve blind pairs and does not alter prior different-action
requirements. No third candidate is started.

The final bounded public-reference supplement is now closed. Its four new pairs
add one agreed object-change pair and one water-nuisance pair (the same pair).
Combined evidence still lacks a second nuisance pair and agreed illumination and
gesture/expression contrasts. `reference_insufficient=true` and
`preference_blocked=false`; U01 is still pending but is not the data blocker.
The sole next proposal is a separately scoped human-annotated reference collection
covering those gaps. No new algorithm, source search, threshold adjustment or
production integration is authorized by this result.

A review found that the original guarded test environment masked a bare sibling
test import. The import now uses the existing `tests` package. Direct spatial
tests pass 15/15 without added `PYTHONPATH`; repository-boundary tests pass 2/2,
with Ruff and diff checks passing. This test-only fix does not change the frozen
reference results or authorize more collection.
