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
- `.material-agent/state.db` under each processed photo folder

The first local backend is intentionally simple: it uses deterministic JPEG-preview heuristics as a safe stand-in while the OpenVINO/ONNX scorers are added. It lets the project run without a model server and gives the new architecture a clean seam.

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

1. Add a native OpenVINO runtime adapter behind the `local` backend.
2. Add report-only benchmarks for the default local model stack documented in `docs/ai/model-selection.md`.
3. Add provider probes for CPU and Intel OpenVINO images.
4. Delete or quarantine copied OMLX/Ollama legacy modules once equivalent local paths exist.
5. Add a local label store for keep/review/reject and pairwise group preferences.

## External Requirements

```text
exiftool >= 12
Python dependency set from pyproject.toml
```

The default path does not require Ollama, OMLX, or an OpenAI-compatible model service.
