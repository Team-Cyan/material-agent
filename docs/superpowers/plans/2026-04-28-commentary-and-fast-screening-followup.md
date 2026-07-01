# Commentary And Fast-Screening Follow-Up

Date: 2026-04-28
Repo: `material-agent`
Status: proposed for review

## Goal

Improve two things without destabilizing the core scoring path:

1. keep `fast-screening` disabled by default for now, but make the recovery path explicit and testable
2. make `commentary` read more like a photographer's per-photo critique instead of a small set of repeated technical templates

## What We Observed

### 1. Core scoring looks broadly usable

From the current runtime database at `/Users/lancer/materials/photos/.material-agent/state.db`:

- processed rows: about `40k`
- average `total_score`: about `6.04`
- decisions are distributed across `review`, `reject`, and a smaller `keep` bucket
- scene mix is dominated by `people`, with meaningful `animals`, `landscape`, `detail`, `city`, and `indoor` coverage

This does not look like a scoring-contract emergency. The score distribution is broad enough that we should not start by retuning weights or thresholds.

### 2. Commentary repetition is still high

Top repeated `commentary_post` strings occur hundreds of times:

- multiple variants of `这张先从锐度和清晰下手...`
- multiple variants of `锐化只做轻量补偿...`
- multiple variants of `轻压背景亮度或反差...`

Top repeated `commentary_group_issues` strings also occur at very high frequency:

- `锐度和清晰度普遍偏弱，影响主体表现力`
- `锐度和层次普遍偏弱，影响主体表现力`

This means the current implementation is better than a broken pipeline, but still not yet at the level of "photographer-style per-photo critique."

### 3. Fast-screening should stay off by default

The previous helper-Python path was intentionally removed. That was the right direction for machine hygiene.

What remains to improve is not "bring back a second Python." It is:

- make the off-by-default state explicit and quiet
- preserve a clean re-enable path under the one allowed Python stack: project env + Homebrew Python 3.14

## Proposed Plan

### Phase 1: Commentary audit tooling first

Goal: make repetition measurable before changing wording logic again.

Changes:

- add a small repo-local audit command or script that summarizes:
  - top repeated `commentary_post`
  - top repeated `commentary_group_issues`
  - repetition ratio by scene
  - repetition ratio by decision bucket
  - representative examples for high-score, mid-score, and low-score rows
- keep it read-only against `processed` SQLite data

Why first:

- right now we can see repetition exists, but the feedback loop still depends on ad hoc SQL snippets
- this should become the default review tool before touching prompts or fallback logic

Likely files:

- `src/material_agent/commands/`
- `src/material_agent/app/`
- maybe `docs/harness-runbook.md` if the command becomes part of the recommended workflow

Acceptance:

- a single command can generate a compact repetition report from an existing run DB

### Phase 2: Make post commentary more photo-specific

Goal: reduce the "same three repair sentences in different order" effect.

Changes:

- strengthen `regenerate_post_commentary()` in `src/material_agent/domain/commentary.py`
- move from generic dim-pair phrasing toward photo-context phrasing:
  - distinguish `detail` from `stage` from `animals` from `city night`
  - use `scene_raw`, `decision`, `group_rank`, and `visible_breakdown` more aggressively
  - make "what to protect" more concrete than `主体边缘`
- explicitly reduce phrase families that still dominate:
  - `锐度和清晰`
  - `锐化只做轻量补偿`
  - `轻压背景亮度或反差`

Desired output behavior:

- comments should still be concise
- but they should sound like they were written after looking at this frame, not selected from a tiny sentence library

Acceptance:

- top repeated `commentary_post` frequency drops materially on a rewrite sample
- sample outputs across one scene cluster no longer read like simple sentence permutations

### Phase 3: Make group commentary less generic

Goal: stop collapsing many groups into the same `锐度/清晰/层次普遍偏弱` diagnosis.

Changes:

- strengthen `regenerate_group_commentary()` so it:
  - uses group scene mix and decision mix more explicitly
  - varies the framing of the dominant failure mode
  - references whether the group problem is timing, subject readability, light placement, clutter, or texture/detail loss
- keep the output short and compatible with current XMP / DB shape

Acceptance:

- top repeated `commentary_group_issues` frequency drops materially
- stage groups, detail groups, and animal groups stop sounding like one generic rule with only score numbers changed

### Phase 4: Add a safe rewrite workflow for existing runs

Goal: make commentary improvements usable on already-processed material.

Changes:

- keep using `rewrite-commentary`
- add a documented audit-before / rewrite / audit-after loop
- optionally add a narrow-scene or narrow-date filter later if needed, but not in the first pass

Acceptance:

- we can run a dry-run commentary rewrite on a real directory and see how many rows would change
- after rewrite, repetition metrics clearly improve on the same DB

### Phase 5: Keep fast-screening off, but make recovery explicit

Goal: preserve machine cleanliness while keeping the feature repairable.

Changes:

- leave `screening.enabled: false` as the default
- document the expected recovery contract:
  - one Python stack only
  - current project env only
  - no helper venv
- add a small readiness check for MUSIQ dependencies when screening is explicitly enabled
- make failure mode quiet and actionable rather than noisy and repetitive

Acceptance:

- default runs do not spam screening warnings
- enabling screening gives one clear dependency/readiness failure, not per-file noise
- no second Python install path is reintroduced

## Priority Order

Recommended order:

1. commentary audit tooling
2. post commentary specificity
3. group commentary specificity
4. rewrite workflow on existing DB outputs
5. fast-screening recovery/readiness cleanup

## What We Should Not Touch First

- scoring weights
- layered decision thresholds
- scene taxonomy
- benchmark contract modes
- broad runtime changes

Those may be worth revisiting later, but the current evidence says commentary quality is the highest-leverage problem.

## Review Questions

Please review these choices first:

1. Should we keep the first pass strictly limited to commentary plus screening-readiness, with no score-contract tuning at all?
2. For existing processed photos, do you want the follow-up path to optimize for:
   - better future runs first
   - or batch-rewrite current commentary as soon as quality is improved?
3. Do you want the audit command/report to live as:
   - a normal CLI command in `material-agent`
   - or a lighter internal-only script first?
