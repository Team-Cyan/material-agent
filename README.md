# material-agent

NAS-first local photo culling and scoring agent.

`material-agent` is forked from `material-judge`, but its default direction is different:

- no Ollama or OMLX dependency in the primary path
- Intel integrated GPU first through native OpenVINO on Python 3.14
- CPU fallback for any NAS
- later hardware tags for NVIDIA CUDA, AMD MIGraphX, and native Apple Silicon
- XMP sidecar + SQLite state remain the durable output format

## Current Shape

The production flow remains:

```text
scan -> group -> local score -> group rank -> write XMP -> persist SQLite
```

The default config uses:

- `backend: local`
- `inference.runtime: openvino`
- `inference.device: AUTO:GPU,CPU`
- runtime state in `$MATERIAL_AGENT_WORK_DIR/state.db` and operational logs in
  `$MATERIAL_AGENT_WORK_DIR/run.log` when configured (the Intel OpenVINO image
  defaults to `/config`); otherwise both live under `.material-agent/` in the
  processed photo folder

The Intel image ships with a learned NIMA MobileNet aesthetic scorer through
OpenVINO. The baked profile currently requests `CPU`, records the requested and
actual OpenVINO execution device, and supports an explicit GPU override with
CPU fallback. No extra config bind mount is required for that profile; a config
mounted at `$MATERIAL_AGENT_CONFIG` can still replace it deliberately.

`run --dry-run` may create runtime session, job, event, and log records in the
writable work directory. It does not write XMP/rating data and does not persist
new processed score or `done` rows. Existing valid processed rows may be read to
simulate an incremental run, and their runtime file status is reported as
`skipped` rather than `written`.

The local backend always retains deterministic JPEG-preview heuristics as its
fallback. The Intel profile enables NIMA as the learned aesthetic input to final
score fusion. Optional MobileCLIP2 scene tags, BRISQUE/NIQE/MUSIQ/CLIPIQA+
signals, DINO embeddings, and MediaPipe face structure remain disabled until
broader real-camera calibration approves them.

## Commands

```bash
make install
make run DIR=/path/to/photos
make dry-run DIR=/path/to/photos
make rescore DIR=/path/to/photos
make reset-ai DIR=/path/to/photos
make reset-ai DIR=/path/to/photos CLEAR_XMP=1
make test
make check
```

Direct CLI:

```bash
uv run material-agent run /path/to/photos --config config.yaml
```

Built-in management UI:

```bash
uv run material-agent web \
  --input-dir /path/to/photos \
  --config config.yaml \
  --work-dir /path/to/appdata \
  --registry-dir /path/to/appdata/models
```

The Web UI manages parameters, checksum-pinned models, dry-run tasks, logs,
and full-library score browsing. Web-triggered tasks never write XMP or ratings;
their complete score payloads stay in the appdata runtime database. The Web UI
has no application-level authentication and is intended only for localhost or a
trusted LAN; do not publish its port to the Internet.

For a read-only Docker pilot, mount the source library read-only and keep all
runtime state in appdata:

```bash
docker run --rm --device /dev/dri \
  -e PUID=99 \
  -e PGID=100 \
  -e MATERIAL_AGENT_INPUT_DIR=/photos \
  -e MATERIAL_AGENT_WORK_DIR=/config \
  -e MATERIAL_AGENT_DRY_RUN=true \
  -v /mnt/user/material/photos:/photos:ro \
  -v /mnt/user/appdata/material-agent/runtime/.material-agent:/config \
  ghcr.io/team-cyan/material-agent:intel-openvino
```

With this layout, the photo library is input only. SQLite state is
`/config/state.db` and the file log is `/config/run.log`; both resolve to the
appdata bind mount rather than the photo directory. Without the `/config` bind,
those files live only in the container writable layer and disappear with a
recreated one-shot container.

The entrypoint starts as root only long enough to align the container account to
`PUID`/`PGID`, attach the account to visible `/dev/dri` groups, and migrate a
small allowlist of existing appdata runtime files. The scorer itself runs as the
unprivileged `material-agent` user. The entrypoint rejects work directories that
resolve to the source tree, `/`, or unsafe symlinks; it never changes ownership
inside the photo mount.

`reset-ai` removes database-owned AI state while preserving source-side XMP by
default. Pass `--clear-xmp` (or `CLEAR_XMP=1` through Make) only for an explicit
cleanup. Even then, scalar rating/instructions/description fields are removed
only when they still equal the values previously written by this application;
user changes are preserved.

For stable deployments, pin the image by digest or by the immutable commit-SHA
tag produced by the publish workflow. The mutable `intel-openvino` tag is
promoted only after the built digest passes the container smoke gate.

Isolated benchmark and OpenVINO bundle preparation:

```bash
uv run material-agent benchmark-local \
  --manifest tests/fixtures/local_benchmark/manifest.yaml \
  --output-dir .local/benchmark

uv run material-agent prepare-openvino-model \
  --source-model /path/to/model.onnx \
  --source-processor /path/to/processor \
  --output-dir ~/.material-agent/models/model-name

uv run material-agent models --registry-dir ~/.material-agent/models list

uv run material-agent benchmark-nima-device \
  --input-dir /path/to/raws \
  --model-path /path/to/nima_aesthetic_fp16.tflite \
  --output-dir .local/nima-device-benchmark \
  --devices CPU,GPU.0 --batch-sizes 1,4,8
```

Managed downloads belong in the persistent work/appdata model registry, not the
container writable layer. The optional token-protected model API and the local
aesthetic label store are documented in
`docs/operations/model-management.md` and
`docs/operations/aesthetic-label-store.md`.

## Dependency Model

The intended packaging model is one codebase with multiple runtime builds:

| tag | target | runtime |
| --- | --- | --- |
| `cpu` | universal fallback | deterministic local backend, optional `onnxruntime` CPU |
| `intel-openvino` | Intel CPU, iGPU, Arc, NPU | native OpenVINO |
| `nvidia-cuda` | NVIDIA dGPU | `onnxruntime-gpu` CUDA |
| `amd-migraphx` | ROCm-supported AMD GPU | ONNX Runtime MIGraphX |
| `apple-native` | Apple Silicon | native CoreML / MLX / MPS, not Docker GPU |

All Docker images should share the same Python 3.14 + uv base:

```text
ghcr.io/astral-sh/uv:python3.14-trixie
```

Do not build one giant image with every provider installed. Vendor runtimes have different wheel and library support windows, and mixed installs are fragile. Build different tags from the same source instead.

## Apple Silicon Position

Apple GPU acceleration should be native first. Docker's newer Model Runner can expose Apple Silicon Metal-backed inference through a host-side service, but direct Metal GPU passthrough into normal containers is not the same as Linux GPU device passthrough. For this project, Apple support should mean:

- native `material-agent` install using CoreML, MLX, or MPS
- optional host inference service bridge if Docker Model Runner is useful
- Docker CPU fallback only when native GPU access is unavailable

## Near-Term Work

1. Calibrate the optional local blocks on a reviewed real-camera RAW set.
2. Measure NIMA-specific warm CPU/GPU parity and utilization on the target Intel
   NAS; the existing DINO matrix is not NIMA evidence.
3. Run a separately authorized target-host isolated-XMP pilot and approve
   promotion thresholds; keep the main photo mount read-only until then.
4. Decide whether to retain or delete the remaining legacy teacher modules.
5. Collect real human labels later; the durable empty label-store infrastructure
   is already available.

## External Requirements

```text
exiftool >= 12
Python dependency set from pyproject.toml
```

The default path does not require Ollama, OMLX, or an OpenAI-compatible model service.
