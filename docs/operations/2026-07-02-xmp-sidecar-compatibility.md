# XMP Sidecar Compatibility Review - 2026-07-02

This note records the RAW rating writeback decision for `material-agent`.

## Decision

Default writeback must remain sidecar-only for proprietary RAW files.

Do not write star ratings directly into ARW/CR3/NEF/RAF/ORF/RW2 files in the
default NAS batch path. Direct RAW mutation is format-specific, harder to
recover from, and conflicts with the non-destructive convention used by major
RAW culling/editing tools.

Embedded RAW star rating is still technically plausible as a separate
rating-only, opt-in mode. It must write only the standard `XMP-xmp:Rating`
field, must keep ExifTool's original-file backup by default, and must pass a
format-specific fixture matrix before it is exposed as anything beyond
experimental.

## Sources Checked

- Adobe Lightroom Classic documents automatic and manual metadata saves to
  external sidecar files, and describes XMP sidecars as the normal metadata
  storage path for RAW workflows:
  https://helpx.adobe.com/lightroom-classic/help/create-xmp-acr-files.html
- ExifTool documents XMP as XML/RDF metadata and recommends standard schemas
  such as `dc` and `xmp` where possible. It also documents explicit
  namespace writes such as `XMP-dc:Description-x-default`:
  https://exiftool.org/TagNames/XMP.html
- ExifTool's supported-file table marks many proprietary RAW formats as
  writable, including Sony ARW/ARQ, Canon CR2/CR3, Nikon NEF/NRW, Olympus
  ORF/ORI, Pentax PEF, Fuji RAF, Panasonic RW2/RWL, Sony SR2, and Samsung SRW:
  https://exiftool.org/
- ExifTool documents `XMP-xmp:Rating` as a writable XMP Basic field with values
  `0..5`, or `-1` for rejected:
  https://exiftool.sourceforge.net/TagNames/XMP.html
- ExifTool application documentation says assigning tag values rewrites the file
  and preserves the original as `_original` by default:
  https://metacpan.org/dist/Image-ExifTool/view/exiftool
- Phil Harvey notes that ExifTool should be fairly robust writing DNG files,
  while still acknowledging spec-version risk:
  https://exiftool.org/forum/index.php?topic=13582.0
- Photomator documents importing Lightroom/Lightroom Classic and Capture One
  ratings from `.XMP` sidecars for read-only RAW formats, requiring the RAW and
  corresponding sidecar to be imported together:
  https://support.pixelmator.com/faq-photomator/advanced-workflows/importing-flags-and-ratings-from-other-apps-into-photomator
- FastRawViewer states that it never modifies RAW files and stores
  rating/label data in same-name sidecar XMP files for compatibility:
  https://www.fastrawviewer.com/node/1026
- FastRawViewer's XMP metadata manual documents `.xmp` / `.XMP` sidecar lookup
  behavior and sidecar naming concerns on case-sensitive filesystems:
  https://www.fastrawviewer.com/usermanual17/xmp-metadata
- FastRawViewer also reads embedded XMP blocks from RAW formats where such XMP
  blocks exist, mainly DNG and some other formats, but records manual changes
  to sidecar XMP files by default:
  https://www.fastrawviewer.com/usermanual17/xmp-metadata

No equally strong official DaVinci Resolve source was found proving that
Resolve will import RAW photo star ratings from external XMP sidecars. Treat
Resolve as a fixture-matrix target, not a guaranteed consumer, until tested
with actual Resolve media-pool imports.

## Compatibility Profile

New sidecars should use a minimal Adobe-compatible XMP packet:

- `xmp:Rating` as the user-visible star rating.
- `dc:description` as `rdf:Alt` with `xml:lang="x-default"`.
- `photoshop:Instructions` for compact score text.
- `xmp:CreatorTool`, `xmp:MetadataDate`, and `xmp:ModifyDate`.
- `xmpMM:DocumentID` and `xmpMM:InstanceID` for new sidecars.
- `dc:subject` only for preserved user keywords.
- `xmp:Identifier` for generated `pj:*` machine tags.

Existing sidecars should be updated in place with explicit ExifTool namespace
tags:

- `XMP-xmp:Rating`
- `XMP-photoshop:Instructions`
- `XMP-dc:Description-x-default`
- `XMP-dc:Subject`
- `XMP-xmp:Identifier`
- `XMP-lr:HierarchicalSubject`

## Embedded RAW Rating-Only Research

