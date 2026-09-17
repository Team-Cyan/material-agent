# Real exposure-bracket grouping counterexample

The current default hash threshold does **not** guarantee that a badly exposed
first frame joins the corrected frames, even within one second. A real public
RAW pair reproduces a split followed by singleton coverage keeping the bad frame.
No production policy was changed to fit this example.

## Source and integrity

Source: Nima Khademi Kalantari and Ravi Ramamoorthi,
[Deep High Dynamic Range Imaging of Dynamic Scenes](https://cseweb.ucsd.edu/~viscomp/projects/SIG17HDR/),
SIGGRAPH 2017. The authors' test archive includes three Canon CR2 originals for
`LadySitting`. Only those originals and archive metadata were retained for this
local diagnostic. Archive CRC32 and SHA-256 were checked; source hashes were
verified again after scoring. Selected original RAW bytes total 79,165,903.

The public project provides downloads for research; no explicit redistribution
license was found in the inspected project page, code README or test README.
This report redistributes **no image content or archive code** and makes no
open-license claim. Only identifiers, measurements and hashes are included.

## Actual EXIF and unchanged grouping

| File | Original time + subseconds | Shutter | Aperture | ISO | Score | Quality |
| --- | --- | --- | --- | --- | ---: | --- |
| 262A2705.CR2 | 13:09:29.11 | 1/250 s | f/8 | 400 | 3.53 | reject |
| 262A2707.CR2 | 13:09:29.45 | 1/60 s | f/4 | 400 | 6.43 | review |
| 262A2706.CR2 | 13:10:19.18 | 1/125 s | f/5.6 | 400 | 5.98 | review |

Date is 2016-12-17. The first pair is approximately 0.34 seconds apart and
4.06 stops apart by shutter/aperture, with unchanged ISO. The middle-exposure
file has an actual 50-second timestamp gap; it is not fabricated into a burst.
Current grouping reads whole-second DateTimeOriginal and stably sorts that value;
this example does not depend on subsecond precision for its 10-second gate.

Hashes from the unchanged production `_hash_file` path are recorded in results.
Dark-to-bright distance is **24/64**; dark-to-middle is 14, middle-to-bright 18.
Main-agent visual inspection of the actual default previews confirms a dark
interior/person in the first frame and a brighter person/interior with clipped
window highlights in the third. This is a bracketed HDR research scene, not a
human-labeled mistake/correction sequence or universal aesthetic ground truth.

Frozen scoring config is the [HDR+ holdout config](../2026-09-17-hdrplus-holdout/config.json).
The real `decode_raw`, `compute_scores`, domain `Grouper`, and group-selection
function were called without a database, writer or synthetic timestamps. Scoring
previews/focus use the production decode contract. No HDR fusion was performed.

## Parameter diagnostic, not a new default

All rows use `time_gap_seconds: 10`. Scores/quality are unchanged across rows.

| Hash threshold | First dark and bright pair | Dark selection | Brighter selection |
| ---: | --- | --- | --- |
| 10 (current default) | Separate groups | keep, singleton coverage | keep, singleton coverage |
| 24 (post-observation diagnostic) | Same group | reject | keep, group coverage |
| 0 (existing time-only option) | Same group | reject | keep, group coverage |

The 50-second-later frame remains separate in every row. Threshold 24 was chosen
from the observed distance solely to demonstrate the boundary, not calibrated on
an independent negative set. Increasing it can also merge different subjects or
actions within the time window; zero intentionally removes all visual checking.
No default or exception was introduced. The frozen product rule remains adjacent
time AND hash proximity, with zero selecting time only.

There are two independent failure surfaces: hash splitting and quality/selection.
This real example's quality stage rejects the dark frame, but split-group coverage
retains it. A previous synthetic display-brightness diagnostic also showed that
clipped previews can be ranked above an original. Those synthetic variants are
not physical RAW exposure changes and do not prove a general quality fix.

A robust next experiment needs labeled exposure-correction pairs **and** same-time
different-subject/action negatives, a frozen calibration/holdout split, and a
comparison of exposure-normalized visual evidence before changing production
hash behavior. Severe clipping can destroy correspondence evidence; a time-only
exception is a separate product tradeoff awaiting the user's decision.

## Follow-up exposure-normalization ablation

The ablation plan was frozen before computing alternative hashes. It compares
64-bit pHash, grayscale histogram-equalized pHash, grayscale autocontrast pHash
(cutoff zero), and dHash on the same 256-pixel production hash input. All 103
baseline hashes were asserted equal to the actual `_hash_file` output. Original
SHA-256 values were rechecked. No derived image or source metadata was written.

HDR+ events 1–10 form a calibration partition and 11–20 a separate holdout
partition; no fitting occurs in this diagnostic. Each partition has 100 positive
pairs (all ten pairs within each five-frame event) and 225 negative pairs
(all 25 cross-frame pairs between consecutive event IDs). The 450 negatives
represent only 18 distinct event-pair comparisons and are strongly correlated.
They are easy different-event controls with no fabricated timestamps, **not**
same-time different-action/dish negatives. This new partition does not retroactively
make the previously inspected exposure bracket a blind holdout.

| Hash variant | Dark/bright bracket distance | Positive pass at 10, calibration / holdout | Negative match at 10, calibration / holdout | Negative match at 24, calibration / holdout |
| --- | ---: | --- | --- | --- |
| Current pHash | 24 | 100/100 / 100/100 | 0/225 / 0/225 | 25/225 / 25/225 |
| Histogram-equalized pHash | 4 | 100/100 / 100/100 | 0/225 / 0/225 | 50/225 / 50/225 |
| Autocontrast pHash | 24 | 100/100 / 100/100 | 0/225 / 0/225 | 25/225 / 25/225 |
| dHash | 10 | 100/100 / 100/100 | 0/225 / 0/225 | 200/225 / 125/225 |

The equalized variant is a promising exposure-tolerant candidate; it recovers
this pair without raising the distance threshold. Autocontrast does not recover
it. Increasing the existing threshold to 24 admits 50/450 different-event pairs
in this fixture, so that single-example threshold change is not justified.
These counts assess hash matching only: real different-event timestamps would
still prevent grouping. They must not be reported as observed production merges.

No algorithm is promoted. Before replacing the current hash, collect independently
labeled hard negatives from the user's same-time different-subject/action case,
include clipped/near-featureless controls and camera/preview variation, and
freeze calibration and holdout events. A change also needs versioned hash-cache
identity and compatibility tests so old pHash entries cannot be mixed with new
normalized hashes. Keep the existing time gate and threshold-zero bypass.

The subsequent [fixed-background synthetic stress test](../2026-09-17-hash-hardcases/report.md)
adds harder controls and final selection outcomes. Equalization still merges
11/24 central-content replacements on holdout, causing one distinct-content
reject, so the easy-negative result above must not be used as a promotion gate.
