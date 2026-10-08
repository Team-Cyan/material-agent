# Grouping EXIF orientation consistency

A read-only input audit found that the six existing public RAW fixtures all have
numeric EXIF Orientation 1. Their original-byte identities were rechecked.
They cover five embedded previews and one RAW-postprocess fallback, but cannot
establish real portrait RAW or rotated-EXIF acceptance. A bounded public metadata
probe made 48 requests: 31 normal orientation, four missing values and 13 failed
reads. No non-normal candidate was found and no RAW was downloaded. Failed reads
remain unknown. The probe conservatively accounted for 2,329,931 metadata bytes
under the frozen 4 MiB limit; its two initial requests reserve their full read
limits because their actual response sizes were not retained. Failed bounded reads
also include the extra overflow sentinel byte; no fetch was rerun for this
accounting correction. The source
[RAW sample repository](https://raw.pixls.us/) asks for landscape inputs, so this
negative search does not prove that portrait RAWs are unsupported or unavailable.

## Confirmed defect and scoped correction

An asymmetric synthetic JPEG with each of the eight EXIF orientation values
reproduced an input inconsistency. Scoring's existing OpenCV decoding matches the
canonical displayed image, while grouping previously hashed stored pixels through
Pillow without EXIF transpose. Orientation 1 matched; orientations 2–8 differed
by 26–32 of 64 hash bits from the displayed pixels, exceeding the existing
threshold 10. This can split equal displayed images or compare images in different
coordinate systems. It is a deterministic decoding defect, not a photographic
quality or semantic-coverage result.

The correction applies EXIF transpose exactly once before RGB conversion and
hashing for standard images and embedded JPEG previews. It preserves the existing
256-pixel pHash, adjacent time-plus-hash rule, thresholds and missing-evidence
splits. BITMAP previews and LibRaw-postprocessed fallback pixels are not rotated
again. It does not infer a RAW's full orientation from an absent preview tag.

Successful persisted grouping hashes carry the `phash-exif-v1:<16hex>`
preprocessing revision. Untagged,
unknown or malformed cache entries miss and are replaced only when an ordinary
future grouping operation needs those files. The existing state API and schema
remain unchanged; there is no cache migration command, processed-score invalidation
or automatic production run. The first subsequent enabled-hash grouping run can
therefore incur hash decoding for old entries; threshold zero still bypasses all
hash/cache work. This cost is explicit rather than reusing incompatible hashes.
Completed historical jobs and already-written groups during the same job
resume are not automatically recomputed.

## Verification and remaining limits

Independent code/cache-boundary review found no actionable defect. Full local
checks pass 1,499 tests / ten skipped; 73 initial focused checks, the added real
SQLite boundary and repository lint pass. All eight synthetic orientations now
match displayed pixels; a display-equivalent pair forms one group at the original
threshold. The six public RAW hashes and source bytes exactly match their saved
pre-change baseline. A real SQLite test verifies legacy replacement, reuse after
close/reopen and an unchanged existing processed score row.

The read-only six-RAW baseline and synthetic reproduction were saved before code
changes. Source photos/XMP, production config/policy and metadata are not written.
These controls cannot fill independent human G1/G2 quotas or establish real
portrait RAW/EXIF, personal preference or current-policy photographic utility.
