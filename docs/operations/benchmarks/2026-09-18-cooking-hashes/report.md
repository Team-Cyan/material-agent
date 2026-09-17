# Real cooking-video transitions: hash and final selection evidence

The exposure-normalized hash still cannot guarantee separation of rapid action
changes. On the small held-out video, current pHash merges 5/10 distinct-action
pairs; equalized pHash merges 3/10; dHash merges 10/10. Every such merge causes
one of the two distinct actions to receive final reject under current scoring
and coverage. No algorithm/default is promoted.

## Source, restrictions and frozen selection

Source: [MPII Cooking 2](https://www.mpi-inf.mpg.de/departments/computer-vision-and-machine-learning/research/human-activity-recognition/mpii-cooking-2-dataset),
Marcus Rohrbach et al., *Recognizing Fine-Grained and Composite Activities Using
Hand-Centric Features and Script Data*, IJCV 2015. The provider permits scientific
use and restricts redistribution. Original videos, annotation archives and frames
remain local; this repository contains only derived experiment evidence, hashes
and reproducibility identifiers, not the dataset or video content.

Select the first lexicographic sequence from the official attribute-training
split (`s07-d72`) and test split (`s22-d23`) before viewing/scoring. Downloaded
video sizes are 19,839,824 and 39,468,178 bytes. SHA-256 values are in the video
manifest. The complete 114,303,918-byte annotation file was read as MATLAB v7.3
with h5py in an isolated environment; no project dependency was changed.

Take up to ten same-segment pairs and ten successive distinct-action boundaries
per video, in chronological order. Same-segment samples are half a second inside
the start and at most five seconds later, staying half a second inside the end;
segments must last at least two seconds. Negative samples are half a second
inside each neighboring non-overlapping segment, with at most ten seconds between
them. Require nonempty, different action sets from the authoritative `iaMat`
attribute membership (action attributes end in `V`), not unchecked raw activities.
Convert MATLAB frame indices from one-based to zero-based. Freeze indices and
labels before scoring. There are only four positive/one negative eligible pairs
in the training video, and ten/ten in the test video: 25 pairs, 38 unique frames.
The capped first-sequence design is reproducible but is not broad acceptance.

Video and annotation frame rates both equal 29.4 fps. Group timestamps preserve
actual frame spacing (`frame_index / 29.4`) anchored to an arbitrary date; they
are **not camera EXIF** and no capture intervals are fabricated. OpenCV seeks are
checked against frame position/count. Preview is JPEG quality 85, max 1024 pixels;
its grayscale is also focus input. Candidate hashes use the exact decoded JPEG
and the production 256-pixel thumbnail rule. Scores use the frozen heuristic
config from the HDR+ experiment. This is real continuous video content, not RAW
camera quality acceptance or evidence about exposure correction.

## Results at ten-second / ten-bit thresholds

| Partition and candidate | Same-action splits | Different-action merges | Different-action pairs losing a frame to reject |
| --- | ---: | ---: | ---: |
| Calibration pHash | 1/4 | 1/1 | 1/1 |
| Calibration equalized pHash | 1/4 | 0/1 | 0/1 |
| Calibration dHash | 0/4 | 0/1 | 0/1 |
| Holdout pHash | 0/10 | 5/10 | 5/10 |
| Holdout equalized pHash | 0/10 | 3/10 | 3/10 |
| Holdout dHash | 0/10 | 10/10 | 10/10 |

These are official action-boundary labels used as grouping expectations, not
human quality/preference labels. Same action does not prove every moment is
interchangeable. Pairs within a video overlap/share frames; only two subjects/
sequences are represented, so pair counts are not independent event counts.
The wide, dark kitchen footage receives poor heuristic quality scores. Final
selection results expose coverage effects; they do not establish human-rated
quality accuracy. Row-level scores, quality and selection are retained separately.

Equalization is not uniformly better even within this tiny sample. Pair
`s22-d23-18` changes from `moveV` to `peelV` over 4.082 seconds. Current pHash
distance 12 separates it; equalization changes the distance to 8 and falsely
merges it (dHash distance 2). Main-agent inspection confirms the same wide kitchen
background with changed hand/tool activity. That inspection is a disclosed sanity
check, not an independent blind panel or substitute for official labels.

This real regression complements the [synthetic content-change test](../2026-09-17-hash-hardcases/report.md)
and the [real exposure bracket](../2026-09-17-exposure-brackets/report.md).
Recovering exposure similarity can also erase distinctions important to action
coverage. Keep conservative production behavior; do not add a time-only exception
or reintroduce semantic merging from these results.

## Reproduction and verification

The invocation below is historical for runner `a90e3ef`. The current runner
requires a frozen plan; use the [sequence protocol](../2026-09-18-cooking-sequences/report.md)
for a current command that also reproduces these pair results.

Download the two official URLs in `videos.json` into a local directory, keeping
original bytes unchanged. With the repository environment:

```sh
uv run --no-sync python scripts/benchmark_cooking_hashes.py \
  --videos .local/mpii-cooking \
  --pairs docs/operations/benchmarks/2026-09-18-cooking-hashes/frozen-pairs.json \
  --video-manifest docs/operations/benchmarks/2026-09-18-cooking-hashes/videos.json \
  --config docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json \
  --output-dir .local/cooking-hash-reproduction
```

The runner requires a new/empty output directory outside the source directory,
verifies video hashes before/after, and writes only JSON results. It invokes the
real grouping and group-selection code with fresh metadata per variant, without
a job database or writer. The reusable runner reproduced all 25 result rows and
summaries. Ruff, JSON/link checks and repository boundary checks pass. Existing
production source tests remain the previously verified 745 passed/102 skipped;
no shared production code changed in this evidence batch.

## Remaining acceptance boundary

Natural action negatives now have a bounded real-video check; the gap is no longer
simply “no hard negatives.” The current candidates demonstrably fail some of them.
A new hash proposal needs a fresh, broader subject/event holdout, explicit allowed
false-merge/false-split criteria, and cache revision separation before production
integration. Completely lost exposure detail still cannot establish visual
correspondence; the user's unanswered time-only-exception choice stays unresolved.
