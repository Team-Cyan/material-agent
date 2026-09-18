# Spatial reference collection scope and provenance

This batch collects reference evidence, not algorithm performance. No third
candidate, residual threshold or learned model is introduced. The prior report
now explicitly states that SIFT input resolution changed together with residual
representation; its development improvement is confounded. A 2x2 algorithm run
would not change the already failed fresh-burst gate or the need for references,
so only the interpretation was corrected.

The [rubric](rubric.json) was written before candidate inspection. A neutral
first-frame inventory of the existing twenty HDR+ bursts selected eight distinct
scenes for category diversity. The first and fifth available frames form each
pair. Four action-transition pairs were selected from official MPII annotations,
without accessing algorithm results. Those four pairs count as **one physical
scene**, not four independent sources. Source/action labels are withheld from the
two independent visual panels. This gives 12 pairs / nine scene sources / two
datasets. It is new spatial annotation of existing data, not a fresh algorithm
holdout. Portrait expression visibility is not guaranteed and must be judged.

The selected HDR+ scenes include a lakeshore, forest, rock-slope hiker, public
atrium, rocky coast with a person, wooded hillside, waterfall/ruins and dark room.
The MPII samples add visible kitchen actions/object changes. These descriptions
are sampling context, not reference labels. Actual categories and visibility must
come from the blinded panels.

## Licenses and budget

- HDR+: [provider and attribution](https://www.hdrplusdata.org/dataset.html),
  Hasinoff et al., SIGGRAPH Asia 2016, CC-BY-SA 4.0. Existing downloaded source
  identifiers, URLs and SHA-256 values are in [inputs](inputs.json).
- MPII Cooking 2: [provider terms](https://www.mpi-inf.mpg.de/departments/computer-vision-and-machine-learning/research/human-activity-recognition/mpii-cooking-2-dataset/),
  Rohrbach et al., IJCV 2015. Scientific-use diagnostic processing only; no media
  redistribution or commercial deployment/training permission is inferred.
- The existing UCSD exposure bracket is excluded from this new reference package
  because inspected license evidence was insufficient for the proposed new use.
  No licensing gap is bypassed by relabeling organizational work as personal use.

New downloads: **0 bytes** of the 100 MB cap. Source selection started at
`2026-09-18 17:16:11 UTC`; the input manifest was frozen by
`2026-09-18 17:18:35.982406 UTC`, approximately **145 seconds**, below the cumulative
30-minute source-search cap. Subsequent quota pauses do not reset that budget.
All 17 unique source files matched their existing digests during package checks.
No public or private image assets are committed; only textual metadata and
annotations are persisted. The renderer creates paired JPEG montages in memory.

## Annotation and conservative agreement

Each panel sees only the rubric and neutral rendered pairs. Panel B reverses
pair and image order. Region boxes use each 768x570 displayed panel excluding the
30-pixel title; unused padding remains within the coordinate frame. Boxes are
therefore displayed-image coordinates, not raw sensor coordinates.

The assessor validates IDs, both unique directed relations, finite normalized
boxes and confidence, categories and provenance. Agreement requires category and
importance equality, confidence at least 0.75, clear visibility in both panels,
and corresponding box overlap at least 0.3 IoU on both photos. This clear-visibility
requirement is a conservative operationalization of reliable reference evidence.
Unmatched regions and both original labels remain in the output. No majority vote
or quality score supplies ground truth.

Feasibility requires 12–24 pairs, four distinct scenes, two agreed important pairs,
two agreed nuisance pairs and the rubric's category coverage. If either panel
needs personal preference for a pair, that counts toward the more-than-half stop
criterion. Incomplete panels remain incomplete; synthetic labels do not fill
missing real-scene references. Any successful reference set permits a next
research proposal only, never immediate algorithm integration.

Independent panel attempts initially hit a usage limit reporting a 05:53 reset.
The subsequent request authorized one bounded recovery attempt on the same inputs.
No completed panel output existed at recovery, and sample/search budgets were not
reset. The final status/report will record whether that attempt completed.
