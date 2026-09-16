# XMP Writer Module Contract

## Purpose

This module translates review results into Adobe-compatible XMP sidecar updates
while preserving user-authored metadata when possible.

## Main Files

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- `tests/test_writer.py`

## Responsibilities

- map score totals to star ratings
- build deterministic `pj:*` machine tags
- preserve non-machine subject tags already stored in XMP
- write standard `xmp:Rating`, Photoshop instructions, `x-default`
  description, creator/lifecycle fields, XMP document IDs, clean user keywords,
  and machine identifiers
- update an existing `.xmp` or `.XMP` sidecar instead of creating a duplicate
- support full XMP regeneration through rewrite flows
- support provenance-safe AI reset: preserve XMP by default, remove machine
  tags explicitly, and clear scalar fields only when they still equal the last
  AI-owned values stored in SQLite

## Non-Goals

- deciding scores or ranks
- commentary policy
- CLI parser behavior
- SQLite runtime event emission
- direct proprietary RAW file metadata mutation

## Inputs

- file path
- star rating
- generated subject tags
- score/instruction summary
- combined commentary text

## Outputs

- updated or newly created `.xmp` sidecar files

## Invariants

- material-agent emits integer ratings in the inclusive `0..5` range; five
  stars is a valid AI result and must not be reserved for human-only use
- non-machine subject tags should be preserved whenever readable
- generated `pj:*` tags should be deterministic for the same score payload
- generated `pj:*` tags should be stored in `xmp:Identifier`, not normal
  `dc:subject` keywords, so DAM apps do not show machine data as user keywords
- `dc:subject` preserves user keywords and projects exactly one of
  `material-agent:keep` / `material-agent:reject` when a recognized decision
  is present; `review` projects conservatively to keep. Only these two exact
  keywords are replaced; similarly prefixed human keywords are preserved.
- new sidecars should write `dc:description` as `rdf:Alt` with `xml:lang="x-default"`
- new sidecars should include `xmp:CreatorTool`, `xmp:MetadataDate`, `xmp:ModifyDate`, `xmpMM:DocumentID`, and `xmpMM:InstanceID`
- new sidecars should write a standard XMP packet header and an explicit
  `xmp:Rating` element
- existing sidecar updates should write descriptions through the explicit `x-default` language alternative
- existing sidecar updates should write `photoshop:Instructions` through the explicit Photoshop namespace
- existing sidecar updates should clear stale `pj:*` data from `dc:subject`
  while preserving non-machine user keywords
- existing sidecar updates and rewrites must preserve unrelated namespaces and
  fields instead of rebuilding the whole document from the known field subset
- malformed existing XMP must fail closed before any metadata write; an
  unreadable preservation source is never treated as an empty tag set
- XMP parsing is byte-bounded and rejects DTD/entity declarations before XML
  parsing, so an imported sidecar cannot trigger entity expansion or unbounded
  memory use
- rewrite dry-runs must parse every existing preservation source, so malformed
  XMP fails during preflight instead of only during a real write
- ordinary write-back, AI cleanup, and rewrite must modify a same-directory
  temporary copy, compare the sidecar identity immediately before replacement,
  and refuse to overwrite a sidecar created or changed after the operation began
- existing symbolic-link sidecars are rejected rather than atomically replacing
  the link itself and silently changing its ownership semantics
- Ordinary updates and rewrites fill only a missing or explicit zero rating.
  All nonzero ratings, including previous AI values and external -1, are left
  untouched. Empty, malformed, nested or duplicate ratings fail closed before
  invoking ExifTool; rewrite dry-run validates this policy too.
- Successful ordinary writes return a projection receipt with requested/effective
  rating and written/preserved status. Review persistence stores this separately
  from the AI score and omits preserved ratings from AI-owned scalar fields.
  This does not infer human authorship from an existing nonzero rating.
- XMP output must stay compatible with ExifTool writes and rewrite flows
- `reset-ai` must not touch XMP unless the operator passes `--clear-xmp`
- legacy processed rows without an owned XMP payload may clear deterministic
  machine tags but must preserve rating, instructions, and description

