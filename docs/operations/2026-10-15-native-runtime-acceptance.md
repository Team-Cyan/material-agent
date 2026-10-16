# Native runtime acceptance — partial, 2026-10-15

Last updated October 17, 2026; the dated filename is retained for existing links.

Deployment, the fixed public native-quality diagnostic, a bounded full RAW
dry-run and one-fixture NIMA CPU fallback passed independent controller review.
Interruption/restore and professional-software GUI acceptance remain incomplete;
the NIMA fallback does not establish SSD fallback or general fixture coverage.

## Deployment and protection

The native DockerMan deployment reconciled the exact reviewed application
revision `02d90568b8ec53c0cab85d739683c0d0cfcba299`, registry index digest
`sha256:a308c3e71293dfc2eb28fcb53f9b12016d04646aee825d48af6b8bb905049fab`
and image configuration ID
`sha256:3779460f3ce4473140f7d505f1b88b8493b64568b7525b2a8f26b6a8166dd3a2`.
The service was running with an idle API, unchanged mounts and read-only source
photos; the DockerMan audit reported no issues. This is deployment verification,
not inference or GUI acceptance.
The later helper commits leave this image's source build inputs unchanged;
their successful publication does not imply another deployment.

The operator retained a consistent database/configuration backup, verified
SQLite integrity and logical parity, and checked post-deployment source DB and
configuration byte identities. Backup verification and a rollback record passed
controller review. These protections do not demonstrate an interrupted-job or
whole-appdata restore.

## Native execution and public answers

The first quality attempt failed when Python multiprocessing created a real
forkserver Unix socket inside persistent work. The strict output guard rejected
it and the supervisor stopped the child; that failed attempt remains evidence.
The runner correction in `f3b01cf` redirects ephemeral IPC to the existing,
separate 64 MiB `/tmp` tmpfs. It preserves the rejection of sockets, symlinks and
other special entries in persistent outputs. Real forkserver and output-socket
regressions passed; the correction did not change scoring or the deployed image.

The separately reviewed quality-v2 attempt completed all 256 frozen images,
with actual CPU NIMA and SSD provenance for every item, two deterministic
repetitions, and unchanged original/copied input hashes. The disposable run was
bounded to two CPUs, 2.5 GiB memory, 512 MiB persistent output and 600 seconds.
Observed process-group sampled peak RSS was **613,842,944 bytes**. The runner
observed **95,020,445 output bytes** before final report publication. Native
benchmark elapsed time was **59.634334 seconds**, with **33.320693 seconds** cold
and **26.313301 seconds** warm. These observations do not establish a performance
improvement.

An independent analyzer joined the original public labels by exact ID and frozen
source SHA, then used SciPy Spearman and Pearson functions without fitting a
curve or tuning. The controller separately recomputed all eight coefficients.
KonIQ MOS and the KADID author's DMOS convention both assign higher values to
better quality.

| Native target | Images | Predictor | SROCC | Unfitted PLCC |
| --- | --- | --- | --- | --- |
| KonIQ MOS | 128 | Raw NIMA | 0.348089 | 0.351791 |
| KonIQ MOS | 128 | Effective benchmark score | 0.348089 | 0.351802 |
| KADID DMOS | 128 | Raw NIMA | 0.462917 | 0.461546 |
| KADID DMOS | 128 | Effective benchmark score | 0.462838 | 0.461556 |

The historical comparison passed exact cohort, source-hash, package-index,
manifest/profile and prior verification-receipt checks. The recorded profile
changes are only compiled-cache directory relocations. Across the same 256
images, the maximum absolute raw-NIMA and effective-score differences were
both **0**. This is descriptive agreement across historical executions; it is
not a causal code/performance comparison or a quality improvement.

This previously exposed fixed subset is not a fresh independent/blinded holdout
or an official full benchmark. `benchmark-local` reports native/effective
aesthetic scores; these are not full RAW-pipeline final ratings. MOS/DMOS do not
label directed important-content coverage. The results do not pass G1/G2,
certify safe discard or authorize policy promotion. Dataset provenance and
native label meanings are retained in the [public composite diagnostic](benchmarks/2026-10-02-public-composite/README.md).

## Bounded RAW execution

The initial RAW-v2 staging command returned failure without a local success
receipt. A subsequent read-only inspection verified all 20 DNGs and the archive,
script and manifest against their exact hashes, with immutable 0444 files and a
0555 source directory. Production identity matched before and after inspection.
The success receipt was subsequently reconciled through read-only verification,
without retransmitting media. The initial failure cause remains unknown;
receipt reconciliation does not establish that cause or a source-data repair.

