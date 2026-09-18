# Spatial references: collection complete, feasibility gate failed

The bounded reference package is complete. It does not justify another algorithm
experiment. Two independent panels finished 12 pairs / nine physical scenes, but
only one pair has an agreed, clearly visible important region and no pair has an
agreed nuisance region. The freeze requires at least two of each plus category
coverage. The stop reason is inadequate localized reference evidence, not a
majority of user-preference questions.

Files: [rubric](rubric.json), [inputs](inputs.json), [provenance](provenance.md),
[panel A](panel-a.json), [panel B](panel-b.json), [assessment](assessment.json),
[display observations](display-observations.json), [minimal user example](user-example.json).
Preparation/validation commit: `775b3f3`. There is no third model or threshold
candidate and no result-based sample selection.

## Evidence and limits

| Measure | Result |
| --- | ---: |
| Blinded pairs completed per panel | 12 / 12 |
| Distinct physical scenes | 9 |
| Dataset sources | 2 |
| Directed relation agreement above confidence gate | 24 / 24 |
| Consensus cover / different directions | 16 / 8 |
| Agreed important spatial pairs | 1, P09 |
| Agreed nuisance spatial pairs | 0 |
| Preference required by either panel | 3 / 12, P10–P12 |
| Required category groups with clear spatial agreement | Object state/identity only |
| Human ground-truth labels | 0 |

Scene variety and relation agreement do not replace spatial evidence. Seven RAW
pairs have no localized region in panel A. P08 has an acquisition-noise region in
A but no region in B; this is not a consensus nuisance annotation. P09 has agreed
object-change boxes. Other kitchen pairs disagree on localization, visibility or
importance even where their overall `different` labels agree. The assessor keeps
unmatched regions and both labels instead of manufacturing agreement.

The decoded previews are not byte-identical. Unregistered displayed RGB mean
absolute differences range from 2.952 to 13.916 across the eight RAW pairs. These
measurements verify that rendering did not simply repeat one image; they do not
label motion, importance or duplicate content. Small changes may be unresolved
at the displayed scale. Expressions are not reliably represented by this set.

All four kitchen pairs count as one scene and are not four independent event
sources. Official action labels were used only to select contrasts; the visual
panels never saw those labels or algorithm results. Prior user intent already
requires retaining different dishes/actions. A model calling such a contrast
preference-dependent does not revoke that instruction or require the user to
repeat it. Model-generated spatial disagreement remains evidence of reference
limitations, not a new product requirement.

## Scope, licensing and recovery

New downloads remain **0 bytes**. Seventeen unique local public source files were
verified against their existing hashes. The initial selection completed within
145 seconds. A supplementary primary-source check considered
[HPatches full sequences](https://github.com/hpatches/hpatches-dataset/blob/master/README.md)
for illumination changes: the full archive is listed as 1.3 GB, and the repository
[MIT notice](https://github.com/hpatches/hpatches-dataset/blob/master/LICENSE)
explicitly concerns software/documentation, without resolving all underlying image
rights. It was not downloaded or used to bypass either the 100 MB cap or the
license requirement. The two short lookup calls are conservatively included in
a **five-minute cumulative active source-search allowance used**, below the
30-minute cap; quota waiting is not a reset of the search budget.

Both initial panel attempts hit a usage limit. One recovery attempt resumed each
same panel after the reported reset. Both then completed all twelve actual image
views; no quota blocker remains. No images or XMP were written. Montages were
rendered in memory; the repository contains text annotations and fingerprints only.

The 512/1024 SIFT-resolution confound is now explicit in the
[previous hypothesis report](../2026-09-19-coverage-observability/report.md).
No 2x2 rerun was needed to choose this reference-collection step: the untouched
burst retention gate had already failed. Neither old holdout nor thresholds were
retuned.

## One minimal user example and next recommendation

U01 is an additional real-video pair, outside the frozen twelve-panel assessment:
frames 3245 and 3392 of `s22-d23`, both annotated as the same cut-dice segment.
It brings the cumulative sample count to **13 pairs**, still within 12–24; the
source file was already present and adds no download. Shared action annotation
is not proof of identical meaningful content.

The user was shown the actual paired images and asked only whether the hand/cutting
progress differences within this same action can be covered by one better-quality
photo, should both be retained, or are too unclear to judge. Different dishes or
action phases remain covered by the user's earlier requirement. The example is
not added as ground truth until the user answers. This question is a preference
clarification, not permission to change production.

The single next recommendation for independent review is **reference adjudication,
not another algorithm**: first record the user's U01 intent as a scoped example;
then require independently visible, localized nuisance/illumination and small
subject-change contrasts before proposing any new coverage predicate. One user
answer does not fill the current category or spatial-reference gaps. Preserve the
failed feasibility result, existing production behavior, and all panel disagreement.

## Verification and reproduction

Twelve focused guarded checks passed: ten assessor tests and two repository
boundary tests. They cover reversed panel/box coordinates, disagreement, low
confidence/visibility, preference aggregation, invalid/partial panels, and sample
count gates. `make check` and `git diff --check` passed. Source hashes and artifact
fingerprints were checked; no production review, deployment or push occurred.

```sh
uv run --no-sync python scripts/assess_spatial_reference.py \
  --inputs docs/operations/benchmarks/2026-09-19-spatial-reference/inputs.json \
  --panel-a docs/operations/benchmarks/2026-09-19-spatial-reference/panel-a.json \
  --panel-b docs/operations/benchmarks/2026-09-19-spatial-reference/panel-b.json \
  --output .local/direct-coverage/spatial-assessment-reproduction.json
uv run --no-sync python scripts/render_spatial_reference.py A 0 \
  --example docs/operations/benchmarks/2026-09-19-spatial-reference/user-example.json
```

The renderer writes base64 JPEG only to stdout for direct viewing, not an image
file. Existing source datasets are required locally. The user-example option was
added after panel collection; the panels used the `775b3f3` renderer's fixed
12-pair path, which remains unchanged when that option is omitted.
