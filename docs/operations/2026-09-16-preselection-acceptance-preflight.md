# Preselection acceptance preflight

The controlled Codex diagnostic pilot is now complete after quota restoration:
both independent panels viewed all 12 candidates and agreed with each other and
the default full-scoring baseline on 6/6 controlled pairs. See the
[pilot report](benchmarks/2026-09-16-codex-blind-pilot/report.md). This is not full
real-burst acceptance; the broader input set remains outstanding.

## Frozen reviewer rubric

[Rubric v1](evaluation/preselection-rubric-v1.json) separates observable quality
from group coverage, preserves the user's time/hash grouping rule, permits
uncertainty, requires independent order reversal, and labels proxy judgments
`model_generated`. SHA-256:
`08308ae486c2085a7dc5723d5b5d0c64558b7d8205a2eb0c67f152f42dbd9ed2`.

The full acceptance image set is **not frozen yet**; the diagnostic pilot below
is frozen separately. Do not represent the rubric hash as an image manifest hash. Freeze capture-event splits and image hashes before running the
baseline or revealing labels. Compare the full scoring/selection path, not only
`benchmark-local`'s client-dimension average.

## Verified available inputs and channel

- The existing six public RAWs cover decoder formats, not within-burst human
  preferences. Their alternative half-size RAW decodes have no greater focus
  pixel area than baseline previews. The unchanged source hashes and dimensions
  are in `.local/review-2026-09-16-coverage/raw-refinement.json`.
- Stanford40 supports action classification. It is not a preselection reference.
- Existing synthetic fixtures support deterministic boundary diagnostics only.
- Correction: an external API is not required for proxy review. Codex subagents
  provide an independent visual-review channel with fresh histories. The user
  explicitly requested this route after the initial API-only preflight.
- Dispatched panels A/B with `fork_turns=none`, `gpt-5.6-sol`, medium reasoning,
  neutral candidate IDs and opposite order. Both initially returned usage-limit errors with no judgments. After the user
  restored quota, the same panels completed without a model switch. The earlier request for external API configuration is superseded.
- A diagnostic input set is now frozen: six existing public RAW sources, each
  paired with an in-memory Gaussian-blur variant (12 candidates, six groups).
  Manifest SHA-256:
  `d868bfe64904b7399f3bf3c6aee82cf3bf4c47cf6810b9fa893b894d485bacb7`.
  This is not a real burst holdout or the complete acceptance dataset.
- The checked-in default local heuristic ran through full `compute_scores` and
  group coverage, with no runtime DB or XMP writer. Each group retained the
  unblurred candidate; the completed independent visual panels also selected those candidates.
  No thresholds were tuned.
- Renderer, frozen inputs, baseline, requested model/runtime versions and dispatch
  status are saved under ignored `.local/subagent-blind-review/`. Sources remain
  hash-identical; variants are encoded only in memory. The resumed panels finished before the controller mapped their judgments;
  raw judgments and a sanitized comparison are committed with the pilot report.

## Task-relevant public dataset search

[Photo Triage's official project page](https://pixl.cs.princeton.edu/pubs/Chang_2016_ATF/)
describes 15,545 unedited photos in 5,953 series with within-series human
preferences. This is a better match for ranking acceptance than action labels.
Its linked `phototriage.cs.princeton.edu` download service was inaccessible in
this check: HTTPS returned `SSL_ERROR_SYSCALL`; HTTP returned an empty reply.
No dataset was downloaded, no usage terms were accepted, and no author was
contacted. An accessible official archive or verified permitted copy is needed.

The [BuIQA paper](https://arxiv.org/html/2511.07958v1) distinguishes objective
restoration-frame value from subjective selection quality; its subjective subset
reuses Photo Triage and visually grouped SPAQ images. Thus its restoration labels
must not be treated as human photo preference. No accessible official release was
verified during this preflight. This search is not a claim that none exists.

## Remaining execution

1. The Codex review channel is verified. Obtain a task-relevant real image/reference
   set for full acceptance; the controlled pilot is not a substitute.
2. Freeze a bounded event-disjoint subset and record source/terms, image hashes,
   group parameters and preview version. Do not fabricate capture timestamps.
3. Collect blind judgments and independent reversed-order judgments; preserve raw
   responses and disagreements. Apply the frozen rubric without tuning on holdout.
4. Run the full baseline and report coverage, false rejects, extra keeps,
   preference agreement, abstentions and latency with denominators.
5. Only then evaluate additional model candidates or fusion separately.

Professional-software XMP round trips and target hardware/container restore tests
remain separately unverified and outside this session's write/deployment scope.

## September 17 continuation

The [expanded HDR+ holdout](benchmarks/2026-09-17-hdrplus-holdout/report.md)
contains 20 frozen events/100 frames. A completed 20 groups, B 17; the last three
are blocked by a reported subagent usage limit. Exact preferred sets agree in
1/17 overlapping groups and only seven strict pairs are order-stable. This fails
the frozen minimum evidence gate, so neither model replacement nor refinement
is promoted. Full product acceptance remains incomplete. The separate
[real exposure bracket](benchmarks/2026-09-17-exposure-brackets/report.md) is a
diagnostic counterexample, not additional blind holdout truth.