The RAW-v2 full-run then failed with GNU `libgomp` thread creation reporting
`Resource temporarily unavailable`, without an OOM kill. This establishes an
OpenMP allocation failure, not the exact exhausted PID/host limit or consuming
library. Helper `a21d299` fixes the child environment to `OMP_NUM_THREADS=1`,
`OMP_THREAD_LIMIT=1` and `OPENBLAS_NUM_THREADS=1` before native imports. These are
requested OpenMP/BLAS controls, not a global thread-count guarantee or an OpenVINO
oneTBB cap. The production profile, prefetch scheduling and existing resource
bounds remain unchanged. Its [CI](https://github.com/Team-Cyan/material-agent/actions/runs/38850988032)
passed quality and publication checks; this is separate from the deployed image.

RAW-v3 full-run passed: **20 SIMULATED**, **0 written**, **0 errors**, unchanged
original/copied source hashes and complete final artifacts. For each adapter,
**15/20 output records carry verified native CPU provenance**; five records per
adapter lack model evidence, and their cause has not been independently
classified. These are output-record counts, not unique NIMA inference-call
counts. No blanket native coverage claim is made for all 20 fixtures.

The actual full pipeline produced A1 grouping diagnostics (five groups with
sizes 1, 4, 5, 5, 5), A2 preparation-memory telemetry and A3 final score/selection
artifacts. This does not certify a conditional refinement branch, new selection
utility or real metadata writes. Elapsed time was **32.235418 seconds**;
process-group sampled peak RSS was **1,864,826,880 bytes**, and observed persistent
output was **278,695,500 bytes** before final report publication. These are
observations for the thread-budget variant, not a quality-v2 performance
comparison. Earlier quality-v2 results retain their original runner identity.

## Bounded NIMA fallback

The RAW-v3 fallback case passed for the selected public RAW `g01i1`. The native
runtime advertised only `CPU`; the actual `GPU` request compiled and executed on
`CPU`, with `fallback_used=true`, actual device readback and reason
`requested_device_unavailable`. Its NIMA score **4.434767** and all ten
distribution buckets exactly matched the explicit CPU control. Source/copy
hashes were unchanged. Elapsed time was **2.528223 seconds** and process-group
sampled peak RSS was **224,935,936 bytes**. This verifies the unavailable-device
NIMA fallback path for one selected fixture, not SSD fallback, GPU performance
or all-fixture coverage.

An initial status observation was rejected by the identity guard. Subsequent
read-only verification matched the saved handle, and export from the same
retained container passed. The initial rejection's cause remains unproven;
there was no guard bypass or relaunch, and the failed observation is retained.

## Remaining acceptance

Recovery was requested but did not start: the run was blocked before a saved
container handle by a production-identity mismatch against the staging receipt.
The plan hash still matches. Exactly three subsequent read-only snapshots match
both the RAW-v3 staging receipt and fallback handle, including full mount
multiset equality. They do not identify the original differing field or cause;
an ordering hypothesis remains unproven. Next implement private failure-time
diagnostics while preserving the exact rejecting guard, obtain main-agent review,
then make one attempt. No code change or recovery launch has occurred, and no
SIGTERM/SIGKILL or restore case has executed. Continue under the [bounded runtime
protocol](2026-10-14-runtime-acceptance-protocol.md), retaining failed-case
evidence and separating each case's acceptance.

Adobe Bridge 2026 GUI roundtrip has not passed. Earlier locked-desktop evidence
is historical. Fresh application lookup by both name and bundle identifier
timed out, although application inventory remains available. There is no fresh
confirmation of the current lock state and no accepted UI read/edit/save result.
Production writer/ExifTool checks on disposable public sidecars establish only
a partial physical-file subset. They do not demonstrate another application's
display, edit/save or preservation behavior. The [external acceptance
protocol](2026-09-17-external-acceptance-plan.md) remains applicable.

## Evidence identities

Operator receipts, media, raw labels and private paths remain outside the public
repository. Full SHA256 identities below identify the reviewed evidence without
publishing those inputs.

| Evidence | SHA256 |
| --- | --- |
| Accepted deployment controller review | `6a261426d6b1dcdc999bde50678c030ead2a4a13e32ac3a73f4eb6e06ab1a8c4` |
| Post-deployment historical-backup verification receipt | `a98c272367e6839182a5d13dedfa8cd9816f2d7696614648a4367950234c549f` |
| Quality-v2 runner (`f3b01cf`) | `aa18168d3bf0a4cf0c3b2fabbb2ef2c0b0b30289710747d68196255f709f23c5` |
| RAW-v3 thread-budget runner (`a21d299`) | `48da718464bb63809ca7daa6da1b718508bebdfdb40201a3b51c772f4c2834a7` |
| Actual quality-v2 operator export | `1ec82f97fa697ba746c555600e2c126b6756e4a66ed5353743c9054536c7d353` |
| RAW-v2 read-only input inspection | `f75ef10f531ace12f366d0c0b2e31a8bfde968c37b67c377fb2e01a8f339b4ea` |
| RAW-v2 read-only reconciled staging receipt | `2523d2a4c507ba55d1be45dbff948fc1dec475fc65769fc1bf97630a9beae646` |
| Actual RAW-v3 full-run operator export | `2383add4990060d000a978ea6610dafef79b42afa802b1a771d0d797e645322b` |
| Accepted RAW-v3 full-run controller review | `6febab9cdf29cf2edc8d27b05a374bde2cb2badad2e18fd13c180adfcd4c69e5` |
| Actual RAW-v3 NIMA fallback operator export | `b5e412f8bda9a08aafa07f97d33b83333b49be26aae7c707be8c5983303b757e` |
| Accepted bounded NIMA fallback controller review | `fa05173c8f6cbd88a55e6ea89f2a527db9a394ffb7480994188a9db94e3cb0fc` |
| Independent analysis script | `0c21f57f21a94625d959224ba5c7f8915bb87034940828fbcb6847d2f745fa30` |
| Independent quality analysis result | `d5acdfeda46621d665a75d91d001778e614757b6b65226bd2ae9dbe4c076744a` |
| Accepted controller coefficient recomputation | `d8ea2b30b47e9d034451ea03fa1af7a22a7da04d0319a7c384f4d3531d5437c3` |
