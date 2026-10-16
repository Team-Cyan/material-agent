# Bounded native runtime acceptance protocol

`scripts/verify_runtime_acceptance.py` is an experiment-owned application runner,
not a deployment or host-control tool. Its controller must authorize and review
public fixture staging and run it in a disposable container with the reviewed
immutable image, no network, read-only public inputs and models, and a separate
writable output mount. The controller independently verifies the image revision
and digest. `source_revision` in this manifest is an expected identity; the runner
explicitly does not claim it proves the running image revision.

## Frozen command and manifest

```sh
python /acceptance/verify_runtime_acceptance.py \
  --case full-run --manifest /acceptance/manifest.json \
  --root /public --profile /app/config/config.yaml --output /output/results
python /acceptance/verify_runtime_acceptance.py --case status --output /output/results
```

Execution cases are `full-run`, `quality`, `fallback`, `recovery`. `status` reads
only the atomic checkpoint and accepts no execution inputs. Output must be new;
retry in a separately reviewed output namespace rather than overwrite evidence.
Use absolute disjoint paths with no symlink components. Original fixture files
must be regular single-link files with no write permission bits; the public root
must also have no write permission bits. A read-only mount alone does not satisfy
these mode checks. Preserve originals and their natural EXIF.

The exact JSON manifest fields are:

| Field | Contract |
| --- | --- |
| `schema_version` | `material-agent.runtime-acceptance.v1` |
| `source_revision` | Expected reviewed full 40-character revision; controller verifies actual image |
| `profile_sha256` | SHA256 of exact reviewed baked CPU profile bytes |
| `script_sha256` | SHA256 of exact independently reviewed runner bytes |
| `models` | Exactly `aesthetic`, `detection`, `face`, each with exact `{size, sha256}` of the profile's NIMA, SSD and YuNet files |
| `items` | Exact `{id, path, size, sha256}` records; IDs start with a letter/number and contain at most 64 ASCII letters/numbers/underscore/colon/dot/hyphen, without `..` or separators; native IDs such as `koniq:10020766793.jpg` are preserved; paths relative to public root, no hidden/traversal components |
| `bounds` | Exact `{wall_seconds, rss_bytes, output_bytes}`; integer limits, no booleans |

No MOS, DMOS, preference or reject labels enter the runner manifest or predictor.
The controller freezes and independently joins external public answers by exact
IDs and source hashes after scoring. Public task labels support only the task
they describe; missing directed important-content coverage labels do not block
these runtime diagnostics and do not require personal annotation.

`full-run` and `recovery` accept at most 32 actual supported RAW files. The
production `decode_raw` uses `rawpy.imread` and cannot score ordinary JPEG/PNG
through this CLI. These cases reject such inputs before output creation rather
than changing production decoding. `quality` accepts at most 256 JPEG/PNG images;
`fallback` accepts at most 32 supported RAW/JPEG/PNG inputs and evaluates one.
Inputs are capped at 64 MiB each and 512 MiB total. The output cap is at most
512 MiB including one shared immutable input copy, all caches/DBs/logs/reports.
Preflight requires at least 64 MiB beyond copied-input bytes. The total case wall
budget is at most 600 seconds, including all recovery children; process-group
RSS is at most 2,560 MiB. Linux sampling reads `/proc`; macOS boundary checks use
`ps`. Resource/output sampling is observational and stops detected excesses;
transport filesystem/container limits supply independent hard enforcement.

Child `TMPDIR`, `TEMP` and `TMP` point to the transport's separate 64 MiB `/tmp`
tmpfs. Python multiprocessing may create legitimate forkserver Unix sockets
there. These ephemeral IPC/temp entries are outside persistent output accounting
and the SQLite/config restore scope; the transport caps their filesystem usage.
DBs, compiled/XDG caches, configs, logs and report artifacts remain in owned
persistent output. Its guard still rejects every symlink, socket and other
special entry, identifying the owned relative path and file type on failure.
The original quality-v1 failure evidence must be retained; this environment-only
correction requires a new reviewed script hash, plan and output namespace.

The real RAW-v2 full-run later exited with GNU `libgomp` reporting thread
creation failure (`Resource temporarily unavailable`), without an OOM kill.
This proves an OpenMP thread-allocation failure, not which PID/host limit or
library exhausted it. Production preparation flattens the semantic groups:
with 20 files and the unchanged prefetch cap 32, up to 20 Python preparation
workers can call RAW postprocessing. It is not limited to a five-frame group.

