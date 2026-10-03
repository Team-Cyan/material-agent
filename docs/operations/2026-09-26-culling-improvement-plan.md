# Culling improvement plan after the September 26 review

Status: mainline evidence inventory and synthetic runner preparation verified
on September 29, 2026; controller finalization completed September 30 after an
execution-session quota interruption. October 2 continues with evaluation-gate
hardening and reviewed publication under the user's new push authorization;
see the [publication review](2026-10-02-culling-tooling-review.md). The product WebUI remains
an admin/operator dashboard under the [Web contract](../ai/modules/web-operations.md).
The offline viewer is an optional internal research artifact; its implementation
is closed for this continuation. Do not extend it, integrate it into WebUI or
schedule browser/download acceptance as a prerequisite for algorithm work.
Preserve existing files and reports without further polishing this branch.

The supplied review, `deep-research-report (2).md`, is supporting analysis,
not independent execution authorization. The user authorized coordinated work
in separate tasks, with this controller owning review and plan updates. This
revision changes the work priority, not the evidence required for algorithm
admission. The frozen experiment baseline remains commit
`175e87e6ea927e40e735717c1a1d3eeb3a1c6753`; no real-photo quality gain is claimed.

## Execution tracking

| Work | Status | Next action or acceptance boundary |
| --- | --- | --- |
| Existing evidence inventory and experiment protocol | Completed locally | [Inventory](benchmarks/2026-09-29-representation-control/inventory.md), [protocol and checks](benchmarks/2026-09-29-representation-control/report.md); 4 synthetic cases / 16 arm cells, no real-photo quality result |
| Reference tooling and offline viewer | Closed supporting work | Preserve [tooling results](benchmarks/2026-09-27-reference-tooling/report.md) and [handler checks](benchmarks/2026-09-27-reference-tooling/2026-09-28-viewer-contract-report.md); no further UI task |
| Constructed candidate/selection graphs | Structural portion accepted locally | [14-snapshot report](benchmarks/2026-09-27-reference-tooling/candidate-graph/report.md); reuse the evaluator, do not repeat completed graph experiments |
| G1 independent reference evidence | Insufficient; audited existing manifests | Zero qualifying human pairs/families found in the scoped inventory; minimum 24 pairs / 12 families and all split/category quotas remain unmet |
| G2 human-labeled oracle diagnostic | Pending G1 | Measure candidate omissions and selector limitations on actually labeled pairs |
| Batch 3 representation comparison | Synthetic runner prepared; real labeled evaluation pending G1/G2 | Fixed 512/1024 geometry x gray/RGB-local matrix with residual512; bind a frozen real-data manifest only after evidence readiness; no threshold/model sweep |
| Batches 4–6 | Conditional | Escalation, integration and target acceptance retain their gates |

### September 29 controller acceptance

The [new report](benchmarks/2026-09-29-representation-control/report.md) records
four fixed synthetic pairs, two geometry resolutions and two residual arms.
Controller checks passed **46 tests in 5.57s** (15 new, historical relation and
observability checks, and repository boundaries); `make check` passed. At each
resolution both arms share one captured geometry artifact. All four 512-gray
numerical residual evidence records exactly match the historical baseline;
1024/residual512 explicitly has no full historical parity claim.

At both resolutions identity and JPEG cases return cover in both arms. The
synthetic isoluminant-color case returns gray cover / RGB unknown, while the tiny
luminance-change case still returns cover in both arms. These are wiring/control
observations, not evidence of improved photographic safety or preference accuracy.
Timing includes historical gray screening plus both residual arms, so it cannot
establish a geometry-stage or representation speedup.

The controller also verified resume without recomputation (four records reused).
Interruption tests recompute only missing cases; full-record integrity and stable
decision-evidence digests are separate because timing/RSS can change. Case/input,
protocol, implementation and runtime identities guard reuse; an observed resource
overrun is saved before stopping further cases. Limits are observed, not hard OS
caps. Historical scripts/reports and the closed viewer template remain unchanged.

