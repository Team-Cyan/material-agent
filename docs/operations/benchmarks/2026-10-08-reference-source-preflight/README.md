# Independent-reference source preflight — October 8, 2026

The newly author-linked FGAesthetics label archive is accessible and byte-verified.
This closes a metadata access question, not a photographic-quality or directed
coverage gate. No image archive, model, inference, submission, external message
or production operation was performed. Existing Photo Triage access findings and
completed benchmark runs remain closed.

## Primary sources and frozen release

The [author repository](https://github.com/yzc-ippl/FG-IAA/tree/a1b2250da2e8bfc466ed3172de29310bafa0283f)
announces a September 30 dataset release. The older
[project website](https://yzc-ippl.github.io/FG-IAA/) still labels the dataset
“soon” and links a model page; use the actual author-linked
[dataset revision](https://huggingface.co/datasets/yzc002/FGAesthetics/tree/f806ec5b06f02d5e80c40e866e397ad78bf9bc09)
instead of treating that placeholder as access evidence. The existing
[author discussion](https://github.com/yzc-ippl/FG-IAA/issues/1) confirms public
release but supplies no field-definition, lineage or rights clarification.

The [paper](https://arxiv.org/html/2603.03907v1) describes human within-series
aesthetic comparisons, with Natural, AIGC and Cropping inputs. Natural includes
both SPS stills and LSVQ video frames; comparative explanatory text is separately
model-generated. Its headline is 10,028 series / 32,217 images / 44,863 pairs.
Those targets do not supply directed important-content coverage, localized
important/nuisance regions or readable unique-content judgments.

## Actual label artifacts

Only `label.rar` was acquired: 201,749 bytes, exactly matching official LFS size
and SHA-256 `de17293c3bdf12c1181be911d2accb7ba7b2acd5bf920da662badcd663bbf8b1`.
Its nine text members total 915,890 bytes. Only fixed text members were read to
stdout; each returned body was checked against a 512 KiB maximum. Images,
provider scripts and weights were not extracted or executed.
Pinned artifact retrieval used nine requests / 253,659 response bytes under the
12-request / 24 MiB cap. Failed assumptions and original artifacts remain in
ignored storage; public results contain only aggregate structure and identities.

| Category / split | Rows | First-column IDs | Referenced image-index tuples |
| --- | ---: | ---: | ---: |
| Natural train | 11,196 | 3,862 | 10,522 |
| Natural val | 538 | 490 | 1,004 |
| Natural test | 824 | 403 | 996 |
| AIGC train | 4,592 | 2,634 | 6,586 |
| AIGC val | 585 | 448 | 1,004 |
| AIGC test | 847 | 339 | 995 |
| Cropping train | 22,258 | 1,275 | 8,555 |
| Cropping val | 1,297 | 259 | 1,009 |
| Cropping test | 2,088 | 168 | 990 |
| Total | 44,225 | 9,878 | 31,661 |

All rows have six numeric fields; the fourth is finite within [0,1]. The final
columns are consistent for each referenced image index, but their precise
semantics and preference direction are undocumented in the examined release.
Do not infer a scoring target from a plausible column layout.

Each category has zero first-column ID intersections across train/val/test.
This is list-level separation, not proof of independent scenes, capture events,
video families, source permissions or training-data independence.

`aigc_train.txt` has one entirely identical repeated ordered pair, already counted
in the table; there are no conflicting duplicate keys. `natural_train.txt` has
92 rows with fourth-column value 0.5. Preserve them; without confirmed semantics,
no definite preference or tie-handling rule is assigned. The first strict audit
stopped on pair uniqueness; that failure was retained rather than removing the
row to manufacture a pass.

Natural totals 4,755 IDs / 12,522 referenced image tuples / 12,558 rows,
numerically matching the paper's SPS row. Overall label-reference counts differ
from the paper by 150 / 556 / 638. This comparison does not establish which
sources the IDs denote, missing image files, or the reason for the difference.
Actual image inventories and a source crosswalk were not inspected.

## Admission and next step

The pinned HF card has no dataset-specific license metadata; neither examined
repository tree/README supplies a dataset-specific grant or item-level source,
capture-time and scene-family crosswalk. The website footer licenses its adapted
website template; it does not establish image-dataset terms. These are scoped
missing facts, not a claim that the dataset cannot be used anywhere.

Image acquisition and ranking execution are not selected yet. First obtain
published field definitions, applicable source terms and a release/source
crosswalk. Then freeze a bounded existing-scorer preference diagnostic, retaining
the actual official partitions, duplicate/tie accounting and training-exposure
limits before prediction. Do not tune on test labels or download the new model
as a consequence of finding this dataset.

G1 remains zero qualifying pairs/families: aesthetic rank labels cannot become
coverage edges. Its minimum 24 pairs / 12 independent still-photo families and
both splits' positive/negative and visible-evidence quotas still require genuine
independent rubric judgments. G2 and any representation or discard promotion
remain pending. Independent metadata recomputation confirmed all table counts,
split intersections and anomalies. No new annotation interface is selected.

[results.json](results.json) is the sanitized machine-readable audit. The
[continuation plan](../../2026-09-26-culling-improvement-plan.md) retains the
quality-versus-coverage boundary.
