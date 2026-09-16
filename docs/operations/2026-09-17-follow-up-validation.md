# Follow-up validation, 2026-09-17

## Reviewed implementation

Commit `2c6ec47` makes rewrite dry-run and execution share stored-payload
preparation and projection validation, and retains refinement baseline when
old dimensions or new focus pixels are missing. Three regressions failed before
the fixes. Focused tests: 51 passed, 8 skipped. Full guarded suite: **741 passed,
102 skipped in 19.91 seconds**. Ruff passed. This supersedes earlier test totals
as the latest execution; skips remain outside the photo/XMP-write boundary.

`_subject_context` is accepted in `scoring_engine._merge_backend_meta` and consumed
by `face_eye_evidence`; no current local adapter produces it. Automatic back-view
or silhouette recognition is **not implemented**. Supported `not_applicable` is
a consumer contract. Six new real DNGs through `decode_raw` and full
`compute_scores` returned `unknown` eye evidence, not an invented back-view label.
No remote VLM or context model was enabled. These samples do not establish a
portrait-specific end-to-end acceptance result.

## Bounded source investigation and new evaluation

- [Photo Triage official publication](https://pixl.cs.princeton.edu/pubs/Chang_2016_ATF/)
  still links its benchmark host. Retried its download endpoint with a 10-second
  timeout: TLS `SSL_ERROR_SYSCALL`; no data downloaded from that host.
- [HDR+ official dataset](https://www.hdrplusdata.org/dataset.html) offers anonymous
  Google Cloud downloads and explicitly links [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  Credit: Samuel W. Hasinoff and colleagues, *Burst photography for high dynamic
  range and low-light imaging on mobile cameras*, SIGGRAPH Asia 2016.
- Selected the first two event directories in the official curated-subset listing
  and first three input frames per event, before scoring. Download ceiling was
  250 MB, request timeout 45 seconds, concurrency three. Actual download:
  **6 DNGs, 41,162,484 bytes**. Cloud MD5 and local SHA-256 verified; unchanged
  hashes verified again after evaluation. No full dataset download was attempted.

Events `0006_20160722_115157_431` and `0006_20160727_185921_651` are new to this
session's evaluations. They were not used for tuning. All event frames remain
in evaluation; no frame-level train/test split was made. The original rubric v1
was retained. This two-event subset is much smaller than its 20–40 group target.
The curated subset is described as generally good technical quality, so it is
unsuitable for establishing all-low-quality coverage by itself.

Artifacts: [manifest](benchmarks/2026-09-17-hdrplus-burst/manifest.json),
[baseline](benchmarks/2026-09-17-hdrplus-burst/baseline.json),
[configuration](benchmarks/2026-09-17-hdrplus-burst/config.json),
[panel A](benchmarks/2026-09-17-hdrplus-burst/panel-a.json),
[panel B](benchmarks/2026-09-17-hdrplus-burst/panel-b.json),
[comparison](benchmarks/2026-09-17-hdrplus-burst/comparison.json).
Source media remain ignored under `.local/hdrplus-evaluation/`; no media is
redistributed in Git. Read-only evaluation script and raw grouping/time receipts
are retained there. Previews use the frozen config's decode/JPEG transform and
are hashed in baseline evidence; no artificial blur was applied.

## Grouping and scoring are separate results

The real `Grouper.group` path used original EXIF times without fabrication:
2016-07-22 11:51:58 for event 1 and 2016-07-27 18:59:22 for event 2. Within each
event all three DNGs have the same original second and subsecond field; these
fields cannot establish actual inter-frame timing below that resolution.

At time gap 30 seconds / hash threshold 10, grouping produced **six singletons**.
All six input DNGs raise `LibRawNoThumbnailError`; the current hash reader has no
RAW-postprocess fallback, returns no hash, and correctly fails closed under its
missing-evidence rule. At hash threshold 0 it produced **two groups of three**.
This is a documented format-coverage limitation, not successful default grouping
acceptance. A bounded thumbnail-free RAW hash fallback needs its own performance,
cache and parity review; no threshold was relaxed to hide this limitation.

Scoring/selection evaluation used the dataset's two event groups explicitly,
independently of the failed hash observation. Full checked-in default local
scoring produced [6.25, 6.25, 6.25] and [6.97, 6.97, 6.97]. Each group retained
one explicit coverage keep and two review candidates. Scores were not inflated;
no candidate was rejected. Default optional model blocks remain disabled.

## Independent reversed-order visual review

Two fresh-context `gpt-5.6-sol` / medium Codex subagents inspected all six previews,
one in forward order and one reversed, with separate neutral IDs. They received
no system scores, source names, other-panel answers, or script source. Each
reported successful rendering of all six images. These are **model_generated**
proxy references, not human preferences or independent model families.

Both panels considered all three candidates in each event acceptable and tied
for preferred. All six pairwise comparisons per panel were ties. Preferred-set
agreement under order reversal is 2/2; system top-1 lies in both panels' preferred
sets for 2/2 groups. All six previews have distinct hashes. This demonstrates
preview-level indistinguishability rather than duplicated inputs. Strict
pairwise preference accuracy has no denominator here and must not be reported
as 100%. No quality-improvement or model-promotion claim follows.

## Remaining minimum evidence

- At least 18 more new event groups to reach the rubric's lower group target,
  including observable quality/moment differences and real all-low-quality,
  back-view/silhouette, multiple-person, small-face and occlusion cases.
- Thumbnail-free RAW hash extraction before using these DNGs as positive default
  grouping acceptance. Keep missing hashes conservative until that is verified.
- An actual local context producer and separate frozen context benchmark before
  claiming automatic back-view/silhouette applicability.
- Optional refinement remains disabled until quality and latency gains are shown.
- Professional-software round trips: proposed isolated copies, imported rating
  and keyword snapshots, application projection, software save/readback and
  original-hash verification. Await distinct actual-write authorization.
- Container recovery: proposed disposable appdata copy, restart/restore, schema
  and job-resumption checks with read-only media. Target-host execution requires
  separate authorization. Neither external plan has been executed.

Local review/fix commits only. No push, deployment, production review, private-host
operation, source-image modification or XMP write occurred.