The inventory checked existing manifests and referenced file availability, not a
new acquisition or photo evaluation. Existing RAW/video/JPEG sources can support
regression work, but no qualifying independent human coverage labels were found
in that scope. The CLI deliberately accepts only the frozen synthetic cases;
real-data binding and blind quality evaluation are separate pending work.

September 30 recovery confirmed the saved runner/protocol hashes, refined
unequal-thumbnail mapping test and final public-artifact checks. The implementation
session stopped on an account usage limit after writing substantive artifacts;
the controller completed its report/checkpoint handoff. Resume from the finalized
snapshot instead of repeating this preparation or reopening UI work.

### Completed evidence and boundaries

Controller checks passed 138 focused/regression tests on September 27 and 81
viewer/reference/boundary tests on September 28, including 31 new handler cases.
Lint passed. Detailed tooling evidence belongs in the linked reports; these
counts are software checks, not evidence of improved photo selection. Real
browser layout/download remains unverified and is outside the active work queue.

Constructed per-event budgeting fixes one unrelated-event displacement case but
matches uncapped decisions in only 10/14 snapshots versus 11/14 for the historical
arm. This does not justify promoting it. No new real-human reference labels were
obtained. Human provenance and judgment quality still require independent audit;
`quota_ready_pending_human_audit` is never an automatic G1 pass.

The controller owns design, integration, review and this plan/status ledger.
Existing execution tasks may be reused with a fresh bounded algorithm scope and
updated checkpoints; their former viewer scope must not silently resume. No new
session was needed for that plan edit. The October 2 request authorizes reviewed
batch commits and a normal push; it does not authorize deployment, new data
acquisition or photo/XMP writes. Source/runtime/default behavior remains unchanged.
The next deliverable uses existing authorized local evidence and
experiment code; historical acquisition budgets remain closed.

### October 2 publication review

The user authorized continuing and pushing the reviewed tooling batch. G1
counting now excludes abstention-only pairs/families from the overall minimum;
one definite direction qualifies its pair once. Independent review additionally
identified nonfinite/unbounded resource limits and protocol/output path
collisions. The runner now rejects both before generating inputs or writing
output. Original synthetic code/evidence is preserved in commit `61d3b3f`;
the hardened runner intentionally rejects records with that older code digest.

Final controller checks passed **1,057 tests, ten skipped**, with lint and public
artifact hygiene passing. See the [publication review](2026-10-02-culling-tooling-review.md).
This completes the local review/fix batch, not G1/G2 or photographic acceptance.
No new experiment or production integration is needed to publish these tools.

The pushed tooling commit `acb52de` also passed remote quality, image smoke and
publication; see the linked review for exact CI counts. The continuation now
uses one reviewed, verified push per completed step. The next step is resolving
actual independent-reference paths and label provenance, not repeating the
completed synthetic protocol. Available input details have been requested; no
person is assigned annotation work and historical acquisition limits stay closed.

### Interruption and quota recovery for this continuation

The user requested durable progress when account limits interrupt a task. Keep
controller and per-task checkpoints under ignored
`.local/task-handoffs/culling-2026-09-27/`; private task identifiers stay there.
Each dispatch must assign a checkpoint path and require an initial checkpoint,
then atomic updates after meaningful edits/checks and before a handoff. Record
owned files, completed and remaining work, actual verification commands/results,
artifact paths, limitations and the next safe recovery step. Write substantive
results as work proceeds, rather than relying on a final chat response.

Before dispatching another batch, inspect available account allowance when the
app exposes it, and prefer a small finishable scope or continuation of an existing
task. If allowance is tight, prioritize checkpoint/report completion over new
parallel implementation. A task's first action is to record its scope and recovery
state; subsequent updates make an abrupt interruption recoverable.

The controller keeps bounded local snapshots of this batch's code/docs/tests
with hashes and an explicit verification state. These snapshots are recovery
copies, not commits or verified release artifacts. On resumption, inspect task
status, checkpoints and current worktree first; reuse the existing tasks and
compare file hashes before accepting old checks or restoring anything. Do not
overwrite newer work or rerun a still-active process. Account-limit exhaustion
must leave recoverable artifacts, not trigger new-task creation to evade limits.