The only embedded RAW write candidate is:

```bash
exiftool -P -XMP-xmp:Rating=4 FILE.ARW
```

Rules:

- Do not pass `-overwrite_original` in default or experimental mode. Keep the
  ExifTool `_original` backup until the file opens in target applications.
- Do not write generated comments, scores, keywords, `pj:*` identifiers,
  Lightroom hierarchy, labels, descriptions, or processing settings into the
  RAW.
- Do not combine embedded RAW rating writes with sidecar regeneration in the
  same filesystem transaction. A failure in either path must not leave the
  operator unsure which file contains the source of truth.
- Prefer DNG first, then TIFF-based proprietary RAWs such as ARW/NEF/ORF/RAF,
  then QuickTime-based CR3 only after dedicated testing.
- Treat each camera/vendor format as a separate compatibility target. ExifTool
  may support writing a file type, but that does not prove Lightroom,
  Photomator, DaVinci Resolve, camera firmware, or vendor desktop software will
  accept the modified file.

Candidate config shape:

```yaml
xmp:
  write_mode: sidecar
  embedded_raw_rating:
    enabled: false
    write_only_rating: true
    keep_exiftool_backup: true
    extensions: [DNG]
```

After fixture validation, extensions can be promoted conservatively:

```yaml
xmp:
  embedded_raw_rating:
    enabled: true
    extensions: [DNG, ARW, NEF]
```

Do not enable `CR3`, `RAF`, `RW2`, `ORF`, or other proprietary formats by
default until fixtures for those formats pass.

## Embedded RAW Verification Matrix

For each fixture format:

1. Copy the RAW to a temporary test directory.
2. Capture pre-write metadata and image-data hashes:

   ```bash
   exiftool -G1 -a -s -XMP-xmp:Rating -Validate -Warning -Error FILE.RAW
   exiftool -api RequestAll=3 -ImageDataHash FILE.RAW
   ```

3. Write rating only:

   ```bash
   exiftool -P -XMP-xmp:Rating=4 FILE.RAW
   ```

4. Confirm backup and readback:

   ```bash
   test -f FILE.RAW_original
   exiftool -G1 -a -s -XMP-xmp:Rating -Validate -Warning -Error FILE.RAW
   exiftool -api RequestAll=3 -ImageDataHash FILE.RAW
   ```

5. Confirm the image-data hash did not change. The container bytes will change;
   the decoded image payload should not.
6. Open the modified copy in:
   - rawpy/libraw preview decode,
   - Lightroom Classic,
   - Photomator,
   - the vendor tool where available,
   - DaVinci Resolve if Resolve support is a target.

Promotion criteria:

- `XMP-xmp:Rating` reads back as `0..5`.
- ExifTool reports no new validation errors.
- Image-data hash is unchanged.
- The RAW still decodes through libraw/rawpy.
- At least Lightroom Classic and Photomator see the star rating.
- Vendor software does not reject or rewrite the file unexpectedly.

Until this matrix exists, embedded RAW rating should remain research-only.

## Local Fixture Pass - 2026-07-02

Downloaded six CC0 fixtures from raw.pixls.us into the gitignored
`.local/raw-fixtures/` directory:

| Format | Source camera | Size | Fixture |
| --- | --- | ---: | --- |
| ARW | Sony ILCE-7S | 5.88 MB | `sony-ilce-7s-14bit-14bit-compressed-3-2.arw` |
| NEF | Nikon D70s | 4.95 MB | `nikon-d70s-12bit-12bit-compressed-lossy-type-1-3-2.nef` |
| CR3 | Canon EOS R6 | 5.03 MB | `canon-eos-r6-3-2.cr3` |
| RAF | Fujifilm FinePix S5000 | 6.53 MB | `fujifilm-finepix-s5000-4-3.raf` |
| RW2 | Panasonic DMC-LX7 | 3.10 MB | `panasonic-dmc-lx7-1-1.rw2` |
| DNG | Blackmagic Micro Cinema Camera | 1.17 MB | `blackmagic-micro-cinema-camera-12bit-16-9.dng` |

Each download was checked against the SHA256 value advertised by raw.pixls.us.

The rating-only write test was run on copied files under
`.local/raw-fixtures/rating-write-sandbox/`, not on the downloaded originals:

```bash
exiftool -P -XMP-xmp:Rating=4 FILE.RAW
```

Results:

