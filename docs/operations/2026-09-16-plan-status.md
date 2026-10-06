# Current implementation and acceptance status

Single status entrypoint, updated October 4, 2026. The dated filename is
retained for existing links. Historical reports preserve their original results;
this page, rather than appended handoff logs, defines current work and next steps.

September 28 mainline correction: the user directed work back to culling
algorithm improvement. The [updated plan](2026-09-26-culling-improvement-plan.md)
closes the optional offline annotation-viewer branch. Product WebUI remains the
admin/operator dashboard; browser layout/download acceptance is outside the
active queue and is not an algorithm prerequisite.

September 29 execution complete: the [evidence inventory](benchmarks/2026-09-29-representation-control/inventory.md)
and [controlled synthetic runner](benchmarks/2026-09-29-representation-control/report.md)
are delivered. Four cases / 16 arm cells verify shared geometry, fixed residual
resolution and 512-gray baseline parity; controller checks passed 46 tests and
lint. Resume reused all four records without recomputation. The tiny luminance
control remains cover in both representations; no accuracy or speedup is claimed.

No qualifying independent human labels were found in the scoped existing-manifest
inventory. Next resolve that evidence scope, then bind frozen real inputs and run
G2/Batch 3. Minimum 24 pairs / 12 independent families and all category/split quotas
remain unmet. Do not repeat runner preparation or reopen annotation UI work.
Production behavior and historical acquisition limits remain unchanged.

September 30 recovery: the implementation session hit its usage limit during
final documentation/checkpoint work. Saved runner/protocol hashes still match
the accepted matrix. The controller finalized the report, refined mapping-test
check, public-document hygiene and recovery snapshot; completed preparation
should not be dispatched again.

Completed support work is retained: 138 focused/regression checks on September 27
and 81 reference/viewer/boundary checks on September 28 passed, with lint; see the
[tooling report](benchmarks/2026-09-27-reference-tooling/report.md) and
[handler follow-up](benchmarks/2026-09-27-reference-tooling/2026-09-28-viewer-contract-report.md).
Local checkpoints and hashed snapshots remain the quota-interruption recovery path.

October 2 publication review: the user authorized continuing and pushing the
reviewed batch. The controller corrected G1 counting: abstention-only pairs and
their families cannot pad the minimum labeled-reference totals. The
[publication review](2026-10-02-culling-tooling-review.md) records current checks
and release status. Independent review also led to finite bounded resource-limit
checks and protocol/output collision prevention. Original synthetic evidence is
preserved under its matching code revision. This changes evaluation tooling only;
G1/G2 remain unmet.

