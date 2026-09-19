# Final bounded spatial-reference supplement

The final collection uses four new, fixed CDnet2012 frame pairs. It does not
introduce another algorithm, change production grouping, tune thresholds, or
relabel the original twelve references. U01 remains outside blind annotation.

## Sources, sampling and budget

[The frozen plan](plan.json) precedes all new candidate viewing. Sequence names
were frozen as `backdoor`, `boats`, `fall`, and `office` before acquisition or
visual inspection. These target shadow, water, foliage and indoor-person
contrasts respectively; these are acquisition categories, not observed labels.
The first and thirtieth JPEG members are used without replacement. Frame rate
was not established, so these are index-only pairs, not verified one-second
intervals. Each sequence contributes one pair and one distinct scene.

[Source ledger](source-ledger.json), [HEAD probes](source-probes.json),
[acquisition ledger](acquisition.json), and [input hashes](inputs.json) preserve
retrieval evidence. Strict HTTP 206 ranges read ZIP directories and the selected
members; ZIP CRC validation and SHA256 protect the retrieved originals.

- Cumulative search accounting: **1,752 / 1,800 seconds (29m12s)**. This includes
  the previous 300-second allowance plus a conservative 03:03:00–03:27:12 UTC
  window on September 19. That window includes intervening development and a
  separately requested push; active search time was not separately measured.
  Search is closed, not reset. Annotation and local reporting occur afterward.
- Measured dataset transfer: **3,797,249 / 100,000,000 bytes**, including ZIP
  metadata; retained eight original JPEGs total **288,129 bytes**. Web-connector
  HTML metadata transfer is not measured, so this is not an exact total network
  byte claim. No full ZIP, RAW collection or replacement frames were downloaded.
- Pair budget: prior 13 including pending U01 + 4 new = **17 / 24**. The combined
  blind reference assessment has 16 pairs; it excludes U01.
- Two sources inspected, one acquired. No third source or additional search is
  started after closure. Originals remain ignored local inputs; no media is
  committed or redistributed.

DAVIS was excluded because the inspected rules establish annotation licensing
but did not establish source-media permission. The inspected URLs are in the
ledger; exclusion is an evidence gap, not a claim that use is prohibited.

[CDnet's official participation page](https://changedetection.net/) invites
academic and industrial research evaluation. This is used narrowly for local
change-reference diagnostics, not treated as a blanket redistribution or
production-use license. The [2012 download documentation](https://changedetection.net/dataset2012/)
defines individual image sequences. Its motion masks were not used as personal
importance labels. Attribution: N. Goyette, P.-M. Jodoin, F. Porikli, J. Konrad,
and P. Ishwar, *changedetection.net: A new change detection benchmark dataset*,
CDW-2012 at CVPR-2012.

## Annotation and reproducibility

Two fresh independent Codex `gpt-5.6-sol` medium panels inspected four rendered
pairs each. Panel B reverses pair order and left/right orientation. Only neutral
IDs, images, and the unchanged original rubric were provided; no algorithm
outputs, other-panel judgments, source category targets, or original labels.
These are model-generated visual references, not human ground truth.

The renderer checks each input SHA256 and makes a display-only montage in
memory. Small frames are enlarged for inspection; enlargement adds no detail.
Coordinates include the white padding within the 768x570 image panel below
the 30-pixel title. Neither source photos nor derived media files are written.

`scripts/assess_spatial_supplement.py` retains the original panel files verbatim,
renumbers only neutral identifiers in memory, and assesses original+supplement
as one set. B's two sets are concatenated in the opposite order to preserve
pair alignment. The regression test checks distinct category alignment and
byte-for-byte original-file preservation. All disagreements remain visible.

## Results and stopping decision

[Panel A](panel-a.json), [panel B](panel-b.json), and the
[combined assessment](combined-assessment.json) give **16 pairs / 13 scenes**:

| Fixed pair | Visible result under both panels | Spatial evidence |
| --- | --- | --- |
| S01 backdoor | Tiny cropped edge fragment; direction judgments differ or abstain | No agreed important/nuisance region; does not establish a usable shadow contrast |
| S02 boats | Clear vehicle identity/appearance difference, plus local water-ripple variation | Agreed important object and nuisance water regions on this single pair |
| S03 fall | No reliably localizable change at displayed resolution | No foliage-change reference; unchanged appearance is not nuisance evidence |
| S04 office | No reliably localizable change at displayed resolution | No gesture/expression reference |

The joint gate has **two important pairs** (old P09 and new S02), but only
**one nuisance pair** (S02), below the required two distinct pairs. Water and
object coverage now pass; illumination and gesture/expression still fail.
Three of sixteen pairs need preference in either panel; this is below the
strict-majority rule. Therefore:

- `blockers = ["reference_insufficient"]`;
- `reference_gaps = ["nuisance_regions", "category_coverage"]`;
- `preference_blocked = false`;
- no third algorithm or production promotion.

This final bounded supplement is **complete and stopped**. Poor visibility is
retained, not evaded with different frames or source searches. U01's unanswered
same-action fine-progression question does not explain or resolve the remaining
illumination/gesture data gap; different dishes/actions remain required to keep.

The sole next recommendation is to obtain a separately scoped, human-annotated
small reference collection with clearly visible local illumination changes and
hand/expression changes, including at least one additional independent nuisance
pair. This is a future evidence-collection proposal, not authorization to start
another download, experiment or photo-writing workflow. The present blocking
input is that missing reference evidence, not a new yes/no preference question.

## Verification and boundaries

Seventeen guarded tests passed across spatial assessment, joint-panel alignment,
and repository boundaries. Ruff and `git diff --check` passed. The original
input/panel files match their pre-supplement Git bytes. All eight source SHA256s
remain unchanged after rendering. Combined summary and pair results recompute
identically in memory. No production source code, defaults or runtime state was
changed; no source media/XMP writes, deployment, production review or push took
place in this supplement. The earlier user-requested push through `7f2a367` is
separate, completed before this continuation.
