# Codex independent blind-review diagnostic pilot

Status: completed after the user restored usage quota. This validates the review
channel and an obvious-blur diagnostic, not full real-burst preselection acceptance.

## Method and boundaries

Six existing public RAW sources were frozen by SHA-256. Each source provided its
1024-edge embedded/fallback preview and a GaussianBlur(radius=3.0) variant, both
JPEG quality 85. Variants existed only in memory. These are six controlled pairs,
not six natural bursts; capture-time/hash grouping accuracy was not tested.
These source images were previously used for decoder diagnostics and are not a
new event-disjoint holdout. No scoring thresholds were tuned on the judgments.

Two Codex subagents used `fork_turns=none`, requested model `gpt-5.6-sol`, medium
reasoning, and [rubric v1](../../evaluation/preselection-rubric-v1.json). Exact
provider model revision was not exposed. The panels received anonymous IDs and
opposite image orders, without baseline scores, filenames, transform labels,
model identities, or the other panel's answers. They could execute the renderer
but were instructed not to inspect its source or the private mapping. Independence
here means separate contexts, not independent model families or human reviewers.

Both panels ultimately displayed and inspected all 12 candidates. Group 5 exceeded
an initial tool-output budget; rerendering the identical bytes with a larger output
limit resolved display failures. Panel B corrected only that group's result after
successful viewing. Tool-display failure was not classified as a corrupt photo.
Both panels completed before the controller mapped and compared their judgments.
All references remain `model_generated`.

The baseline is the checked-in default local heuristic through full
`compute_scores` and group coverage; no production job, SQLite repository or XMP
writer was constructed. Learned optional models and refinement remained disabled.
Scores apply to the same encoded previews seen by reviewers, not full-resolution
RAWs. Input/renderer/baseline hashes were verified unchanged before resumption;
source RAW hashes were verified again after completion.

## Results

| Measure | Panel A | Panel B |
| --- | --- | --- |
| Visually inspected candidates | 12/12 | 12/12 |
| Baseline top-1 in reviewer preferred set | 6/6 | 6/6 |
| Baseline strict pairwise preference agreement | 6/6 | 6/6 |
| Groups retaining a reviewer-acceptable keep | 6/6 | 6/6 |
| Reviewer-acceptable candidates rejected by baseline | 0/6 | 0/6 |
| Baseline keeps outside reviewer-acceptable set | 0/6 | 0/6 |
| Pairwise ties / abstentions | 0/6 / 0/6 | 0/6 / 0/6 |

Opposite-order panels agreed on preferred sets **6/6** and acceptable keep sets
**6/6**. Each selected the original preview over its blurred variant. These are
six underlying comparisons, not twelve independent sample events.

| Group | Original quality score | Blurred quality score | Baseline keep role |
| --- | --- | --- | --- |
| 1 | 6.94 | 0.00 | group_coverage |
| 2 | 5.58 | 0.00 | group_coverage |
| 3 | 4.75 | 0.21 | group_coverage |
| 4 | 7.03 | 0.00 | group_coverage |
| 5 | 6.29 | 0.13 | group_coverage |
| 6 | 6.45 | 0.00 | group_coverage |

Coverage kept an original in each group without raising its quality score. This
is a diagnostic of large blur differences; zero errors on six controlled pairs
is not an estimated production false-reject rate. Scoring-only timings are kept
in JSON and exclude RAW preview generation, tool transport and reviewer latency.

## Evidence and next acceptance step

- [Panel A raw judgments](panel-a.json) and [Panel B raw judgments](panel-b.json)
- [Validated comparison and denominators](comparison.json)
- [Baseline scores, quality/selection roles and hashes](baseline-evidence.json)
- [Anonymous ID mapping](reveal-map.json), used only after review

No live humans, eye/face detail, action transitions, subtle near-ties, unique
memories or complete decode failures were evaluated visually. Reviewer language
about eye applicability on non-person scenes is not an acceptance test of the
portrait evidence contract. Full acceptance still needs a task-relevant frozen
real-burst subset, event-disjoint development/holdout splits and the missing case
categories. No additional model fusion or quality-threshold changes follow from
this pilot. Professional-software and hardware/container checks remain separate.
