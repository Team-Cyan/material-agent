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

The local runtime refinement and whole-project hardening pass are implemented
through benchmarked optional model blocks, native OpenVINO inference,
provenance-safe resumability, stable incremental grouping, non-root Intel
deployment, and legacy backend quarantine. See
`docs/operations/2026-07-11-refine-plan-completion-audit.md` for the
original requirement-by-requirement status and
`docs/operations/2026-07-13-whole-project-review-fixes.md` for the latest
findings, repair plan, and verification boundary.

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
- a single cold ten-file end-to-end comparison measured about 28 seconds on CPU
  and 43 seconds on GPU. This is not warm parity or utilization evidence;
- the hardened Intel image now bakes the DINOv3 profile, drops scoring to the
  PUID/PGID account, migrates only allowlisted appdata files, and tests both
  OpenVINO AUTO selection and explicit CPU fallback before tag promotion.

## Recommended Next Task

- after immutable-image CI passes, redeploy that exact digest to the controlled
  Unraid container and repeat the ten-file read-only/dry-run audit, including
  non-root UID/GID, appdata ownership/modes, actual device provenance, and zero
  source writes;
- run warm CPU/GPU parity plus target-host utilization measurement, then perform
  target-host isolated XMP validation only with separate operator approval;
- collect broader labelled real scenes; the current holdout is interleaved with
  the calibration burst and is not a distribution-independent validation set;
- decide whether the legacy teacher harness remains or copied modules can be
  deleted.