## Decision and verified baseline

Continue toward directed content coverage with conservative keeper selection.
Separate representation, candidate generation and selection failures. Audit
existing evidence and prepare the controlled experiment while independent
reference requirements are resolved. Preserve current production behavior while
this evidence is collected. Do not repeat completed inference migration or
rotate through models without a specific failure hypothesis.

| Checked evidence | Consequence for this plan |
| --- | --- |
| [Grouping contract](../ai/modules/grouping.md) and `Grouper._group_with_times` still use adjacent time AND pHash; zero bypasses hash | Old mode remains the compatibility baseline, including chaining |
| [Direct coverage report](benchmarks/2026-09-18-direct-coverage/report.md): 1,164 directed relations, 93.99% unknown, two false-cover edges and one synthetic unique-content loss | Retain the selector contract; current relation predicate is rejected for promotion |
| [Observability report](benchmarks/2026-09-19-coverage-observability/report.md): development improves, both fresh RAW bursts retain 3/3 | No demonstrated holdout retention gain; these inspected bursts are now regression inputs |
| `benchmark_coverage_observability.evaluate_relation` changes `Protocol(max_side=...)` before `prepare` | Previous 512-to-1024 comparison confounds geometry resolution and change representation |
| [Spatial supplement](benchmarks/2026-09-19-spatial-supplement/report.md): 16 pairs / 13 scenes, two important pairs, one nuisance pair, no human labels | `reference_insufficient` remains the primary blocker; missing illumination and gesture evidence cannot be fixed by answering U01 |
| `direct_coverage.candidates` has nearest-forward and global pair caps; `select` orders by quality | Candidate locality and incremental selection require their own tests |

The baseline numbers above are historical experiment results checked in the
current checkout, not experiments rerun for this plan. Synthetic controls, video
action labels, model panels and human still-photo labels must remain separate.

## Proposed future-mode contract

- A rejected photo must have a direct, current `cover` edge from a final keeper
  that passes the independent quality comparator. No transitive witness.
- Relation does not consult quality. Quality alone cannot reject unique readable
  content; selection does not alter scores, defect reasons or user ratings.
- Missing time/features, timeout, decode failure, ambiguous content and revision
  mismatch never supply a reject witness. Without another valid direct witness,
  retain the photo or report it as unscored/review-required. One unknown pair
  does not invalidate a separate trustworthy witness from another keeper.
- Preserve different dishes, actions and clear subject-state changes. Treat
  unresolved same-action fine progression as unknown; do not invent a preference.
- Source photos remain immutable. This is keep/reject recommendation, not file
  deletion. Existing nonzero XMP ratings remain protected.
- New mode sorts by real capture time plus stable photo ID. Preserve old-mode
  ordering exactly: current equal-time ties inherit input order, so adopting the
  new tie-breaker globally would itself be a behavior change.

## Delivery order and gates

Each batch ends with a compact report and a pass/fail decision. Failure freezes
that result; it does not automatically start another candidate. Execution status
is recorded above; the attached review alone authorizes none of these actions.

### Batch 1 — reference package and evaluator contract

**Purpose:** obtain trustworthy evaluation references with the existing tools.
The manifest, rubric, validator and optional offline viewer are already implemented;
no additional annotation UI is planned. Existing independently human-labeled data
may be reused only if provenance, category coverage, independence and leakage
checks satisfy the same contract. Missing judgments remain missing; neither the
user nor another person is presumed to have accepted an annotation assignment.
Default reference target:
32 pairs from at least 16 independent still-photo events; bounded range 24–40
pairs from 12–20 events if category quotas remain satisfied.

Target eight primary categories: exposure-only; illumination/shadow; moving
texture/noise; object/dish state; same-action hand progression; expression/eyes/
head pose; camera motion/composition; occlusion/back-view/silhouette/clipping.
Aim for four pairs from two events per category. A category target is an
acquisition goal, never a label assigned before inspection.

Keep source bytes and private manifests outside Git. Record content digests,
preview recipe/dimensions, real capture-time provenance, source permissions,
event/scene family, split and annotation revision. Related bursts, scenes,
videos and derived variants must share a split. Freeze development/holdout
membership before algorithm evaluation; keep holdout judgments hidden from
candidate development. Existing inspected examples are regression only.