October 2 remote acceptance: tooling commit `acb52de` is on `main`; its
[workflow](https://github.com/Team-Cyan/material-agent/actions/runs/36969418207)
passed remote quality (1,024 passed / 43 skipped), image publication, immutable
smoke and verified-tag promotion. No deployment occurred. The user now requests
one review/verification/push per completed continuation step. The directed-coverage
acceptance step awaits independent-reference input paths and label provenance;
do not substitute repeated preparation or auxiliary UI work for those inputs.

October 2 public benchmark search: the user requested labeled standard test sets
with published results. The [primary-source shortlist](2026-10-02-public-benchmark-search.md)
identifies Photo Triage for within-series preference, KonIQ-10k for quality,
AlbumBench for query-conditioned selection and MFND/DISC21 for near-duplicate
diagnostics. Next verify source access/metadata for a native-target diagnostic;
current search did not download image archives or execute evaluation. G1/G2
directed coverage acceptance remains separate from preference/MOS metrics.
The user's public-dataset direction now owns source investigation; a new private
photo or annotation assignment is not the prerequisite for this diagnostic track.

October 2 composite execution: the user separately authorized downloading
multiple public datasets. The new [composite corpus and baseline](benchmarks/2026-10-02-public-composite/README.md)
contain 20,965 actual images (20,584 labeled-task items) plus 5,124 retained
AlbumBench tasks. KonIQ has 300 extra unrated images; AlbumBench has six repeated
rating-target ID records; these source anomalies are preserved and recorded.
KADID covers 81 references, 25 distortion types and five levels. The linked
AlbumBench image host remains inaccessible here, and query-conditioned prediction
is unsupported; it has no fabricated metric.

The frozen baseline evaluates 1,024 KonIQ and 1,024 KADID images, plus all 229
Copydays strong queries against 157 gallery originals. Local heuristic SROCC is
0.3643 / 0.0694; pHash retrieval top-1 is 20.52% with MRR 0.2558. All 2,434 feature
records succeeded; resume reused every record with identical identity/metrics.
These are native-target diagnostics, not deployed learned-model measurements,
leaderboard results or directed coverage acceptance. Full tests passed 1,101 /
10 skipped with Ruff; independent review findings were fixed and re-reviewed.
Archive receipts, image checksums and atomic checkpoints preserve recovery.

October 3 fixed component comparison: the existing pinned NIMA aesthetic asset
was evaluated on the same 2,048 quality images; see the [protocol and results](benchmarks/2026-10-03-public-nima/README.md).
KADID reference families stay disjoint between frozen development/comparison
partitions. These are diagnostic partitions, not blinded holdouts; training-image
overlap remains unknown. All predictions succeeded on CPU without fallback.
Resume reused all 2,048 with identical identity, semantic records and metrics.
NIMA SROCC improved KADID from 0.0694 to 0.3630, but regressed KonIQ from 0.3643
to 0.2806. This raw aesthetic component is not admitted as a universal quality
replacement. Copydays and unsupported AlbumBench results are inherited unchanged.
Full tests passed 1,125 / 10 skipped, with Ruff; model-identity review findings
were fixed and independently re-reviewed. No production policy was changed.

October 3 controller [self-review](benchmarks/2026-10-03-public-nima/self-review.md)
independently verified original native-label joins, all selected byte/cache
identities, exact partitions and all twelve baseline/NIMA correlations. No scoped
implementation defect was found. Commit `6b0b6e9` passed remote quality (1,092 /
43 skipped), publication, immutable smoke and verified promotion; no deployment.

October 3 technical-IQA execution: the [frozen MUSIQ comparison](benchmarks/2026-10-03-public-musiq/README.md)
used the unchanged 2,048 quality images, existing checksum-verified KonIQ-trained
weights and offline CPU batch 1 / four threads. All predictions succeeded; actual
parameter/input/output devices and seed/determinism were verified. Exact-command
resume reused all records with identical identity, provenance, metrics, intervals
and semantic digest. All twelve baseline/MUSIQ correlations and six paired
2,000-draw bootstrap interval sets were independently reproduced within 1e-12.

KADID SROCC rose from 0.0694 to 0.5487; its family-resampled delta interval is
+0.3935 to +0.5610 (comparison partition: 0.0656 to 0.5964, delta interval
+0.4045 to +0.6481). KonIQ SROCC 0.8695 is training-exposed and cannot establish
independent generalization. Source-image training overlap remains unaudited.
Observed run-entry elapsed time was 316.71 seconds including statistical work;
observed peak RSS 988,086,272 bytes stayed below 2.5 GB. Full tests passed 1,167 /
10 skipped, with lint. The current Intel image excludes Torch/PyIQA, so MUSIQ
remains a diagnostic candidate with runtime/product-utility feasibility pending.
The NIMA timing wording now explicitly excludes CLI imports; its scores and local
artifacts remain unchanged. No production policy or photo metadata was changed.

October 3 authorized target execution: the [Unraid public-corpus report](benchmarks/2026-10-03-unraid-public/README.md)
records native DockerMan deployment of reviewed revision `098ccb0`, retained
rollback metadata, SSD storage of 23,414 checksum-verified read-only files and
three isolated runs. The 2,434-item baseline has identical selected IDs/inputs,
zero failures and metrics equal within 2.22e-16. The fixed DINOv3 candidate has
386 successful actual CPU predictions, zero fallback, 0.8341 top-1 / 0.8792 MRR
versus pHash 0.2052 / 0.2558. Exact resume reused all 386; all 229 ranks and
paired 2,000-draw family bootstrap intervals were independently reproduced.
Training overlap and upstream export recipe/revision remain unknown.

The baked default stack ran 256 public images twice with deterministic scores;
NIMA/SSD native CPU execution passed with no fallback, while YuNet execution
readback remains unknown. Observational total time is 31.89 seconds, not a
controlled performance improvement. Production library counts remain 40,620
indexed/scored with zero errors and idle state; no photo/XMP or policy writes.
Application checks passed 1,183 / ten skipped, 50 transport checks and lint passed.
Controller self-review completed saved work after other sessions hit usage limits;
numerical recomputation is independent, completed independent code review is not claimed.

October 4 [MUSIQ Intel feasibility](benchmarks/2026-10-04-musiq-intel/README.md)
is complete: the unchanged checkpoint exports as a whole-image fixed-shape graph
with native preprocessing/eager parity. All 32 public images and 64 Intel CPU
inferences passed the fixed 0.001 error gate (maximum 0.0000534); repeats and
exact-command resume match. Production remains free of Torch/PyIQA dependencies.
Independent runner/wrapper reviews and separate numerical verification passed
after temporary-directory and UTF8 recovery fixes. Full tests passed 1,197 /
ten skipped; 80 wrapper checks and lint passed. Production state is unchanged.

October 4 [full MUSIQ Intel cohort](benchmarks/2026-10-04-musiq-intel-full/README.md)
is also complete: all 2,048 native CPU predictions passed, with maximum raw error
0.0003052, zero fallback and exact full-record resume. Independent SciPy
recomputation verified 24 candidate/heuristic correlation fields and six paired
bootstrap sets. Observed time is 275.15 seconds and peak RSS 509,554,688 bytes,
not a controlled speedup. Full checks passed 1,230 / ten skipped; 133 wrapper
checks, lint and completed independent code review passed. Library/config
snapshots remain unchanged and photo inputs are read-only.

The [actual-input/native-shape diagnostic](benchmarks/2026-10-04-musiq-native-shapes/README.md)
now verifies nine existing public inputs: three exact CPU/F32 shapes pass raw
parity with maximum error 0.00009155, zero repeat error and exact nine-record
resume without inference. Six unsupported inputs produce no graph or score.
Whole preprocessing tokens and eager scores match; independent source/protocol/
package review and numerical verification passed. Checks pass 1308 full tests /
ten skipped, 92 focused and 232 wrapper checks. Five actual RAW preview shapes
remain unsupported; derived portrait does not establish real RAW orientation.

The [shared-token-core resource diagnostic](benchmarks/2026-10-06-musiq-shared-core/README.md)
is complete. The initial conversion failed token-pixel parity. A graph-only
native-float32 basis correction passed all six fresh Intel rounds, 288 raw
scores, 54 structural and nine photo-token checks under unchanged gates.
Median peak RSS fell 31.56%, but the warm latency statistic rose 38.27%, failing
the frozen 10% bound: **shared-core optimization not accepted**. Sources,
packages and initial failure/partial receipts remain intact. Full tests pass
1,338 / ten skipped, 131 wrapper checks and lint pass. Independent numerical
verification and controller recomputation agree; final source deltas were
self-reviewed after reviewer quota exhaustion. Library/config remain unchanged.
The [static lifecycle review and validity fix](2026-10-06-static-lifecycle-quality-validity.md)
is complete: 216,346,624 duplicate constant bytes do not establish actual RSS
savings, weight-buffer retention and per-model packed caches remain constraints,
and no new performance experiment is selected. Invalid PyIQA raw/configuration
and aggregate values now fail as unavailable instead of known quality evidence.
Independent code/client review found no actionable defect; 1,402 full tests / ten
skipped, 155 focused checks and lint pass. Commit `beab0ae` passed exact-revision
CI (1,369 / 43 skipped), immutable smoke and promotion, then authorized native
release verification: idle API, unchanged config/40,620 records and zero DockerMan
audit issues. Retain optional adapter deferral
until a credible bounded resource contract and input acceptance exist. Do not
integrate the rejected shared runtime or repeat the full cohort.
The [persisted-score audit/cache boundary](2026-10-06-persisted-score-audit-cache-validity.md)
rechecked bounded historical outliers. The latest full-library job is August 28,
2026; inspected old payloads lack current quality/selection facts. Full group/rank
distribution comparison remains unverified and requires job-pinned diagnostics.
The conditional pre-guard local-quality processed-cache reuse defect is fixed
with an enabled-quality-only evidence revision: 1,416 full tests / ten skipped,
26 focused cache checks, three boundary checks and lint pass. No global cache
invalidation, production rerun or metadata migration is performed. Next complete
reviewed publication/release, then job-pinned historical comparison support.
Variable-shape/GPU, real portrait RAW/EXIF and product utility remain separate.
Copy correspondence cannot admit semantic grouping or discard policies. Technical-quality product utility and independent directed
coverage references remain separate gates; annotation UI work stays closed.

The inherited composite commit `d746815` passed [remote quality and image publication](https://github.com/Team-Cyan/material-agent/actions/runs/37018657320)
(1,068 passed / 43 skipped), immutable smoke and verified-tag promotion. The NIMA
step's code, aggregate and plan review passed with no remaining must-fix findings.
Its original Git/CI receipts are retained in the local controller handoff. Those
earlier steps did not deploy; the later explicit target authorization above is separate.

## Rules and authorization

Grouping remains adjacent capture-time proximity AND adjacent pHash proximity;
`hash_threshold: 0` selects time only. Chains are allowed. No semantic/action
veto, all-pairs constraint, default hash replacement or severe-exposure exception
has been approved. Quality and selection remain separate; readable groups can
retain a quality-reject for coverage without score inflation.

Local experiments, fixes, verification and reviewed local commits are authorized.
The user now authorizes reviewed step commits, normal pushes and a separate
bounded public-composite acquisition (8 GB compressed / 15 GB expanded). The reviewed
reference, audit and tooling commits through `acb52de` have been pushed, with remote
quality and image publication successful. Git push, publication and deployment
remain distinct. The October 3 user request explicitly authorizes test-set storage
on Unraid, latest native DockerMan deployment and isolated real-environment tests;
those operations are now verified as described above. Production photo/XMP writes
and score/grouping/discard policy changes remain excluded. Synthetic, video,
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
| MUSIQ Intel feasibility and resources | Full/native/shared parity accepted as diagnostics; shared resource optimization rejected | [Full cohort](benchmarks/2026-10-04-musiq-intel-full/README.md), [native shapes](benchmarks/2026-10-04-musiq-native-shapes/README.md), [shared core](benchmarks/2026-10-06-musiq-shared-core/README.md); 288 paired scores, RSS -31.56% / latency +38.27%; 1338 full tests / ten skipped | Static lifecycle review complete, no new resource experiment selected; [finite quality validity](2026-10-06-static-lifecycle-quality-validity.md) fixed and verified by 1402 full tests / ten skipped. Optional adapter deferred; five RAW preview shapes, real portrait/EXIF and product utility unaccepted |
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
| Human-reference tooling continuation | Closed supporting work; preserve existing artifacts | [Tooling guide](benchmarks/2026-09-27-reference-tooling/README.md); validator/merge and handler contracts verified locally | No further annotation UI or browser task; zero real human labels, G1 remains insufficient |
| Controlled algorithm comparison preparation | Accepted locally; synthetic scope | [Report and commands](benchmarks/2026-09-29-representation-control/report.md), [inventory](benchmarks/2026-09-29-representation-control/inventory.md); 4 cases / 16 arm cells, 46 controller checks, verified resume | Zero qualifying human labels found in scoped manifests; G1/G2 and frozen real-data binding still required for quality evaluation |
| Constructed candidate-graph diagnostics | Structural portion accepted locally | [14-snapshot report](benchmarks/2026-09-27-reference-tooling/candidate-graph/report.md); 42 arm/snapshot component/full equalities, zero witness violations; historical global-cap displacement retained | Per-event cap still omits useful pairs; no production promotion, real event segmentation or complete human-oracle G2 acceptance |
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
That historical result does not authorize another source search, threshold
adjustment or production integration. The evidence inventory and synthetic runner
preparation are complete. The current next step is resolving independent
reference inputs; missing judgments still block labeled quality evaluation. Existing
reference tools may be reused, with no further annotation-page work.

A review found that the original guarded test environment masked a bare sibling
test import. The import now uses the existing `tests` package. Direct spatial
tests pass 15/15 without added `PYTHONPATH`; repository-boundary tests pass 2/2,
with Ruff and diff checks passing. This test-only fix does not change the frozen
reference results or authorize more collection.
