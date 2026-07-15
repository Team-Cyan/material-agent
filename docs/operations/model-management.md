# Local Model Management

## Storage Boundary

Published container images are immutable. Bundled production models therefore
remain under `/opt/material-agent/models`, while operator-installed models live
under the appdata-backed `${MATERIAL_AGENT_WORK_DIR}/models` registry. Downloading
into the container writable layer is not supported because an image update would
discard the files.

The built-in catalog is checksum-pinned and currently exposes only adapters the
runtime actually understands:

- `nima-mobilenet-ava-fp16` for whole-frame aesthetic scoring;
- `ssd-mobilenet-v1-coco-opset12` for COCO object detection;
- `yunet-face-int8-2023mar` for face and eye localization.

Operators may provide `--catalog /path/catalog.json` or
`model_management.catalog_path` for additional models that use one of these
implemented adapter contracts. Catalog entries still require HTTPS, a pinned
SHA-256, a safe filename, and a supported role/adapter pair.

An arbitrary ONNX file is not selectable merely because it can be downloaded.
Its input, preprocessing, output, labels, and adapter contract must first be
implemented and tested.

## CLI

```bash
material-agent models --registry-dir /config/models list
material-agent models --registry-dir /config/models install nima-mobilenet-ava-fp16
material-agent models --registry-dir /config/models select nima-mobilenet-ava-fp16
material-agent models --registry-dir /config/models delete nima-mobilenet-ava-fp16
```

Deleting an active model is rejected. `--force` removes the managed copy and
clears the selection, but never deletes the immutable image-bundled copy.
Downloads use the catalog URL only, write through a private partial file, verify
SHA-256, and then atomically replace the managed asset.

Enable selection resolution in runtime config:

```yaml
model_management:
  selection_enabled: true
  registry_dir: ${MATERIAL_AGENT_WORK_DIR}/models
```

Selections are read at process startup. A running scoring job does not hot-swap
models.

## HTTP API

The API is an explicit command, not part of the one-shot scorer process:

```bash
material-agent models --registry-dir /config/models serve \
  --host 0.0.0.0 --port 8765 --token-file /run/secrets/material-agent-model-api
```

A bearer token is mandatory outside localhost. Endpoints:

- `GET /health`
- `GET /v1/models`
- `GET /v1/model-selections`
- `POST /v1/models/{model_id}/install`
- `POST /v1/models/{model_id}/select`
- `DELETE /v1/models/{model_id}`
- `DELETE /v1/models/{model_id}?force=true`

The API deliberately accepts no arbitrary URL or filesystem path.
