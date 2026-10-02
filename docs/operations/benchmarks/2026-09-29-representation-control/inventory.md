# Existing culling evidence inventory — 2026-09-29

This inventory is limited to manifests and source paths already named by the
September 17–19 experiments and the September 27 reference tooling. It did not
search a wider photo library, acquire bytes, decode real media or inspect the
reserved holdout's judgment content. Availability means `is_file()` and, where
published, an exact size match. Historical manifests carry SHA-256 values, but
this inventory did **not** rehash the real media. It does not newly certify
permissions or source identity.

| Evidence and manifest | Local availability checked | Origin, permission and label provenance | Use now |
| --- | --- | --- | --- |
| [HDR+ 20-event manifest](../2026-09-17-hdrplus-holdout/manifest.json) and [source audit](../2026-09-18-direct-coverage/sources.md) | 100/100 DNG files, 100/100 published sizes; 2,064,640,904 bytes under ignored `.local/hdrplus-holdout/` | Real public RAW stills; provider-linked CC-BY-SA 4.0. Earlier scoring/spatial inspection consumed these events. Eight spatial pairs use model-generated panels. | Existing regression/preview-source inputs; none is a fresh human holdout. |
| [Direct-coverage inputs](../2026-09-18-direct-coverage/inputs.json) | Two selected HDR+ RAW cases have 6/6 DNG files in ignored `.local/direct-coverage/holdout/` (49,699,126 bytes); the UCSD exposure case has 3/3 CR2 files in its separate root. | These were fresh for the *old* direct-coverage run, then inspected/model-judged. Its 40 cases comprise 10 constructed synthetic, 27 video and 3 RAW cases; [blind references](../2026-09-18-direct-coverage/blind-references.json) are `model_generated`. | Regression only; old success/failure reports do not create new G1 labels. |
| [Observability holdout input manifest](../2026-09-19-coverage-observability/holdout-inputs.json) | 6/6 DNG files and sizes, 46,526,386 bytes under ignored `.local/direct-coverage/observability-holdout/` | Two real RAW events; model-generated holdout panels were opened in the completed 2026-09-19 experiment. | Previously inspected regression, not a reserved fresh holdout. Label content was not read for this inventory. |
| [UCSD exposure manifest](../2026-09-17-exposure-brackets/manifest.json) and [report](../2026-09-17-exposure-brackets/report.md) | 5/5 CR2 files and sizes, 79,166,102 bytes under ignored `.local/exposure-brackets/` | Real bracketed stills with actual EXIF discussed in the historical report. Redistribution permission was not established; human visual inspection is not a directed coverage label. | Read-only regression if separately scoped; no G1 quota. |
| [MPII Cooking 2 direct inputs](../2026-09-18-direct-coverage/inputs.json) and [spatial provenance](../2026-09-19-spatial-reference/provenance.md) | 2/2 distinct referenced AVI files, 59,308,002 bytes under ignored `.local/mpii-cooking/`; the one AVI used in the spatial-reference inputs is present | Video/action annotations are official task labels and only negative proxies. Provider terms limit scientific use and prohibit redistribution; 27 direct cases and four spatial pairs do not become independent still-photo events. Both visual panels are `model_generated`. | Historical diagnostic only, never human still-photo gold. |
| [CDnet2012 supplement inputs](../2026-09-19-spatial-supplement/inputs.json) and [report](../2026-09-19-spatial-supplement/report.md) | 8/8 JPEG frames and sizes, 288,129 bytes under ignored `.local/spatial-supplement/`; four pairs/four scenes | Public dataset frames used for narrow local change-reference diagnostics; no blanket media redistribution/production-use conclusion. Two panels are `model_generated`; motion masks are not importance labels. | Historical regression/reference diagnostic, not still-photo human gold. |
| [Historical observability synthetic plan](../2026-09-19-coverage-observability/plan.json) and [current frozen protocol](protocol.json) | Procedural controls are generated in memory, so source bytes are not missing files. This batch actually executed identity, JPEG quality, small luminance and isoluminant color. | Construction-based symbolic labels, not human judgments or realistic gesture/expression evidence. Noise, exposure and subpixel recipe parameters are frozen but those control kinds were **not** executed in the four-case matrix. | Wiring/parity/isolation only. |
| [Human-reference synthetic example](../2026-09-27-reference-tooling/synthetic-example.json) and [historical spatial package](../2026-09-19-spatial-reference/inputs.json) | Public manifest: 4 pairs/2 synthetic events/0 annotations; ignored demo bytes were available during its earlier validation. Spatial package: 12 pairs/9 physical scenes, plus four CDnet pairs/four scenes in the supplement. | The manifest's events are `synthetic`; prior panels explicitly say `model_generated`. [U01](../2026-09-19-spatial-reference/user-example.json) remains `awaiting_user` outside blind assessment. No genuine human directed still-photo coverage judgment appears in these referenced packages. | No G1 contribution. |

The checked paths had **zero missing files and zero size mismatches** among
these specific listed inputs. Different manifests overlap in source events, so
row counts and byte totals must not be added as independent data. Availability
is not label sufficiency. Existing model annotations and previously inspected
RAW stills do not become new holdout or human truth by reusing them.

The RAW preview recipe is recorded in the [earlier config](../2026-09-17-hdrplus-holdout/config.json)
(SHA-256 `040425b33053c22409f96822c1622e4f197bfd02f8b396877568c6f63941fe84`).
Spatial display used an in-memory renderer; its model panels are judgments, not
persisted source previews for this new matrix. A real labeled comparison would
still need frozen preview bytes/recipe and actual capture-time provenance per
candidate event, in addition to independent human judgments. The current
synthetic runner makes no real-media output or content-hash assertion.

## Exact known G1 gaps

Against the [current plan](../../2026-09-26-culling-improvement-plan.md), the
relevant manifests supply **0 qualifying fresh human-labeled still-photo pairs**
and **0 independently labeled scene families**. Thus the minimum shortfall is
24 pairs from 12 independent families (default target 32 pairs/16 families;
allowed cap 40 pairs/20 families). Because both splits have zero qualifying
relations, **development and holdout each lack at least six definite human-cover
and six definite human-negative directed relations**, with each class still
requiring three independent families. Counting A→B and B→A does not turn one
pair into two independent events.

Both splits lack qualifying visible illumination nuisance and qualifying clear
hand/expression change; the overall independent-family counts for each are
0/2. The observed human nuisance-type count is 0/2. None of the eight category
acquisition targets has a qualifying new human pair. Historical model regions
about water/objects do not fill these deficits, and unknown/unjudgeable or
preference-dependent directions cannot fill positive/negative quotas. Human
provenance, source permission, real capture-time and scene-family lineage would
also require audit when genuine labels are collected. These are missing inputs,
not permissions to reopen historical acquisition budgets or to invent labels.
