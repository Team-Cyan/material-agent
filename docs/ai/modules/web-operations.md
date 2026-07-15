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

The library index is stored in `library_index` inside the runtime database. It
keeps paths, sizes, modification times, and a scan generation. Scores are read
from the latest `jobs`/`job_files`/`artifacts(kind=score_payload)` record, so
dry-run results remain inspectable without marking source files processed.

## Safe Editing Guidance

- Keep API routes bearer-protected when listening beyond loopback.
- Keep the static shell public so it can present the token prompt.
- Preserve redacted secret values when a configuration is round-tripped.
- Validate a temporary YAML file with `load_config` before atomically replacing
  the active configuration, and keep the `.web.bak` backup.
- Resolve library paths below the configured input root before thumbnail reads.
- Do not add an endpoint that accepts arbitrary commands or arbitrary paths.
- Keep one active scoring subprocess per work directory.

## CLI

```bash
material-agent web \
  --host 0.0.0.0 \
  --port 8776 \
  --input-dir /photos \
  --config /app/config/config.yaml \
  --work-dir /config \
  --registry-dir /config/models \
  --token-file /run/secrets/material-agent-web-token
```

Listening on a non-loopback address without a token is rejected.

## Verification

- `uv run pytest -q tests/test_web_service.py`
- `uv run pytest -q`
- `uv run ruff check .`
- verify unauthorized `/health` returns 401 and authorized `/health` returns
  `{"status":"ok"}`;
- inspect container mounts and confirm `/photos` is `ro` while `/config` is the
  only mutable runtime-state mount;
- compare source XMP and `.material-agent` counts before and after a task.
