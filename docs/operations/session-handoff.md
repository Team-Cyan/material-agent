# Session Handoff

## Repository State

- local repository: `/Users/lancer/projects/material-agent`
- AI knowledge base: `docs/ai/`
- agent asset layer: `.agents/`

## Durable Knowledge Already Recorded

- `AGENTS.md`
- `.agents/codex.md`
- `.agents/harness-engineering.md`
- `docs/ai/project-overview.md`
- `docs/ai/harness-workflow.md`
- `docs/roadmap.md`

## Current Focus

The local runtime refinement, whole-project hardening, Web operations surface,
and first complete 40,620-file target-host validation are implemented. The
remaining gates are deliberately limited to human preference labels/personal
calibration and separately authorized XMP promotion. See
`docs/operations/2026-07-11-refine-plan-completion-audit.md` for the
original requirement-by-requirement status and
`docs/operations/2026-07-13-whole-project-review-fixes.md` for the latest
findings, repair plan, and verification boundary.

## 2026-07-30 Review And Candidate Verification

- the whole repository review hardened transient EXIF failure caching, bounded
  SQLite cache reads, complete model-bundle cache identity, private Web runtime
  files, Web/container path agreement, configuration failure cleanup, OMLX
  symlink boundaries, and XMP parsing/write concurrency;
- local verification passes 704 tests; six live OMLX integration tests remain
  opt-in through `PIXEL_JUDGE_RUN_OMLX_TESTS=1`;
- the current Unraid DockerMan container still uses immutable image
  `intel-openvino-47fb49e` and is stopped (`Exited (137)`); this review did not
  restart it, replace it, change its template, or publish an image;
- candidate source `47fb49ed1c7a+tree.7370e5c8b2ed` was overlaid read-only on
  that existing image in a networkless, read-only, capability-free one-shot
  container; 600 real RAW EXIF reads, 1,901-path SQLite batching, XMP
  preservation/fail-closed/concurrent-update checks, model companion identity,
  Web private modes, configuration, entrypoint syntax, and OMLX symlink
  isolation all passed;
- the candidate run left source XMP at `0 -> 0` and production-state file count
  at `31 -> 31`; the ephemeral container was removed, and the subsequent
  DockerMan audit reported 13 containers, 9 templates, and zero issues.

## Real-Camera Pilot Snapshot

- private fixtures: five calibration and five holdout Sony A7C II ARWs from one
  concert burst;
- benchmark RAW decoding uses embedded previews and leaves both source
  directories unchanged;
- a concert-specific MobileCLIP2 prompt transfers from calibration 5/5 to
  holdout 5/5 without regressing the maintained synthetic 4/4 scene gate;
- DINOv2 grouping evidence is positive, while MediaPipe face detection is 0/10
  on the small/occluded stage faces and must remain non-default;
- an isolated copy of all five holdout files passed dry-run and real XMP writes,
  with source hashes unchanged and no source-side XMP creation.

## Unraid Read-Only Pilot Snapshot

- the pre-hardening bounded pilot exposed `/dev/dri`, and all ten embedding
  payloads reported actual OpenVINO execution on `GPU.0`;
- `/mnt/user/material/photos` was mounted read-only, dry-run wrote zero XMP files
  and zero source-side `.material-agent` directories, and SQLite/logs stayed in
  the `/config` appdata bind;
- the hardened 128-RAW cold/warm matrix measured CPU at 6.737 warm
  files/second and `GPU.0` at 0.496 across batch 1/4/8; actual batch 4/8 and
  zero fallback were recorded, but did not improve either device;
- the winning CPU batch-1 profile processed 512 RAW files in 88 seconds with
  512 embeddings, zero errors, zero XMP writes, and appdata-only DB/log/cache;
- the hardened Intel image now bakes the DINOv3 profile, drops scoring to the
  PUID/PGID account, migrates only allowlisted appdata files, and tests both
  OpenVINO AUTO selection and explicit CPU fallback before tag promotion.

## Recommended Next Task

