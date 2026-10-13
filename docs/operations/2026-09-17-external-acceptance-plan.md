# External acceptance protocol

This is a reviewable protocol, not an executed result. Updated October 14 to
retain the user's subsequent session authorization: public dataset downloads,
Unraid corpus storage, latest-version deployment, isolated real-environment
assessment, and reviewed commits/pushes may proceed within the agreed scope.
This document alone grants no authorization and must not erase authorization
already supplied by the user. See the [current follow-up plan](2026-09-26-culling-improvement-plan.md).

Existing public human ground truth can replace new personal annotation for the
task it actually labels, such as native quality or copy correspondence. Match
labels, splits and source identities to the diagnostic being reported. Missing
independent judgments of directed important-content coverage limit that quality
conclusion and policy promotion; they do not block deployment, CPU fallback,
recovery checks or other labeled algorithm diagnostics. Do not treat that gap as
a general requirement for the user to annotate photos.

## Professional-software round trip

Use an isolated disposable directory containing copies of two public RAWs,
one JPEG and one DNG, within the concrete authorized fixture scope. Keep originals
read-only and record their SHA-256 values.
Discover and record the directory and installed application/version before any
write. Never select a user's actual library as the scratch directory.

Create the following isolated fixture cases when covered by the existing
authorized test scope; otherwise request only the specific missing write scope:

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
are actually available. Record rating/keyword display, then a controlled
rating/keyword edit and software save through available application automation.
Discover available applications and attempt the supported UI path before asking
the user to operate it. A real account/login, interactive consent, or a personal
preference that cannot be inferred may require a concrete user action. Read back
fields and compare them with the saved state and the projection ledger. Repeat an application rewrite to verify
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
authorized homelab controller manages the already selected Unraid target and
private backup/deployment workflow. Isolated recovery, CPU fallback and benchmark
checks can proceed autonomously within that authorization, without writes to the
user's source library. Do not copy credentials, host names or host paths
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
5. When relocation is covered by the authorized isolated test scope, change only
   the disposable input mount;
   verify path/cache identity and expected reprocessing without metadata writes.
6. Compare media hashes and inspect logs for accidental writer invocation. Retain
   sanitized results, rollback to the original disposable state, and stop the
   test environment according to its original state.

Pass criteria: consistent SQLite restore, no lost/duplicated completion, explicit
provider/fallback status, documented path-identity behavior, and zero source-media
changes. Local unit tests and a different architecture's timing are insufficient.

## Remaining human involvement

Do not request the dataset, Unraid deployment, isolated evaluation or reviewed
push authorization again. Discover available applications, prepare a recoverable
disposable appdata backup and execute covered checks through the operator workflow.
Retain source hashes, rollback artifacts and actual application read/write evidence.

Ask only when a concrete step needs an unavailable account/interactive consent,
a personal selection preference, or a consequential action outside the agreed
scope. In particular, the authorization does not grant arbitrary writes to the
user's original photos/XMP or permission to contact dataset authors. Disposable
public-fixture writes and cleanup are assessed against the actual authorized test
scope, rather than a new blanket confirmation requirement. Report unavailable
application/version paths or missing task-specific labels as unverified evidence,
while continuing independent covered work.
