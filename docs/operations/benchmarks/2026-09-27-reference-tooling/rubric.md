# Human annotation rubric v1

Annotate independently from the images. Do not consult scores, algorithms, source
categories, desired quotas or other annotators. The viewer's A and B are neutral
presentation names. A later export maps them back to private source identities.

## Content and direction

First judge visible correspondence: `yes`, `no`, `unknown` or `unjudgeable`.
Correspondence is spatial/subject comparability, not identity of all content.
For A → B ask: **Would retaining A preserve all important visible content of B?**
Then ask B → A independently. Direction is coverage, not chronological order.

- `cover`: visible evidence supports full preservation of important target
  content; nuisance differences do not matter for this judgment.
- `negative`: a clear important target region/content is absent or changed in
  the source. Mark that region on the target (B for A → B; A for B → A).
- `unknown`: evidence is insufficient or a fine same-action progression cannot
  confidently be called important or nuisance.
- `unjudgeable`: visibility, decoding/preview quality, lack of correspondence or
  occlusion prevents a useful comparison. This is not a negative.
- `preference_dependent`: the difference matters only under an unresolved human
  preference. Do not invent that preference or force cover/negative.

Distinct dishes, object states, actions, clear gestures and expressions can be
important. Exposure, changing shadows, texture/noise or composition may be
nuisance **only when inspected evidence supports that conclusion**. A darker
image is not automatically redundant. A silhouette/back view is not an error
merely because no face is visible. Preserve uncertainty and disagreement.

Use `no_visible_change` only when there is no visible change to localize; it
cannot coexist with regions or negative coverage. Otherwise localize the actual
change. A pair-level explanation should explain both directions, especially
when they differ. Never infer a transitive relation through a third image.

## Regions and coordinates

Choose an image side, importance (`important`, `nuisance`, `unknown`,
`preference_dependent`), observed phenomenon, visibility (`clear`, `limited`,
`not_visible`) and a concrete description. Drag a nonempty box on that image.
The coordinate system is normalized **[x1, y1, x2, y2] within the fully oriented
image pixels**, origin at top left, x rightward, y downward, with 0 ≤ x1 < x2 ≤ 1
and 0 ≤ y1 < y2 ≤ 1. Titles, browser whitespace and padding are excluded. Browser
scaling does not change the coordinates. Paired boxes need not occupy identical
coordinates: locate evidence on each image separately.

Select the observed phenomenon: `exposure`, `illumination`, `texture_noise`,
`object_state`, `hand_progression`, `expression_pose`, `camera_motion` or
`occlusion`. These are observations, not imported acquisition-category targets.
If evidence is limited or invisible, use the corresponding visibility and
abstain on the relation; it cannot meet a visible-evidence quota. Include enough
boxes to support the directional claims, not decorative whole-image boxes.

## Independent quality

Judge A and B independently as `readable`, `unreadable` or `unknown`. Record a
quality preference (`A`, `B`, `tie`, `unknown`, `preference_dependent`) and reason.
Coverage must not consult the quality preference: a lower-quality readable
unique image can still contain content the better image lacks. These fields do
not create production scores, ratings or defect reasons, and the viewer never
writes XMP or deletes photos.

## Provenance and disagreement

Save and export your own observations. Start/completion timestamps and input
preview hashes are included automatically; they establish traceable declarations,
not proof of human identity. The curator retains source hash, permission,
capture metadata provenance, preview recipe, split freeze and lineage privately.

Do not change a previous annotator's record. Independent disagreement stays
unresolved until a human adjudication records all raw record IDs and its own
later timestamp/reason. Regions, quality and correspondence disagreements also
require review; a majority label is not sufficient. Unknowns are useful evidence
and never count toward positive/negative quotas. Two directed judgments from
one pair are two directions, not two independent events.
