# Web Operations

## Ownership

`src/material_agent/app/web_service.py` owns the built-in operator HTTP service.
Static assets live under `src/material_agent/web/` and ship inside the normal
Python wheel and Docker images. The service intentionally uses the standard
library HTTP server so the CPU and Intel images do not gain another framework.

## Product Boundary

The Web UI is the primary operator surface for:

- indexing the mounted photo library;
- starting and cancelling scoring tasks;
- viewing task state and logs;
- browsing indexed files, thumbnails, scores, scene/target fields, and the
  complete persisted `score_payload`;
- validating and updating the runtime YAML configuration;
- installing, selecting, and deleting checksum-pinned managed models.

Web-started scoring is always invoked with `--dry-run`. It may write runtime
sessions, jobs, events, score artifacts, logs, thumbnails, task state, model
files, and configuration backups under the mounted work directory. It does not
write XMP, ratings, processed-cache rows, or files in the photo-library mount.

## Storage Model

- photo library: read-only input mount such as `/photos`;
- runtime DB: `${MATERIAL_AGENT_WORK_DIR}/state.db`;
- Web task state/logs/thumbnails: `${MATERIAL_AGENT_WORK_DIR}/web/`;
- managed models and selections: `${MATERIAL_AGENT_WORK_DIR}/models/`;
- runtime config: an operator-owned appdata file mounted read-write;
- no Web state is stored beside source photos.

Web directories are private (`0700`). Runtime configuration, task snapshots,
per-task configuration, logs, and configuration backup/temporary files are
created or repaired as private files (`0600`).

The library index is stored in `library_index` inside the runtime database. It
keeps paths, sizes, modification times, and a scan generation. Scores are read
from the latest `jobs`/`job_files`/`artifacts(kind=score_payload)` record, so
dry-run results remain inspectable without marking source files processed.
After group ranking, the score artifact is updated with `output_preview`, which
contains the rating, machine tags, instructions, description, and group fields
that would be sent to the metadata writer. This preview is DB-only in dry-run.

## Task Process Lifetime

`app/web_worker.py` supervises each Web CLI subprocess using only the standard
library. Before publishing a queued task, the manager locks two unique private
files under `web/workers/` and records their device/inode identities. It passes
the lifetime lease descriptor to both supervisor and CLI, and the control lease
only to the supervisor. Copies close without explicitly unlocking the shared
open-file-description locks. The resolved `MATERIAL_AGENT_WORK_DIR` is passed to
the CLI; the public task command remains the original dry-run command.

A restarted manager observes matching existing lease files and token-bound
private receipts. It reports a live task while the leases remain held, reads its
actual exit result after lifetime lease release, and maps CLI exit 130 to
`cancelled`. Cancellation writes an idempotent private request consumed by the
original supervisor, which signals only its own unreaped child process group.
The manager never signals a saved PID. Capabilities and lease identities stay
out of API task dictionaries.

Missing, replaced, unreadable or invalid ownership/control evidence yields
nonterminal `unknown` and blocks another Web launch. A released lifetime lease
without a terminal receipt yields `interrupted` with unknown exit status. A dead
supervisor with a surviving CLI releases its control lease but leaves the CLI's
lifetime lease held: status is `unknown`, cancellation returns an explicit
unavailable-controller error, and a new task remains blocked until exit. This is
not a guarantee of automatic recovery from arbitrary supervisor/process-tree
crashes; descendants that close the inherited descriptor are outside the lease's
lifetime evidence. The shared CLI `run.lock` remains the final write exclusion;
Web probes an existing lock without rewriting its contents before launching.

Legacy PID-only snapshots cannot authorize cancellation. A missing legacy
process together with a free runtime lock can be marked interrupted; live,
permission-unknown or PID-less legacy records remain unresolved. Corrupt task
snapshots fail manager initialization without overwriting the retained state.
No legacy task is replayed automatically. Keep unresolved evidence in private
operator storage for reconciliation rather than deleting lease files to bypass
an active task.

## Safe Editing Guidance

