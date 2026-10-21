# Native runtime acceptance — partial, 2026-10-15

Last updated October 21, 2026; the dated filename is retained for existing links.

Deployment, the fixed public native-quality diagnostic, a bounded full RAW
dry-run and one-fixture NIMA CPU fallback passed independent controller review.
The separately reviewed isolated recovery-write case also passed bounded
SQLite restore, fresh-job reprocessing and XMP verification on public RAW copies.
The bounded Bridge technical stage is complete: clean case 07's post-writer UI
values, no-save close and hashes passed worker, main and independent advisory
review on October 21. Overall acceptance remains partial because this bounded
stage does not establish SSD fallback, general fixture coverage or the broader
cross-application and scientific gates.

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

## Recovery attempt 2 — failed, October 17

The first recovery launch was blocked before a saved container handle by a
production-identity mismatch against the staging receipt. The plan hash matched;
exactly three later read-only snapshots matched the RAW-v3 staging receipt and
fallback handle, including complete mount multisets. The original difference
and cause remain unknown; mount ordering was never established as the cause.

The private operator added failure-time identity diagnostics (`1f00a69`) and a
bounded export of nine fixed recovery JSON snapshots (`5b9b214`). Both received
review; the final wrapper suites passed 149 checks and the changes were pushed
to the private operator repository. Exact identity comparisons remain unchanged,
with no normalization or bypass. These are operator tooling changes, not a new
application deployment.

The single separately authorized attempt 2 passed that exact guard and launched
one isolated container with the unchanged RAW-v3 plan, runner and bounds. It
failed with `job completed without an interruptible committed milestone`.
The uninterrupted control completed **20 SIMULATED**, **0 written**, **0 errors**;
**15 serialized records per adapter** carry native CPU provenance. Control
elapsed time was **26.563908 seconds**, with sampled process-group peak RSS
**1,864,859,648 bytes**. The SIGTERM-designated child then finished with exit code
**0**, no observed committed milestone and **no signal sent**. SIGKILL, consistent
backup, restore and reconciliation were not executed. No interruption or restore
acceptance follows from this attempt.

The terminal export is retained and independently reviewed as failed: only the
control `after-db.json` snapshot is available, with the other eight fixed
snapshots explicitly missing. The supervisor verified original sources and the
checkpoint records unchanged original hashes. The final copied-input hash check
was not reached. There was no OOM kill, automatic retry or identity bypass.

Read-only code tracing explains why this dry-run harness could not observe its
required committed milestone: `JobExecutor` batches 2,048 logical updates, while
dry-run does not flush them individually. In the successful unresumed dry-run fixture path used for this attempt, the
fixtures stayed below that threshold; scores and finished status commit together,
leaving no committed running-plus-scores state for the observer. This finding
does not establish behavior for every possible set of 32 fixtures. This is a transaction-observation
constraint, not evidence that the successful CLI work needed more fixtures or
prefetch tuning. Do not blindly repeat that workload.

## Isolated recovery-write — accepted, October 19