| Format | Write result | Rating readback | ExifTool backup | ImageDataHash unchanged | rawpy opens after write | Validate after write |
| --- | --- | ---: | --- | --- | --- | --- |
| ARW | ok | 4 | yes | yes | yes | 5 Warnings (1 minor), same as before |
| NEF | ok | 4 | yes | yes | yes | 1 Warning, same as before |
| CR3 | ok | 4 | yes | yes | yes | OK; fixture had rating `0` before write |
| RAF | ok | 4 | yes | yes | yes | OK |
| RW2 | ok | 4 | yes | yes | yes | 1 Warning (minor), same as before |
| DNG | ok | 4 | yes | yes | yes | OK |

This pass supports adding an experimental embedded RAW rating mode for copied or
operator-approved files. It does not prove Lightroom, Photomator, DaVinci
Resolve, or vendor applications will display every embedded rating correctly;
application import/readback remains the next required verification step.

## No-Backup Embedded Rating Pass - 2026-07-02

To answer storage concerns, a second copied fixture set was created under
`.local/raw-fixtures/display-test/` and written with persistent ExifTool backups
disabled:

```bash
exiftool -P -overwrite_original -XMP-xmp:Rating=4 FILE.RAW
```

Results:

| Format | Rating readback | `_original` backup left behind | ImageDataHash unchanged |
| --- | ---: | --- | --- |
| ARW | 4 | no | yes |
| NEF | 4 | no | yes |
| CR3 | 4 | no | yes |
| RAF | 4 | no | yes |
| RW2 | 4 | no | yes |
| DNG | 4 | no | yes |

Conclusion: production can avoid persistent 2x storage by using
`-overwrite_original` after the operator accepts the risk. ExifTool still
rewrites each file, so the implementation should process one file at a time and
leave enough temporary working space for the file currently being rewritten.

## Application Readback Pass - 2026-07-02

Tested the no-backup `display-test` copies on this Mac.

### Adobe Bridge 2026

Opened `.local/raw-fixtures/display-test/` directly in Bridge. The content grid
showed star-rating overlays under the embedded-rated RAW thumbnails. This is the
best local evidence so far that Adobe-family browsing can see the embedded
rating without sidecars.

### Photomator

Photomator displayed embedded four-star ratings in the window title for these
files:

| Format | Photomator result |
| --- | --- |
| CR3 | `3408 x 2272 - ****` shown |
| ARW | `2768 x 1848 - ****` shown |
| NEF | `3008 x 2000 - ****` shown |
| RW2 | `1368 x 1368 - ****` shown |
| DNG | `1920 x 1080 - ****` shown |
| RAF | No star shown for this old FinePix S5000 RAF; Photomator also did not fully enable editing controls for this sample, so this appears to be file-format/support related rather than an ExifTool rating-write failure. |

### DaVinci Resolve 21.0.0b.20

Resolve was launched headless and tested through its official scripting API.
The test project `material-agent-embedded-rating-test` imported five of the six
fixtures from `.local/raw-fixtures/display-test/`; RW2 was not imported.

For imported DNG, CR3, RAF, NEF, and ARW clips:

- `GetClipProperty()` included a `Rating` field, but it was empty.
- `GetMetadata()` did not expose a rating/star key.
- `GetThirdPartyMetadata()` did not expose a rating/star key.

Conclusion: Resolve should not be treated as a consumer of embedded
`XMP-xmp:Rating` for these RAW photo fixtures. If Resolve integration matters,
use a Resolve-specific metadata import path or a separate media-pool labeling
workflow rather than relying on RAW XMP rating.

## Filename Policy

Use the same base filename as the RAW with `.xmp` by default. If `.XMP` already
exists, update that file instead of creating a second sidecar. This mirrors the
practical lookup behavior documented by FastRawViewer and avoids stale-rating
duplicates on case-sensitive NAS filesystems.

## Verification

The code path now includes tests that:

- create a new sidecar without invoking ExifTool,
- parse the generated sidecar with ExifTool and read back `XMP:Rating`,
- preserve user `dc:subject` keywords while moving generated `pj:*` data to
  `xmp:Identifier`,
- update an existing uppercase `.XMP` sidecar without creating a lowercase
  duplicate.

Real application verification is still needed:

- Lightroom Classic: import RAW + generated sidecar or run Metadata -> Read
  Metadata From File.
- Photomator: import the RAW and corresponding `.XMP` sidecar together or import
  the containing folder.
- DaVinci Resolve: create a fixture import matrix before claiming support.