- Treat the Web service as a trusted-LAN operator surface. It intentionally has
  no application-level authentication, so port `8776` must not be published to
  the Internet or an untrusted VLAN.
- Preserve redacted secret values when a configuration is round-tripped.
- Validate a temporary YAML file with `load_config` before atomically replacing
  the active configuration, clean a rejected temporary file, and keep the
  private `.web.bak` backup.
- Resolve library paths below the configured input root before thumbnail reads.
- Do not add an endpoint that accepts arbitrary commands or arbitrary paths.
- Keep one active scoring subprocess per work directory.
- Keep container entrypoint source protection aligned with explicit Web CLI
  `--input-dir` and `--work-dir` values as well as their environment defaults;
  the scoring subprocess must inherit the resolved work directory.

## CLI

```bash
material-agent web \
  --host 0.0.0.0 \
  --port 8776 \
  --input-dir /photos \
  --config /app/config/config.yaml \
  --work-dir /config \
  --registry-dir /config/models
```

The maintained Unraid deployment listens on the trusted LAN without a token.

For a bounded offline comparison of persisted scores, execution provenance,
the effective task configuration, and reconstructed scoring previews, run the
application-owned review command inside the deployed image:

```bash
material-agent review-scores \
  --input-dir /photos \
  --work-dir /config \
  --output-dir /config/reviews/latest \
  --sample-count 18
```

The command opens `state.db` read-only, selects samples across score quantiles,
scenes, and multi-photo group spreads, and writes private (`0700` directory,
`0600` files) `review.json`, reconstructed JPEG samples, and a contact sheet
outside the photo input tree. Reconstruction uses the recorded job preview
configuration and the current decoder, including the explicit RGB-to-BGR
conversion immediately before OpenCV JPEG encoding. Historical byte identity
cannot be proven because prior scoring jobs did not persist their JPEG inputs.

For a complete, job-pinned historical comparison without photo reconstruction:

```bash
material-agent review-scores \
  --input-dir /photos \
  --work-dir /config \
  --output-dir /config/reviews/historical-comparison \
  --job-id JOB_A \
  --compare-job-id JOB_B \
  --no-previews
```

Replace `JOB_A` and `JOB_B` with two distinct stored review-job IDs. This v3
diagnostic accepts only `finished` or `finished_with_errors` review jobs and
reads both cohorts, session snapshots and artifacts in one read-only SQLite
transaction. Missing or unsupported IDs fail; there is no fallback to the latest
job. Default invocation without the new flags retains the v2 preview behavior.
`--no-previews` requires an explicit job; comparison requires both IDs and that
flag. A single explicit job can still reconstruct bounded previews if requested.

The report accounts for every stored job-file row, including errors, unscored
and nonfinite values. Group membership and rank diagnostics use complete cohorts;
quality/selection facts and their versions remain separate from legacy top-level
decisions. Missing, malformed, ambiguous and unsupported evidence is reported,
never inferred as a current policy decision. Configuration snapshots are redacted;
unrecorded historical application revisions remain unknown. Comparison uses exact
stored paths and exposes root, configuration and coverage differences; it does
not attribute observed differences to current policy or quality improvement.

With `--no-previews`, no photo existence, image decoding, thumbnail creation,
model call, rescore or selection recomputation is needed. Only private diagnostic
output is written, outside the current and historical photo roots and runtime
database. V3 validation/output streams strict compact JSON without whole-report
serialization buffers. A private same-directory temporary file is fsynced, then
published atomically without overwriting an existing report; choose a fresh
output directory for a new run. Default v2 preview output is unchanged. These reports can contain private paths and model metadata; keep them
in operator storage, not the public repository.

## Verification

- `uv run pytest -q tests/test_web_service.py`
- `uv run pytest -q tests/test_score_review.py`
- `uv run pytest -q`
- `uv run ruff check .`
- verify unauthenticated `/health` returns `{"status":"ok"}` from the trusted
  LAN;
- inspect container mounts and confirm `/photos` is `ro` while `/config` is the
  only mutable runtime-state mount;
- compare source XMP and `.material-agent` counts before and after a task.