The harness now fixes `OMP_NUM_THREADS=1`, `OMP_THREAD_LIMIT=1` and
`OPENBLAS_NUM_THREADS=1` in every fresh child's environment before native
imports, overriding inherited values. The report's `child_thread_budget`
records these requested controls and their scope. They bound applicable
OpenMP/OpenBLAS teams, not the Python preparation pool or all process threads;
OpenVINO's default oneTBB runtime is not governed by these OpenMP variables.
See the [GNU OpenMP thread controls](https://gcc.gnu.org/onlinedocs/libgomp/OMP_005fNUM_005fTHREADS.html),
[OpenMP thread limit](https://gcc.gnu.org/onlinedocs/libgomp/OMP_005fTHREAD_005fLIMIT.html)
and [OpenVINO threading properties](https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/query-device-properties.html).
Production profile, scheduling and the two-CPU/128-PID/container bounds remain
unchanged. A new reviewed runner hash/RAW namespace is required; earlier quality
results remain unchanged and are not a performance comparison for this variant.

## Actual case behavior

`full-run` launches the actual production CLI in a new process with
`MATERIAL_AGENT_WORK_DIR` under its owned output root and `--dry-run`. Differences
from the exact baked profile are fixture extensions, max-files bound and owned
registry/compiled-cache paths. Models/settings remain unchanged. It retains real
SQLite jobs/artifacts, complete native NIMA/detection provenance, semantic outputs,
`Grouping complete` counters and `material-agent.preparation-memory.v1` telemetry.
All files must end as `SIMULATED`, with zero `written_files` and zero errors.
Actual CPU native execution must occur for both NIMA and SSD. Conditional
refinement and multi-item grouping are reported only when their real evidence
exists; invoking finalization does not certify every conditional branch. This
case does write experiment runtime state, despite the dry-run flag.
Per-item missing model status is recorded in `native_observation_scope`, with
actual counts and excluded paths. A possible business short-circuit is not
silently promoted to full inference coverage or an independently diagnosed cause.

`quality` launches real `benchmark-local` with repeat count two and isolated
cache paths, using singleton fixture groups and no supplied labels. It requires
all selected IDs, deterministic finite scores and actual native CPU NIMA/SSD
execution. The service's own report remains in
`quality/benchmark/benchmark-report.json`; the final report also retains its
machine-readable results and SHA256. These scores reflect the existing
benchmark-local NIMA/effective-aesthetic contract, not RAW full-pipeline ratings.
The controller calculates native MOS/DMOS ranking diagnostics separately. No
production SQLite repository is constructed by the benchmark path.

`fallback` reads real `ov.Core().available_devices` in the isolated child and
fails if any GPU is advertised. It executes the real native NIMA adapter twice,
requesting CPU and GPU with explicit CPU fallback. Both distributions/scores must
match within 0.000001 and native execution-device readback must be CPU. The GPU
request must report `fallback_used=true` and the adapter's actual fallback reason;
CPU defaults or AUTO selecting CPU do not establish fallback. The controller
must omit GPU devices/groups from this disposable container. Neither available
provider lists nor inference results are mocked.

`recovery` first completes an uninterrupted control. It then runs independent
SIGTERM and SIGKILL cases; the external supervisor waits for a real committed
score artifact in a RUNNING job, makes a consistent SQLite online backup, checks
that the job is still interruptible and sends the actual signal. If the job
finishes too quickly, the case fails as unperformed. A signal receipt, PID, exit
code, pre-signal backup and actual post-signal DB are retained. SIGTERM must leave
CANCELLED; SIGKILL must terminate the child and leave the actual job RUNNING.
The supervisor always kills remaining descendants and reaps its child on errors,
including parent SIGTERM/KeyboardInterrupt. Native calls are subject to an
independent outer deadline rather than Python signal delivery assumptions.

Each captured DB is restored into a separate owned state root and checked for
exact row equality before launching another real CLI. The exact saved config is
retained and restored, remapping only owned cache/registry paths. SQLite backup
includes all runtime/processed tables and durable score-artifact metadata,
including committed WAL contents. Compiled model caches and process logs are
retained as evidence but are explicitly outside the restored durable-state scope;
this is not a general whole-appdata or host disaster-recovery test.

A fresh CLI invokes the real repository's abandoned-run reconciliation, records
exactly one `job_reconciled_cancelled` event for the captured old job, and creates
a new job for full reprocessing. Old job-file/artifact rows must remain unchanged
and unique. The new complete SIMULATED outcomes must match uninterrupted control
on scores, scene, decisions/reasons, policy signals, visible breakdown,
instructions, group commentary, rank/group and stable native predictions. Timing,
process/session/event IDs and owned cache paths are observational and excluded
from that declared comparison; full DB/native records remain available. This
contract does not claim same-job resume, WRITTEN completion reuse, photo metadata
restore or application-software roundtrip.

## Evidence and verification

Every parent stage and actual child start/online-backup/signal stage publishes an
atomic `checkpoint.json`. `report.json` is produced only after all selected case
requirements and original/copied input/profile/model identities pass; its
`schema_version` is `material-agent.runtime-acceptance.v1`, `case` is selected,
and `status` is `complete`. Failures preserve logs/DBs/checkpoints, emit no native
acceptance claim and never delete source media or prior experiment outputs.
Resource failures are not scores or performance successes.

```sh
uv run --no-sync pytest -q tests/test_runtime_acceptance_script.py \
  tests/test_local_benchmark.py tests/test_runtime_state.py
uv run --no-sync ruff check scripts/verify_runtime_acceptance.py \
  tests/test_runtime_acceptance_script.py
uv run --no-sync pytest -q tests/test_repository_boundary.py
git diff --check
```

Boundary tests exercise exact identity/path limits, real online SQLite/WAL
backup/restore/reconciliation, real process signalling and watchdog cleanup.
The optional existing ignored public RAW integration executes the real local
heuristic CLI and asserts SIMULATED artifacts and production telemetry; it is
not target-native acceptance. Missing native models, target transport or public
RAW fixtures remain unverified rather than replaced with simulated predictors.
