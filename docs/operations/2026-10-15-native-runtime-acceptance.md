# Native runtime acceptance — partial, 2026-10-15

Deployment and the fixed public native-quality diagnostic passed independent
controller review. Full RAW-pipeline, forced CPU fallback, interruption/restore
and professional-software GUI acceptance remain incomplete. This record does
not close those objectives.

## Deployment and protection

The native DockerMan deployment reconciled the exact reviewed application
revision `02d90568b8ec53c0cab85d739683c0d0cfcba299`, registry index digest
`sha256:a308c3e71293dfc2eb28fcb53f9b12016d04646aee825d48af6b8bb905049fab`
and image configuration ID
`sha256:3779460f3ce4473140f7d505f1b88b8493b64568b7525b2a8f26b6a8166dd3a2`.
The service was running with an idle API, unchanged mounts and read-only source
photos; the DockerMan audit reported no issues. This is deployment verification,
not inference or GUI acceptance.

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

## Remaining acceptance

The initial RAW-v2 staging command returned failure without a local success
receipt. A subsequent read-only inspection verified all 20 DNGs and the archive,
script and manifest against their exact hashes, with immutable 0444 files and a
0555 source directory. Production identity matched before and after inspection.
The original failure cause remains unknown; safe success-receipt reconciliation
is pending. Complete verified inputs alone do not establish a recovered staging
operation, and no retransmission is currently indicated.

All full-run, fallback and recovery cases remain unexecuted. There is no
successful A1/A2/A3 target-pipeline, forced-fallback, real interruption or restored
job result from this scope. Preserve the initial failure and inspection evidence,
reconcile the receipt before dispatch, and continue under the [bounded runtime
protocol](2026-10-14-runtime-acceptance-protocol.md).

Adobe Bridge 2026 GUI roundtrip has not passed. A locked desktop blocked actual
UI acceptance, and a later automation timeout supplied no success evidence.
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
| Corrected native runner | `aa18168d3bf0a4cf0c3b2fabbb2ef2c0b0b30289710747d68196255f709f23c5` |
| Actual quality-v2 operator export | `1ec82f97fa697ba746c555600e2c126b6756e4a66ed5353743c9054536c7d353` |
| RAW-v2 read-only input inspection | `f75ef10f531ace12f366d0c0b2e31a8bfde968c37b67c377fb2e01a8f339b4ea` |
| Independent analysis script | `0c21f57f21a94625d959224ba5c7f8915bb87034940828fbcb6847d2f745fa30` |
| Independent quality analysis result | `d5acdfeda46621d665a75d91d001778e614757b6b65226bd2ae9dbe4c076744a` |
| Accepted controller coefficient recomputation | `d8ea2b30b47e9d034451ea03fa1af7a22a7da04d0319a7c384f4d3531d5437c3` |
