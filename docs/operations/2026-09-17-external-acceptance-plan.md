# External acceptance plan awaiting execution authorization

This is a reviewable protocol, not an executed result. Current authorization
allows local code/tests, public-data evaluation and local commits. It excludes
physical photo/XMP writes, professional-software writeback, private-host work,
deployment and push. Do not execute these steps from this document alone.

## Professional-software round trip

Use a newly approved disposable directory containing copies of two public RAWs,
one JPEG and one DNG. Keep originals read-only and record their SHA-256 values.
The directory and installed application/version must be explicitly identified
before any write. Never select a user's actual library as the scratch directory.

Create the following isolated fixture cases only after write authorization:

| Initial state | Application projection | Expected effective state |
| --- | --- | --- |
| No Rating | Requested rating 3, selection keep | Rating 3, exactly one app keep keyword |
| Rating 0 | Requested rating 4, selection reject | Rating 4, exactly one app reject keyword |
| Rating 5 or -1 | Requested rating 2, selection keep | Existing nonzero rating preserved; conflict recorded |
| Existing app keep plus user keywords | Selection reject | Only app selection keyword replaced; user keywords unchanged |
| Multilingual keywords/description and unrelated namespaces | Supported app update | Unicode preserved; unrelated XML retained |
| Malformed or duplicate Rating declarations | Any update | File rejected without replacement; source identity/hash unchanged |

For each fixture, capture read-only ExifTool output and the application projection
receipt before and after the local writer operation. Import/open in Adobe Bridge,
Camera Raw, Photoshop and Capture One, using whichever applications and versions
are actually available. Record rating/keyword display, then a controlled human
rating/keyword edit and software save. Read back fields and compare them with the
saved state and the projection ledger. Repeat an application rewrite to verify
nonzero rating preservation and app-keyword replacement. A receipt alone cannot
prove that another application displays or preserves the fields.

Pass criteria: effective ratings and user keywords survive all covered paths;
app selection tags are exclusive; source RAW content hashes remain unchanged;
no unsupported format is edited in place; projection status matches real write
outcomes. Any application/version not executed remains unverified. Test failures
stop that fixture and preserve its before/after evidence for diagnosis. Delete
only the disposable copies after evidence is retained and cleanup is authorized.

## Target hardware and container recovery

This repository owns the generic application contract, not host control. An
external authorized operator must choose the target host and manage the private
backup/deployment workflow. Do not copy credentials, host names or host paths
into this public repository.

Reviewable execution sequence for a disposable appdata copy:

1. Record image digest, application/schema versions, provider config, SQLite
   integrity, representative job states and a hash inventory of read-only media.
2. Take an operator-managed recoverable appdata backup. Verify that the backup
   contains the DB/WAL state needed for a consistent restore before proceeding.
3. Restart/recreate the disposable container with the same image/config. Verify
   health, schema compatibility, provider availability and CPU fallback provenance.
4. Restore the disposable appdata backup, confirm completed jobs remain completed,
   and exercise the documented recovery behavior for an interrupted fixture job.
5. If relocation is separately approved, change only the disposable input mount;
   verify path/cache identity and expected reprocessing without metadata writes.
6. Compare media hashes and inspect logs for accidental writer invocation. Retain
   sanitized results, rollback to the original disposable state, and stop the
   test environment according to its original state.

Pass criteria: consistent SQLite restore, no lost/duplicated completion, explicit
provider/fallback status, documented path-identity behavior, and zero source-media
changes. Local unit tests and a different architecture's timing are insufficient.

## Minimum inputs required to execute

- Explicit scratch-photo/XMP-write scope and the photo application(s) available.
- Separately authorized target-host/operator scope and a recoverable disposable
  appdata backup for container/hardware work.

No push or production deployment is implied by either authorization.
