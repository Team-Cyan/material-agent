# Frozen HDR+ event holdout and isolated candidate comparison

This is bounded diagnostic evidence, not product acceptance or a production
promotion. The default scoring stack and time/hash grouping policy are unchanged.
No source photo/XMP, production review, job database or live service was modified.

## Dataset and frozen protocol

The [official HDR+ dataset](https://www.hdrplusdata.org/dataset.html) is attributed
to Samuel W. Hasinoff et al., *Burst photography for high dynamic range and
low-light imaging on mobile cameras*, SIGGRAPH Asia 2016, and distributed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The manifest records source URLs, identifiers, byte sizes and original SHA-256.
No image content is redistributed here.

Before scoring or viewing, select 24 uniformly spaced official event prefixes,
take the first 20 with at least five frames, and take each event's first five
payload frames. Exclude the two previous pilot events. The resulting 100 DNGs
contain 2,064,640,904 bytes; cloud MD5 and local SHA-256 were verified. This is
an evaluation-only split, with no threshold fitting or training. It samples
mobile bursts, not the user's camera or a balanced defect/preference corpus.

Ordered `(id, sha256)` input fingerprint:
`3e07bb3fec63e3d620879283999db8398c281a3361b17fbb1cb72141cd240e69`.
Frozen rubric v1 SHA-256:
`08308ae486c2085a7dc5723d5b5d0c64558b7d8205a2eb0c67f152f42dbd9ed2`.
The original private manifest fingerprint retained in result files includes local
paths; the public manifest removes those paths and retains portable identities.

Baseline uses the frozen config, real `decode_raw` and `compute_scores`, followed
by group coverage. Learned scoring blocks are disabled. Previews are 1024-pixel
JPEG quality 85; baseline focus is bounded at 2048 pixels. Candidate preview
SHA-256 values exactly match the baseline. Ranking is compared within the 20
published event groups; actual domain grouping is reported separately below.

Two opposite-order Codex proxy panels use `gpt-5.6-sol`, medium reasoning, with
scores/source labels hidden. A has fresh contexts for groups 1–10 and 11–20;
B has contexts for 1–10, 11–16 and a replacement context for 17–20 after a quota
interruption. Contexts are not fresh per group; cross-group calibration drift
remains possible. For group 01, `A011` maps to `g01i1` and `B011` to `g01i5`; B reverses all five frame IDs.
Every completed group must contain five readable IDs and all ten unique pairs.
These are model-generated references, not human ground truth. Order disagreement
must be disclosed before using their preferences to justify a model change.

## Blind reference results and incomplete coverage

Panel A completed 20/20 groups; panel B completed 17/20. Groups 18–20 remain
missing after the replacement agent also returned a usage-limit error. They are
not imputed. Raw panel JSON preserves all completed judgments. Exact preferred-set
agreement is **1/17** overlapping groups; pairwise agreement, including ties,
is **41/170**. Only **7** strict pairwise preferences agree across order, below
the frozen minimum of 30. This unstable proxy cannot support model promotion.

| Scorer | A top-1 preferred | B top-1 preferred | A strict pairs correct | B strict pairs correct | Stable strict correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 6/20 | 2/17 | 50/126 | 25/85 | 1/7 |
| TOPIQ_NR | 3/20 | 4/17 | 60/126 | 43/85 | 5/7 |
| MUSIQ | 5/20 | 4/17 | 67/126 | 44/85 | 4/7 |
| Optional refinement | 5/20 | 2/17 | 49/126 | 25/85 | 1/7 |

Baseline rejects 30/59 panel-A acceptable candidates and 38/62 panel-B acceptable
candidates. It visibly retains 23/52 and 13/37 candidates outside the respective
acceptable sets (review counts as retained). These are proxy disagreements, not
human false-reject estimates. An explicit keep exists in every evaluated event
(20/20 A, 17/17 B). The very different acceptable sets and order preferences
prevent treating group coverage alone as successful culling acceptance.

## Runtime and grouping

The missing-thumbnail RAW hash fallback is implemented in `accad08`. It preserves
existing embedded-preview paths and uses a bounded half-size RAW decode only
when LibRaw reports a missing/unsupported thumbnail. Default grouping now reads
all 100 hashes and produces 21 groups: 19 groups of five and one event split into
one plus four. Event 03 has a real five-hour EXIF discontinuity (09:09:32 versus
14:09:32). Its timestamps were not corrected or fabricated. Hashing/grouping took
7.367 s. Threshold 0 still bypasses all hash decoding.

Within the 20 event groups, baseline selection has 20 keep, 32 review and 48
reject. Full scoring p95 is 0.05289 s; RAW decode p95 is 0.15572 s. Groups 04 and
16 have all-zero scores due to the catastrophic blur guard; group coverage still
retains a selection without changing its quality score. This is policy behavior,
not evidence that those scores accurately reflect photographic intent.

## Isolated candidates

Candidates run independently, without fusion or rejection calibration, in ignored
extra environments. Repository dependencies/defaults are unchanged. Quality runs
use CPU tensors, batch 1 and four Torch threads on Apple M4; these are not Intel
OpenVINO target-hardware results. The frozen budget is warm p95 at most 2 s and
incremental peak RSS at most 2 GiB. Model asset hashes are recorded separately;
the public adapter still reports unknown asset/device readback where unsupported.

| Candidate | Frames | Warm p95 | Incremental peak RSS | Result |
| --- | ---: | ---: | ---: | --- |
| TOPIQ_NR | 100 | 0.390808 s | 1,904,214,016 bytes | Resource budget passes; no promotion |
| MUSIQ | 100 | 0.318034 s | 978,796,544 bytes | Resource budget passes; no promotion |
| MediaPipe 0.10.35 | 100 | 0.005858 s | 357,269,504 bytes | Zero faces; no replacement evidence |

Quality uses PyIQA 0.1.16 / Torch 2.14.0 / torchvision 0.29.0. Model-specific
lifecycle/provenance limitations remain visible in result JSON. MediaPipe uses
the official Face Landmarker task asset, five-face limit and confidence 0.5;
YuNet uses its existing confidence 0.6 and 640-pixel resize path. YuNet detects
five faces, all in event 14; both panels identify a small, hat-shadowed person
there. No annotated landmark truth supports a precision/recall claim. MediaPipe
logs include Metal context initialization and XNNPACK; configured/default CPU is
not a physical execution-device readback. A missed face remains unknown eye
evidence, never poor eyes or inferred back-view/silhouette.

The frozen promotion gate requires at least 30 order-stable strict pairs, a
five-percentage-point pairwise improvement, no top-1 regression, and no increased
false rejection/coverage loss. Raw independent quality scores cannot establish
the last two policy outcomes without a separately calibrated integration.

## Optional focus refinement

The real group finalizer was exercised with opt-in refinement and mocked state
and repository boundaries; no persistence/writer calls occurred. Of 100 frames,
60 were not triggered, 22 retained baseline for no resolution gain, and 18
completed a larger-focus observation. Fourteen numeric scores changed. Total
finalizer time was 3.612 s, group p95 0.294 s, with zero scheduling overruns.
These observations correct the earlier six-fixture finding: some RAWs do gain
resolution. They do not establish better ranking; refinement stays disabled.
There is still no local producer for back-view/silhouette subject context.

## Verification and scope

The hash fallback source batch passed four focused regressions, `make check`,
repository boundary checks and the guarded full suite: **745 passed, 102 skipped**.
Skips include photo/XMP-write paths suppressed by the guard and unavailable
optional integrations. Original input SHA-256 values were rechecked. No push,
deployment, production review or physical metadata writes occurred.

Professional-software round trips and target container recovery have a separate
[reviewable execution plan](../../2026-09-17-external-acceptance-plan.md), awaiting
its required external inputs and write/host authorization. Personal ranker
training still needs genuine preference labels. Fine action discrimination and
exposure-clipped first-frame grouping are not established by these HDR+ bursts.