- decide separately whether to publish this verified candidate and perform an
  authorized DockerMan image update/start; source-overlay verification is not a
  production deployment;
- use the Web library/detail views for optional human outlier review when the
  service is deliberately restored and the user is ready to provide real
  preference evidence.

## Web Operations Snapshot

- the Web operator is deployed on Unraid as immutable image
  `ghcr.io/team-cyan/material-agent:intel-openvino-47fb49e` at port `8776`, but
  the container is currently stopped;
- the generation-based index contains 40,620 files from
  `/mnt/user/material/photos`, all with current score records and zero errors;
- `material-agent web` serves configuration, task, model, library, thumbnail,
  score payload, and log APIs plus the bundled responsive operator UI;
- the maintained Unraid Web listener is intentionally unauthenticated on the
  trusted LAN; port `8776` must not be forwarded to the Internet;
- Web tasks are hard-coded to `--dry-run`, and the photo root is only used for
  scanning and thumbnail decode;
- `library_index` and complete dry-run score artifacts live in `/config/state.db`;
- a post-deployment one-file run verified DB-only proposed rating, machine tags,
  instructions, description, grouping metadata, SSD target detection, YuNet
  face/eye focus, and generic NIMA output; `/photos` remained read-only with
  zero source XMP files and zero source-side state directories;
- configuration updates are validated before atomic replacement and preserve
  redacted secret values;
- the module guide is `docs/ai/modules/web-operations.md`.

## Full-Library Closure Snapshot

- task `8be6f3270f1d495289b3465e68609965` and job
  `7a01c08bff4441c7abcd014107f3e5cc` finished successfully on 2026-07-16;
- 40,620/40,620 files scored, zero errors, zero writes, and 40,620 simulated
  dry-run outputs were persisted in the appdata runtime DB;
- end-to-end elapsed time was 5,683 seconds: 7.148 files/second and 0.14
  seconds/file;
- scenes were people 21,250, other 16,964, animals 1,724, detail 551, and
  sports 131; the most common detected target was person at 19,920;
- NIMA executed on actual OpenVINO CPU with no application fallback, 1,197
  inference runs, and the checksum-pinned model digest; personal target
  calibration remained an intentional no-op because no human profile exists;
- `/photos` remained read-only, source XMP and source state-directory counts
  remained zero, and `/config/state.db` plus `/config/run.log` remained in
  appdata;
- the first post-import run exposed 1,455 unreadable files because rsync had
  preserved Mac `0700/gid20` metadata. The bounded import receipt was used to
  set `gid=users` plus group-read access for exactly those files; a non-root
  rawpy probe and the complete rerun proved the repair.

## NIMA Device And Operations Snapshot

- the same bundled NIMA graph was benchmarked on the target Unraid i7-11700T at
  CPU and `GPU.0`, batch 1/4/8, with 128 RAW files and repeated warm passes;
- OpenVINO execution-device readback confirmed both CPU and `GPU.0` profiles
  with zero application fallback; a benchmark-only `PERFMON` capability was
  required for Intel PMU sampling and is not part of the production profile;
- run-to-run variation was larger than the small CPU/GPU warm-throughput gap,
  while GPU cold start and peak RSS were materially higher, so production stays
  on the simpler CPU batch-1 profile without `/dev/dri`;
- model artifacts can now be listed, installed, selected, and deleted through
  the CLI or the primary Web service. Bundled immutable assets are never
  physically removed, while downloaded assets live under `/config/models`;
- human aesthetic labels live under an appdata SQLite store with train/holdout
  splits. No personal target calibration was fitted because no genuine labels
  were supplied; this is intentionally deferred rather than replaced with
  generated labels.

## Target Aesthetic Calibration Boundary

The runtime now supports label-backed exact-object/scene NIMA calibration and
persists raw plus effective scores. No non-identity production profile has been
fitted because the available five-file calibration/holdout sets and existing
`mj:score` XMP values are generated evidence, not human aesthetic ground truth.
Use `docs/operations/aesthetic-target-calibration.md` to collect and fit real
labels before promotion. Subject-crop NIMA remains an evidence-gated ablation.