Collect separate human judgments for visible correspondence, localized
important/nuisance regions, directed content coverage A→B and B→A, and quality
preference/tie. Region coordinates must map to a documented image coordinate
system. Permit unknown, unjudgeable and preference-dependent. Hide scores,
algorithm outputs and source category targets during annotation; preserve raw
disagreement and human adjudication. Model agreement never creates a human label.

**G1:** both splits contain visible illumination nuisance and hand/expression
change; overall at least two independent events for each, two nuisance types,
and in each split at least six human-coverable and six human-negative directed
relations, each class spanning at least three events. Count both directions but
do not treat them as independent samples. Unjudgeable/ambiguous items do not
satisfy positive/negative quotas. If quotas fail within the cap, report the exact
missing input and stop collection rather than quietly expanding it.

This small set enables hypothesis screening, not a population-level safety claim.
Independent human judgments and a suitable source collection are required inputs.
The schema, rubric, validator and synthetic evaluator checks are already available.
Further preparation should target the controlled algorithm runner and evidence
inventory, not another annotation interface.

### Batch 2 — isolate candidate and selector limitations

**Purpose:** determine whether better visual evidence can actually improve the
current candidate/selection path.

First use small constructed directed graphs, without image inference. Compare
nearest-three/global-cap enumeration with all eligible pairs on bounded graphs
and a deterministic per-event budget. Test chains, cycles, tied scores, missing
quality, low-quality unique A plus high-quality duplicate B/C, keeper deletion,
component bridging and insertion into a disconnected event. Count omitted pairs
and reasons; an unevaluated pair is unknown, never negative or cover.

After G1, repeat the oracle diagnostic only where human labels actually cover
the relevant pairs. Missing labels remain unknown; do not fabricate a complete
oracle graph from action labels. Measure reachable human-covered redundancy
before and after caps. This distinguishes candidate omission from predicate
abstention and greedy over-retention.

**G2:** zero witness violations; permutation-stable new-mode output; inserting
an unrelated event does not displace another event's candidates. Use bounded
full component recomputation as the correctness oracle. Selection may cascade
through a connected component; do not promise a fixed-radius local update.
Measure component growth and bound it before implementing incremental updates.
Constructed event IDs are fixture inputs, not evidence of automatic event
segmentation; passing per-event budget tests does not establish that capability.

Scope: isolated scripts and tests. Constructed-graph checks can proceed while
human annotation is pending. No production candidate generator is replaced here.

### Batch 3 — clean representation experiment

**Entry for the quality experiment:** G1 and G2; fixed candidate list, quality
results, selector, previews, labels and runtime protocol. Preserve the rejected
historical baseline unchanged. Runner/protocol preparation and synthetic parity
checks can precede G1; they must not tune the predicate, inspect reserved holdout
labels or be reported as an algorithm-quality experiment.

Run the following development matrix, reusing identical geometry artifacts
between representation arms at each resolution:

| Geometry input | Change representation | Question |
| --- | --- | --- |
| 512 SIFT | gray residual | Frozen baseline |
| 512 SIFT | RGB/local residual | Representation effect at fixed geometry |
| 1024 SIFT | gray residual | Resolution effect |
| 1024 SIFT | RGB/local residual | Interaction |

Record the residual input resolution separately from geometry resolution and
hold it fixed within each representation comparison. Do not silently mix a
larger preview, a different registration and a new residual threshold.

Choose one candidate using development only, then freeze code/config, metrics,
thresholds and artifact digests before opening holdout results. A failed
holdout cannot be reused to tune the next candidate.

**Proposed G3**, to be frozen before execution:

- Zero cover edges on definite human-negative holdout relations, even if the
  current quality ordering would not yet use them; zero selected false rejects
  and zero witness violations. Any such error stops promotion.
- At least a 10 percentage-point true-cover recall gain over the frozen baseline
  on the same holdout, with actual successful covers in at least three independent
  events. All-keep fails. Report numerators, denominators and uncertainty by event;
  never compare new-set performance directly to the historical 93.99% abstention.
