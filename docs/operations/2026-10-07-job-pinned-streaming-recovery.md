# Job-pinned diagnostic serialization recovery

The [job-pinned diagnostic](2026-10-06-job-pinned-score-diagnostic.md) was
implemented, independently reviewed and published in `d5446a5`. Local checks
passed 1,448 tests / ten skipped; exact-revision Linux CI passed 1,415 / 43
skipped, immutable-image smoke and promotion. Native deployment acknowledgement
timed out, but the exact live image, template, idle API and unchanged durable
sources were independently reconciled without repeating the update. Backup and
validated rollback context were retained.

The approved comparison of two existing 40,620-file historical jobs then failed.
The original private output was preserved. A separate read-only status check
found `MemoryError` in serialization, with allocation failure and no OpenBLAS,
pthread or NumPy import-failure indicators. Only the original private process
log exists, with no published review or completion receipt. This classification
is derived from a bounded log tail; the log body was not exported. Fixed
database, WAL/journal and configuration identities match the approved plan and
remain stable across the failure/status inspections.

## Scoped correction

The diagnostic previously serialized the entire report once for strict JSON
validation, then again as a complete Unicode string followed by a complete
UTF-8 byte buffer for writing. The fact graph and these copies could coexist.
The SQL reader already iterates its cursor; dropping cohort members or model
provenance is not an acceptable workaround.

The correction streams strict JSON validation and compact v3 JSON output. It
writes a private temporary file in the output directory, flushes/fsyncs it and
publishes only a complete report atomically. Existing outputs are protected and
owned temporary files are cleaned on write/encoding failure. Default v2 preview
behavior remains unchanged. All cohort rows, complete groups, rank diagnostics,
missing evidence and model provenance retain their existing schema and meaning.

The original diagnostic bounds remain 4 GiB address space, 600 seconds and
512 MiB report size. No model, scoring, rescore, selection-policy recalculation or
production metadata migration is added. A retry must use a new approved output
namespace and retain the failed original; it must not relax caps or truncate a
report to claim completion.

## Verification and continuation

Streaming regressions verify semantic parity with Unicode and full facts, strict
nonfinite errors, late write/encoding/fsync failure, atomic visibility and
protection of existing outputs and publication races. Independent review found
no actionable defect. Full checks pass 1,463 tests / ten skipped; 139 focused
checks, three repository-boundary checks and lint pass. The read-only status
transport passed 80 focused checks and independent review.

Commit `76ec1db` passed [exact-revision CI](https://github.com/Team-Cyan/material-agent/actions/runs/37618966435)
(1,430 passed / 43 skipped), immutable-image smoke and promotion. Authorized
native DockerMan deployment verified the exact revision, running idle API,
unchanged config/library, template audit, backup and validated rollback context.
Docker healthcheck is undefined; running/API verification does not claim a
Docker healthy status.

Two new approved namespaces completed the full August 28/August 27 and
August 28/July 16 comparisons under unchanged caps. Both exported complete
reports and integrity receipts; independent recomputation found zero mismatches
and exact completed-output reuse passed without another application invocation.
Durable source identities, private permissions and idle service/config/library
snapshots remain unchanged. July 16 is a true singleton baseline; historical
configuration differences and unknown code revisions prevent causal or
current-policy acceptance. See the [sanitized results](benchmarks/2026-10-07-job-pinned-historical/README.md).
A subsequent documentation-only deployment does not change the recorded
diagnostic revision or relabel these historical results as current-policy output.
