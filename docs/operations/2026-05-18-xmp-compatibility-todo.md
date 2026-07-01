# XMP Compatibility Todo

This note turns the May 2026 XMP compatibility research report into repo-local follow-up work.

## Done In Current Pass

- Confirmed that `score_to_stars()` already uses `int(score / 2 + 0.5)`, matching the SQLite star-rating rule.
- Confirmed new sidecars already use `dc:description` as `rdf:Alt` with `x-default`.
- Added lifecycle metadata to newly generated sidecars:
  - `xmp:CreatorTool`
  - `xmp:MetadataDate`
  - `xmp:ModifyDate`
  - `xmpMM:DocumentID`
  - `xmpMM:InstanceID`
- Updated existing-sidecar ExifTool writes to target `XMP-dc:Description-x-default` explicitly.
- Updated existing-sidecar ExifTool writes to target `XMP-photoshop:Instructions` explicitly.
- Updated reset/clear behavior to clear `xmp:Rating`, `photoshop:Instructions`, and `dc:Description-x-default` through explicit namespaces.
- Kept current `pj:*` subject tags unchanged to avoid breaking existing rewrite and reset flows.

## Short-Term Todo

- Add golden XMP fixtures for new sidecars and rewrite output.
- Add an ExifTool round-trip smoke test that reads back rating, creator tool, instructions, description, subject tags, metadata dates, and XMPMM IDs.
- Decide whether existing sidecar updates should preserve, create, or migrate `xmpMM:DocumentID`.
- Replace `RewriteXmpService` direct calls into writer private helpers with a public writer method when the serializer boundary is clarified.
- Build a small manual compatibility checklist for Adobe Bridge/Lightroom and Photomator before claiming software-level compatibility.

## Mid-Term Todo

- Introduce explicit export profiles:
  - `interop-core`: rating, label when available, clean keywords, x-default description, lifecycle metadata.
  - `adobe-rich`: interop core plus Adobe-friendly instructions/details.
  - `judge-rich`: interop core plus authoritative material-agent machine fields.
- Move authoritative machine metadata out of `dc:subject` into a documented custom namespace.
- Keep only intentional human-readable mirror tags in `dc:subject`.
- Add a compatibility matrix with real software versions and sample RAW formats (`CR2`, `NEF`, `ARW`, `DNG`).

## Deferred

- Do not treat DaVinci Resolve sidecar behavior as guaranteed until it is tested in the real app.
- Do not add embedded metadata writes for DNG/JPEG/HEIC until sidecar profile behavior is stable.
- Do not rename `pj:*` tags in the current pipeline without a migration plan for existing sidecars and SQLite-driven rewrite flows.
