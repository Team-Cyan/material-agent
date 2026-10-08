# Native DNG orientation conformance

Two existing public DNGs with source EXIF Orientation 6 and 8 pass complete
orientation conformance in the native Linux container at application revision
`5274e944ab53653847f303564e94bfd842dca1d9`. The actual production decoder and
Grouper both take their RAW-postprocess fallback, with no model/inference,
production scoring or photo metadata write. This closes this two-input fallback
verification gap, not photographic or general RAW acceptance.

## Sources and frozen scope

The preceding [JPEG orientation correction](../../2026-10-08-grouping-exif-orientation.md)
had only six normal-orientation generic RAW fixtures and synthetic rotation
controls. A separate read-only inventory of the already acquired public HDR+
corpus selected the first DNG in each of 22 events: 18 had Orientation 1, one
had 6, one had 8 and two lacked the tag. Missing metadata stays unknown. No new
network source acquisition or broad source sweep was performed.

These are input DNGs as released by the [official HDR+ dataset](https://www.hdrplusdata.org/dataset.html),
attributed to Samuel W. Hasinoff et al., *Burst photography for high dynamic range
and low-light imaging on mobile cameras*, SIGGRAPH Asia 2016, under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The two original size/SHA identities match the existing manifests before and
after execution. They total 30,767,682 bytes. They were previously used in public
experiments and are not untouched photographic holdouts. No image content,
private source paths, host identities or operation receipts are redistributed.

## Oracle and measured conformance

For each source, force LibRaw `user_flip=0`, camera white balance, 8-bit output and
half-size demosaicing. Apply the independent explicit Pillow transform indicated
by numeric EXIF: 6 is clockwise 90 degrees, 8 counterclockwise 90 degrees.
Compare default LibRaw output and production decoding with that oracle. LibRaw's
own flip codes are 6 and 5 respectively; they are not the EXIF enum values.

| Source EXIF orientation | 6 | 8 |
| --- | ---: | ---: |
| Sensor size W×H | 4048×3036 | 4032×3024 |
| Native half-size displayed H×W | 2024×1518 | 2016×1512 |
| Focus gray H×W | 2024×1518 | 2016×1512 |
| Encoded scoring preview W×H | 768×1023 | 768×1024 |
| Maximum native/oracle pixel difference | 0 | 0 |
| Grouper hash Hamming distance from oracle | 0 | 0 |

Both preview-gray and focus-gray arrays exactly match the resized oracle. JPEG
bytes match an independently constructed encode with the same quality 85
parameters; decoded lossy JPEG pixels are not compared with uncompressed RGB as
if they were lossless. Both original sources remain byte-identical.

There are exactly eight successful postprocess calls: unrotated reference,
default reference, production decode and production grouping for each source.
`prefer_embedded=True` remains enabled. The observed preview source and one real
postprocess call at each production site prove actual fallback; matching a hash
alone would not prove that branch. The 1023 preview edge follows the existing
integer resize implementation; 1024 is a maximum, not an exact-size promise.

## Execution, integrity and limits

The first local launch failed before helper execution because the Mac rejected
its requested address-space limit. The failure is preserved with zero RAW calls;
the same 4 GiB bound was retained for Linux execution. Four frozen regular files
(two originals, protocol, helper) were staged as a 30,781,440-byte reviewed USTAR
package on SSD. Corpus, archive and index are root-owned/read-only; outputs use
UID:GID 99:100 and private modes 0700/0600.

The child enforces 4 GiB address space before imports, CPU 120/125 seconds, 1 MiB
output files, 128 file descriptors and an external 120-second wall deadline.
Python optimization is explicitly prohibited before the assertion-based helper
imports. These are enforced limits, not measured peak-RSS or speedup results.

Source database/WAL/journal/configuration identities, exact image, idle API,
mounts and SSD placement are checked around execution and failures. A review
found a premature success receipt; publication now occurs only after all inner,
controller and finalization guards pass. Failure regressions prove no receipt
survives a failed final guard or can be exported after drift is restored.
The completed run and exported report have matching protocol/report/plan hashes.
The idle service, full configuration and 40,620-record/zero-error library snapshot
remain unchanged. Original partial failures and completed results remain private
and durable. The wrapper prohibits overwriting or implicitly rerunning outputs.

The helper/protocol/package and private transport were independently reviewed.
The transport passed 73 focused and 203 related checks plus lint. Independent
completed-result verification matched strict JSON, all eight phase/parameter
records, complete source/protocol/plan identities and the original 2,970-byte
report digest. The service snapshots also match exactly. No full application-suite
rerun is needed for this report-only continuation, whose application sources and
previous 1,499-test result are unchanged.

[results.json](results.json) contains only sanitized counts, shapes and parity.
This supports two configured DNG fallback paths, not other RAW families, embedded
preview orientation, full-sensor decoding, real-person/eye quality, G1/G2 or policy
promotion. Their NCHW previews `[1,3,1023,768]` and `[1,3,1024,768]` match none of
the three previously validated MUSIQ buckets. No graph was selected, compiled
or scored, and no implicit resizing or new resource experiment is admitted.
