# Preselection acceptance preflight

This is a readiness report, not a GPT acceptance result. No images were sent to
a remote model and no evaluation accuracy is claimed.

## Frozen reviewer rubric

[Rubric v1](evaluation/preselection-rubric-v1.json) separates observable quality
from group coverage, preserves the user's time/hash grouping rule, permits
uncertainty, requires independent order reversal, and labels proxy judgments
`model_generated`. SHA-256:
`08308ae486c2085a7dc5723d5b5d0c64558b7d8205a2eb0c67f152f42dbd9ed2`.

The input set is **not frozen yet**. Do not represent the rubric hash as an image
manifest hash. Freeze capture-event splits and image hashes before running the
baseline or revealing labels. Compare the full scoring/selection path, not only
`benchmark-local`'s client-dimension average.

## Verified available inputs and channel

- The existing six public RAWs cover decoder formats, not within-burst human
  preferences. Their alternative half-size RAW decodes have no greater focus
  pixel area than baseline previews. The unchanged source hashes and dimensions
  are in `.local/review-2026-09-16-coverage/raw-refinement.json`.
- Stanford40 supports action classification. It is not a preselection reference.
- Existing synthetic fixtures support deterministic boundary diagnostics only.
- No independent model-completion connector was available. Standard OpenAI,
  Azure and OpenRouter credential environment variables were absent; no project
  `.env` files were present. The five ignored experiment config files use the
  local backend and expose no GPT provider section. No credentials were printed.
- The user has been asked for the location of an existing independent review API
  configuration, not for repeated authorization to evaluate images.

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

1. Obtain a usable image-review channel and a task-relevant image/reference set.
2. Freeze a bounded event-disjoint subset and record source/terms, image hashes,
   group parameters and preview version. Do not fabricate capture timestamps.
3. Collect blind judgments and independent reversed-order judgments; preserve raw
   responses and disagreements. Apply the frozen rubric without tuning on holdout.
4. Run the full baseline and report coverage, false rejects, extra keeps,
   preference agreement, abstentions and latency with denominators.
5. Only then evaluate additional model candidates or fusion separately.

Professional-software XMP round trips and target hardware/container restore tests
remain separately unverified and outside this session's write/deployment scope.
