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

The local runtime refinement is implemented through benchmarked optional model
blocks, native OpenVINO CPU inference, embedding-assisted grouping, and legacy
backend quarantine. See
`docs/operations/2026-07-11-refine-plan-completion-audit.md` for the
requirement-by-requirement status.

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

## Recommended Next Task

- extend the controlled Unraid safe-read model to expose `/dev/dri` or approve a
  material-agent Intel container deployment plan;
- run CPU/GPU parity and a target-host isolated XMP validation before enabling
  learned score fusion by default;
- collect broader labelled real scenes; the current holdout is interleaved with
  the calibration burst and is not a distribution-independent validation set;
- decide whether the legacy teacher harness remains or copied modules can be
  deleted.
