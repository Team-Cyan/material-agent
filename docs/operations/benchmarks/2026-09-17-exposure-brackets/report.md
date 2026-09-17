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