## Projection snapshots and attempt ledger

`preview_projection` reads current sidecar policy fields and returns a versioned
plan without writes. Each rating/keyword/instructions/description record separates
`imported`, `requested`, `planned`, `effective`, `status`, `reason`, and conflict
facts. Imported authorship is always `unknown`; existing ratings are not human
training labels. A dry-run review exposes this record in its score artifact.

Public atomic review and rewrite writers return `committed` receipts only after
replacement succeeds. Preserved nonzero ratings are `skipped`; generated fields
are `written`. A failed operation records `failed` fields with unknown effective
values, since a concurrent editor may have changed the source. Planned values are
never represented as successful writes. Files are atomic, while batches may have
mixed successful and failed receipts.

`xmp_projection_ledger` stores append-only attempt snapshots independently of
processed rows, so later `mark_error` does not erase write history. Successful
rewrite also updates latest projection metadata and scalar ownership, excluding
preserved ratings. If the filesystem commit succeeds but persistence fails, that
is a persistence error, not a failed filesystem write. Recovery after a process
crash between filesystem replacement and database persistence is not transactional.
The ledger covers projection attempts, not an automatic external-app change watcher.

## Typical Safe Changes

- add one more generated `pj:` tag
- improve preservation of existing user metadata
- adjust how instructions or descriptions are assembled
- improve error messaging around write failures

## Risky Changes

- changing XML structure without checking existing readers
- removing preservation behavior for user keywords
- depending on ExifTool behavior that differs between updating an existing file and creating a new file
- writing ratings directly into proprietary RAW files; use sidecars unless a
  format-specific, opt-in, verified writeback path exists
- treating the existence of a processed row as proof that current user-visible
  scalar XMP values are still owned by the application

## Files Usually Safe To Edit Together

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- `tests/test_writer.py`

## Minimal Verification

- `pytest tests/test_writer.py tests/test_state.py`

## Known Tensions / Technical Debt

- The writer currently uses both ExifTool writes and direct XML generation, which means there are effectively two write paths to keep aligned.
- `RewriteXmpService` reaches into writer internals such as
  `_read_non_pj_subject_tags()` and `_write_minimal_xmp()`, which is practical
  but leaky.
- Description formatting is assembled in runtime wiring rather than owned entirely by the writer boundary.
- New sidecars now include creator/lifecycle metadata and XMPMM IDs, but the existing-file ExifTool update path intentionally avoids overwriting `xmpMM:DocumentID` until a preservation/migration policy exists.
- `pj:*` machine data now lives in `xmp:Identifier`. This avoids polluting
  user keyword lists but still keeps deterministic machine tags in a standard
  XMP Basic bag readable by ExifTool.
- Capture One can consume the standard rating and keyword fields, but whether
  its two-way metadata sync preserves `xmp:Identifier` and unrelated XMP
  fields remains fixture-matrix evidence rather than an assumed guarantee.
- A Capture One human-rating round trip needs separate AI and effective-rating
  ownership. The current writer can preserve user-modified scalar fields during
  explicit AI reset. Ordinary review/rewrite now protect nonzero ratings and
  project visible selection keywords, with in-memory compatibility checks.
  Projection-attempt import/write receipts are locally tested; real software
  round trips remain unverified.
- DaVinci Resolve compatibility is not guaranteed by this module. The target is
  standards-based XMP that common DAM/photo tools can read; Resolve should be
  verified with a real fixture matrix before claiming support.

## Current verification boundary

The 2026-09-16 projection slice is verified with in-memory XML and intercepted
ExifTool commands, without writing XMP or source media. See
[full-plan status](../../operations/2026-09-16-plan-status.md). These tests do not
replace an authorized physical sidecar or professional-software round trip.

Rewrite preflight and execution share side-effect-free stored-payload preparation
and projection validation. A malformed row counts as an error and does not stop
subsequent rows. Dry-run does not write a projection ledger receipt or sidecar;
filesystem changes after preflight can still cause execution to fail.