- Report unknown, geometry failure, important-change miss, nuisance false alarm,
  omitted pairs, and decode/feature/matching/residual/selection costs separately.
- Initial local budget: 90 seconds/case and 2,000,000,000 bytes peak RSS, matching
  the old diagnostic units. Reject advancement above 2× a same-input, same-runner
  baseline wall time. Distinguish base execution from mutation reruns. Boundary
  timing checks and sampled RSS are observations, not hard OS enforcement.

These numerical gates are proposed engineering screening criteria, not measured
success or a statistical guarantee. A denominator too small for the frozen gate
is insufficient evidence, not a pass.

### Batch 4 — conditional algorithm escalation and sequence validation

If G3 fails, use development attribution to propose one new bounded experiment:
ECC when registration error is demonstrated; XFeat when correspondence fails;
patch representations when alignment succeeds but local meaning remains unresolved.
Each needs a new frozen hypothesis and an untouched holdout before promotion.
Do not execute all branches as a model tournament.

The [XFeat official implementation](https://github.com/verlab/accelerated_features)
describes CPU inference using PyTorch and still requests ONNX export contributions.
Therefore export, dependency cost, weight identity and Intel parity are unresolved
project work, not assumed deployment readiness. The [DINOv2 model card](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md)
documents patch outputs, but does not establish their culling accuracy.
[OpenCV ECC](https://docs.opencv.org/4.13.0/dc/d6b/group__video__track.html)
is an alignment tool; registration success is not a coverage label. These primary
sources were checked on September 26. LightGlue/EfficientLoFTR remain later
options only if attribution justifies their additional scope.

After a relation passes G3, validate 30–50 independent still-photo events,
approximately 200–400 photos, split by event/scene family. Compare current
production behavior with the fixed relation plus direct-witness greedy. Only if
oracle diagnostics show material selection loss add complete-link constraints
or a sparse constrained coverage optimizer, one at a time. Every optimizer must
retain the same direct-witness requirement.

**G4:** zero observed human-confirmed unique-content losses/false rejects; every
reject adjudicated or the gate remains incomplete; zero structural violations;
at least 50% reduction of human-established redundant photos across at least ten
redundant events. Define redundancy against human acceptable keeper sets, allowing
multiple equally valid sets. Report per-event distribution, over-retention,
unknown-driven retention and candidate/component sizes. Action-label coverage is
diagnostic only. Repeat permutation and mutation checks against full recomputation.

### Batch 5 — opt-in production design and cache integration

**Entry:** G3/G4 plus a separately chosen production behavior change. First deliver
a design review against grouping, scoring, state, config and runtime contracts;
do not import experiment scripts into application code.

Use domain-owned relation/selection rules, adapter-owned feature/cache storage,
and application-owned orchestration through `review_runtime.py`. Preserve old
mode as default and exact-compatible fallback. Persist `covered_by`, evidence
identity, reasons and selector revision alongside existing quality/selection
metadata; reject stale witnesses after rescore/restart. Provide report-only output
before metadata projection. Avoid new default dependencies unless measured gains
justify them and CPU fallback is verified.

Separate cache dependencies:

| Layer | Required identity |
| --- | --- |
| Features | Content digest, preview recipe, extractor/weights/config, preprocessing/output revision and relevant runtime dependencies |
| Pair relation | Ordered feature identities, direction, registration/change/policy revision |
| Candidate set | Photo membership and stable IDs, capture-time snapshot, window and budget policy |
| Selection | Actual candidate/edge result digests, quality result/config digest, selector revision |

A policy version alone cannot identify graph contents. Do not persist transient
failures as successful cover. Bound cache size and test eviction/restart. Keep
photo identity distinct from content identity so byte-identical copies remain
distinct selectable items. Feature changes invalidate relations and selection;
quality changes invalidate selection; selector-only changes retain features and
relations. Insert/delete/keeper removal recomputes all affected components and
reverse witness dependencies, including component splits/merges.

**G5:** old-mode decision/metadata parity; new-mode mutation equivalence to full
recomputation; no stale witness after restart or revision changes; writer/rating
protections intact. Run focused owning-module tests, `make check`, `make test`
and applicable integration checks for the cross-module change. This is local
software acceptance, not a deployment or photo-quality result.

### Batch 6 — target performance and external acceptance

Use at least 100 independent real events and 1,000–3,000 photos, including at
least 30 RAW-heavy bursts. Prefer disjoint held-out events for quality acceptance;
report unlabeled bulk throughput separately. Use actual capture metadata, record
provider/fallback, image digest and source hashes, and separate cold compilation,
warm inference and result-cache hits. Never describe cached results as inference
throughput. `run --dry-run` still writes job state; use isolated appdata and
read-only media under the authorized operator workflow.

**G6:** zero known unique loss, CPU fallback and bounded failure behavior verified,
peak RSS below the separately frozen target budget (initial proposal 2 GiB), and
old-mode parity. Measure the target old-mode baseline first and freeze an
acceptable end-to-end slowdown before candidate evaluation; do not choose the
multiplier after seeing the candidate. Performance approval does not replace G4.

Professional-software XMP round trips and Docker/SQLite recovery remain a separate
acceptance track using the [existing protocol](2026-09-17-external-acceptance-plan.md).
They can be scheduled independently when scratch/application/operator scope is
available. Avoid repeating already completed XMP unit work or runtime migration.
Publication, deployment and real photo writes remain distinct outcomes.

## Mainline preparation delivered on September 29

The scoped inventory and runnable synthetic comparison protocol are delivered.
The following sequence remains the contract for completing labeled evaluation.
Reuse this preparation before another model is introduced. The controlled wiring
now separates the known resolution/representation confound. Further changes should
be limited to binding suitable real inputs when available; do not build another
labeling application or general benchmark framework.

1. **Existing-evidence audit — completed in scoped manifests.** Inventory only relevant, already authorized local
   manifests/artifacts and their accessible source files. Record source origin,
   event/family, inspected status, permissions, preview identity and label origin.
   Separate synthetic controls, video/action labels, model judgments and genuine
   human judgments. Previously inspected cases remain regression inputs, not fresh
   holdout. Report the exact missing categories and counts for G1; if no reusable
   human labels exist, say so without fabricating them or reopening acquisition.
2. **Controlled runner — synthetic preparation complete.** Preserve historical scripts/results. Freeze
   candidate pairs, quality inputs, selector and preprocessing. Reuse identical
   geometry artifacts between gray and RGB/local arms at each 512/1024 resolution;
   record residual resolution separately. Verify baseline parity and arm isolation
   on synthetic controls. Freeze metrics, input/config/code digests, execution
   limits and resume behavior. A passing runner check is not an accuracy claim.
3. **Run the labeled diagnostics when evidence is ready.** First use the existing
   Batch 2 evaluator on genuinely labeled pairs; missing edges stay unknown. Then
   run the four Batch 3 arms on development inputs, choose and freeze one candidate,
   and evaluate it once on untouched holdout. Report false covers, selected unique
   loss, true-cover recall, unknown/retention, omitted candidates and stage costs,
   with per-event numerators/denominators and comparison to the same-input baseline.
4. **Decide from results.** Stop a failing candidate and preserve its report. Only
   attribution can justify one subsequent matcher/representation hypothesis.
   G3/G4 still precede production design; deployment and photo writes remain separate.

The controller can perform inventory, runner preparation, execution and review
without asking the user to operate the browser or run commands. Independent
human evidence remains required for claims about meaningful content and personal
selection preference. If that evidence is unavailable, finish the inventory and
runnable protocol and report the precise quality-evaluation dependency. Do not
substitute more UI work, proxy labels or repeated historical tuning for it.

### Next substantive step and dispatch boundary

October 2 public-benchmark search, explicitly requested by the user, found
standard targets and published results; see the
[source review](2026-10-02-public-benchmark-search.md). The user's subsequent
request to download several datasets authorizes a new bounded composite
acquisition: KonIQ quality, KADID distortion quality, Copydays correspondence
and pinned AlbumBench task metadata. See the
[composite protocol and recovery commands](benchmarks/2026-10-02-public-composite/README.md).
Native targets and official AlbumBench splits are preserved. This diagnostic
does not require new personal annotation work and cannot pass G1/G2.

The frozen local-heuristic/pHash baseline is complete and pushed as `d746815`,
with separate quality/copy metrics and explicit unsupported AlbumBench predictions.
The [October 3 NIMA comparison](benchmarks/2026-10-03-public-nima/README.md)
uses the same 2,048 quality images, fixed existing weights and CPU settings,
with KADID reference-family development/comparison boundaries frozen before
inference. All predictions succeeded and exact-command resume matched. NIMA
SROCC improved sampled KADID (0.0694 to 0.3630), but regressed sampled KonIQ
(0.3643 to 0.2806); do not replace the quality scorer with raw NIMA aesthetics.
These are diagnostic partitions with prior label exposure and unknown training
overlap, not blinded holdouts. No fusion or thresholds were fitted.

The [controller self-review](benchmarks/2026-10-03-public-nima/self-review.md)
verified native-label joins, exact cohorts, source/cache identities and all twelve
baseline/NIMA correlations without finding a scoped implementation defect.
The [fixed MUSIQ experiment](benchmarks/2026-10-03-public-musiq/README.md) is now
executed on the unchanged quality cohort. All 2,048 offline CPU predictions and
exact-command resume passed, with identical metrics/intervals and provenance.
Independent recomputation verified all twelve baseline/MUSIQ correlations and
six paired 2,000-draw bootstrap interval sets. KADID SROCC improved to 0.5487
from 0.0694, with family-resampled delta interval +0.3935 to +0.5610. KonIQ 0.8695
remains training-exposed; image resampling does not establish semantic independence
or cure training exposure. Observed peak RSS was 988,086,272 bytes; the lean
Intel image excludes Torch/PyIQA, so runtime and product utility remain unaccepted.
Do not promote default quality/fusion/rejection settings from this diagnostic.

The next substantive experiment compares pHash with one existing embedding
candidate on the unchanged Copydays gallery/query cohort (157 originals / 229
strong queries). Verify asset/training exposure, freeze preprocessing, similarity,
tie handling and resource limits before inference, then execute, review and push.
Preserve complete-gallery correspondence checks and separate top-1/MRR/failure/tie
metrics. Do not convert a copy match into semantic grouping/coverage or discard
authorization. Technical-quality runtime feasibility remains a distinct later
decision. Do not compare diagnostics with published trained-model results as if
they shared a protocol or tune on the comparison partition. Complete this step's
review and normal push before another candidate; do not launch a parallel sweep.

The preparation handoff now contains the input/provenance inventory, exact G1
shortfall, runnable commands, frozen synthetic protocol and parity/isolation
checks. Its decision is **no-go for directed-coverage evaluation** while G1/G2 are
unmet. Do not restart completed preparation, polish the viewer, tune thresholds
on historical samples or launch another model merely to keep tasks busy.

For the directed-coverage track, resolve the independent-reference input scope:
the minimum is 24 qualifying
pairs / 12 independent families, including the specified positive/negative and
illumination/hand-expression/nuisance coverage. Existing inspected or model-labeled
examples do not fill those quotas. No person has been assigned annotation work,
and standard benchmark targets do not fill those quotas. With suitable authorized
inputs and independent judgments available, freeze a real-data manifest, add only
its minimal runner binding, then execute G2 and the development/holdout sequence.

The composite scope uses bounded preparation, execution and independent review
assignments. Keep design, integration and final review in the controller. Each
owner saves files and atomic checkpoints before final chat output; acquisition
partials and verified archives remain available after quota interruption. Do not
launch a parallel model sweep until this baseline has been reviewed.

The [current status ledger](2026-09-16-plan-status.md) owns execution status.
The user authorizes one review/verification/push per completed step and separately
authorizes this new composite download. Historical acquisition budgets remain
closed for their earlier scopes. The direct-witness invariant, conservative unknown handling,
quality/selection separation and production time-plus-pHash behavior remain intact.