The separately versioned `recovery-write` case used the same 20 frozen public
DNGs, immutable `02d9056` image, baked CPU profile/models and resource bounds.
Helper commit `092f3141f086b05a535aae99881fefa0e4286862` passed exact
[CI](https://github.com/Team-Cyan/material-agent/actions/runs/39146400398).
Its runner was staged separately; production runtime/source build inputs remain
unchanged. The dedicated plan permits only this case and public RAW input.
Originals and staged controls remained read only; the real CLI used explicit
`--reprocess` and wrote XMP only alongside owned RAW copies in isolated output.
No production hook, production-media write or service reconfiguration was introduced.

The control and both restored phases each completed **20 WRITTEN**, **0 errors**,
**0 simulated**, **0 skipped**, with 20 score artifacts and 20 XMP sidecars.
The SIGTERM phase observed three committed score artifacts and the SIGKILL phase
one, each belonging to its running job. Actual SIGSTOP barriers recorded the
same three process identities in stopped state before and after SQLite backup.
SIGTERM followed by SIGCONT produced exit **130** and cancellation; SIGKILL
produced exit **-9**, leaving the interrupted job running in its retained DB.
Both interrupted sidecar maps were empty and remain valid retained evidence.

Each consistent pre-signal backup was restored into a separate owned state root;
all-table rows matched before CLI execution. Fresh `--reprocess` runs created
distinct new jobs, reconciled each captured old job once, preserved its job-file
and artifact rows, and wrote all 20 outputs. This accepts backup restore followed
by new-job reprocessing. It does not establish same-job continuation.

Independent controller review accepted all **14 fixed JSON evidence files**.
The reviewer recomputed each complete phase's 20 XMP UTF-8 byte sizes/hashes,
reparsed the XML, and compared its semantic projection and generated values
against control. Original/copied RAW invariance is supported by frozen-plan-bound
supervisor and per-phase receipts; original RAW bytes were not exported for an
independent remote reread. JSON snapshot byte hashes were reconstructed from the
runner's deterministic serialization. Export contents alone do not independently
attest the launch image or actual process states; controller/transport receipts
own those checks.

Total child elapsed time across five phases was **88.656467 seconds**; sampled
peak RSS was **1,864,622,080 bytes**. The recorded output size before final report/checkpoint serialization was
**390,222,709 bytes**, including **2,803,326 bytes** in the fixed JSON evidence set. Each complete phase
has 15 serialized native CPU records per adapter, preserving the earlier
output-record coverage limitation. These measurements do not demonstrate a
performance or photographic-quality improvement.

The failed October 17 dry-run, its missing snapshots and unexplained earlier
identity rejection remain unchanged evidence. The replacement neither retries
that workload nor changes its result. This acceptance excludes production or
whole-appdata restore, atomic DB/XMP crash consistency, preservation of existing
vendor IDs, GUI roundtrip and G1/G2 admission. See the [bounded runtime
protocol](2026-10-14-runtime-acceptance-protocol.md).

## Remaining acceptance

Adobe Bridge 2026 16.0.3 now has accepted October 19 read/edit/save/reopen
observations for bounded ARW/NEF paths: cases 01, 02 and 05 cover rating/selection
keyword changes and user-keyword preservation; case 06 covers Unicode, foreign
fields and language alternatives. Case 03 DNG has correct read-only File Info
metadata; no thumbnail was observed in the tested Bridge grid. Case 04 JPEG
shows rating 0 and empty metadata despite an adjacent rating -1 sidecar: retain
this negative interoperability result, with no embedded write. Clean 07's GUI
edit and correct writer repeat are distinct
evidence: the October 20 physical writer review passed. The October 21 readback
attempt found Bridge running but its app-path and bundle-ID bindings timed out
with `-10005: timeoutReached`; Finder accessibility worked, and Finder-based
activation did not clear the timeout. No File Info result was observed during
that attempt; media and sidecar hashes remained unchanged, and no writer or
recovery path ran. After the human-confirmed normal Bridge reopen, the GUI
worker observed rating 4, keywords `家族`, `café`, `東京`, `Ω`,
`material-agent:keep`, and description `Repeat 家族 café 東京 Ω` for
`07-writer-repeat-clean.nef`. The main reviewer independently inspected the
private after-reopen screenshot. File Info was closed with Escape without
saving; root recomputed the four pre/post file hashes and 27 fixture/copy
inventory checks, and post-UI ExifTool semantics passed. An independent advisory
review found no actionable issue. The wrong-API first 07 attempt and its
same-copy correction are preserved and excluded.

See the [bounded Bridge review](2026-10-20-bridge-roundtrip-review.md) for exact
paths, evidence and finite closeout. Earlier lock/lookup failures remain history;
the blanket claim that no GUI path has passed is superseded by these scoped
results. The bounded Bridge technical stage is complete after worker
self-review, main visual/hash/metadata review and independent advisory review.
The October 20 lock error and October 21 binding timeout are resolved historical
access failures. Preserve the JPEG limitation; this stage does not certify
Capture One, a complete format matrix or vendor-ID preservation. Optional JPEG
embedded-write design is a separate follow-up requiring explicit opt-in scope;
no implementation or embedded write is authorized by this stage.

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
| Failed RAW-v3 recovery attempt 2 operator export | `abe37672aca7200c5852d7acc8f236d806215bbd2e2741f617e51f5deb6772a3` |
| Reviewed failed recovery attempt 2 controller receipt | `f7f07bd81f9d73e3263833662d2d6c15e0e7f286699f35d527339d64eefcd897` |
| Independent analysis script | `0c21f57f21a94625d959224ba5c7f8915bb87034940828fbcb6847d2f745fa30` |
| Independent quality analysis result | `d5acdfeda46621d665a75d91d001778e614757b6b65226bd2ae9dbe4c076744a` |
| Accepted controller coefficient recomputation | `d8ea2b30b47e9d034451ea03fa1af7a22a7da04d0319a7c384f4d3531d5437c3` |
| Recovery-write runner (`092f314`) | `445448bb6188a2a86ccf409a9904fd26c7bbc1f888823637d019d4260ca29508` |
| Accepted recovery-write plan | `b781524f7d9631ece71969ce109cfc3dfca11a30a644e55664de1af4dcbb29ba` |
| Accepted recovery-write manifest | `78b2211a138f93df18eb80792e358486098d4536a8dd7e1c625160473e8c7af8` |
| Actual recovery-write operator export | `5a172e64b233d972ba568020b79ff6626672b37df54f4ced6dc02ca2737010ec` |
| Recovery-write offline self-review | `e659d752ede9df5fdfecbdb05512b6b30d7fa9b607394dded1887a445116de77` |
| Accepted main independent recovery-write review | `b735a204d584887366ac91ceb6400be6d12d3b07c70c41c8977033be15f6c446` |
