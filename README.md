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
- runtime state in `$MATERIAL_AGENT_WORK_DIR/state.db` when configured (the
  Docker images default to `/app/.material-agent`); otherwise
  `.material-agent/state.db` under the processed photo folder

The local backend always retains deterministic JPEG-preview heuristics as its
fallback. Optional learned blocks now provide MobileCLIP2 scene tags,
BRISQUE/NIQE/MUSIQ/NIMA/CLIPIQA+ signals, DINO embeddings, and MediaPipe face
structure. They remain disabled in the default config until broader real-camera
calibration approves production promotion.

## Commands

```bash
make install
make run DIR=/path/to/photos
make dry-run DIR=/path/to/photos
make rescore DIR=/path/to/photos
make reset-ai DIR=/path/to/photos
make test
make check
```

Direct CLI:

```bash
uv run material-agent run /path/to/photos --config config.yaml
```

For a read-only Docker pilot, mount the source library read-only and keep all
runtime state in appdata:

```bash
docker run --rm --device /dev/dri \
  -e MATERIAL_AGENT_INPUT_DIR=/photos \
  -e MATERIAL_AGENT_WORK_DIR=/config \
  -e MATERIAL_AGENT_DRY_RUN=true \
  -v /mnt/user/material/photos:/photos:ro \
  -v /mnt/user/appdata/material-agent:/config \
  ghcr.io/team-cyan/material-agent:intel-openvino
```

Isolated benchmark and OpenVINO bundle preparation:

```bash
uv run material-agent benchmark-local \
  --manifest tests/fixtures/local_benchmark/manifest.yaml \
  --output-dir .local/benchmark

uv run material-agent prepare-openvino-model \
  --source-model /path/to/model.onnx \
  --source-processor /path/to/processor \
  --output-dir ~/.material-agent/models/model-name
```

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
2. Verify native OpenVINO with `/dev/dri` on the target Intel NAS.
3. Run an isolated XMP/SQLite production pilot and approve promotion thresholds.
4. Decide whether to retain or delete the remaining legacy teacher modules.
5. Add a durable local label store after the initial fixture workflow stabilizes.

## External Requirements

```text
exiftool >= 12
Python dependency set from pyproject.toml
```

The default path does not require Ollama, OMLX, or an OpenAI-compatible model service.
