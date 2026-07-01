# Roadmap

## Completed

- forked `material-agent` from `material-judge`
- renamed the Python package, CLI, launcher names, and runtime work directory
- switched the default config to `backend: local`
- removed Ollama and OMLX from the default user-facing setup path
- added a local heuristic backend so the pipeline can run without a model server
- moved the project to Python 3.14 and the shared Python 3.14 + uv Docker base
- added CPU and Intel OpenVINO Dockerfile entrypoints
- documented the default local model stack and candidate backlog

## In Progress

- separate copied legacy OMLX/Ollama modules from the new primary path
- define the first Intel OpenVINO implementation boundary
- keep native OpenVINO as the Python 3.14 Intel path until `onnxruntime-openvino` publishes `cp314` wheels
- benchmark the remaining model candidates on fixed photo sets
- keep XMP sidecar and SQLite persistence compatible with the original review workflow
- keep CPU fallback usable while adding accelerator-specific runtime tags

## Next

- add a native OpenVINO adapter behind the local backend
- add the report-only benchmark harness for the current default model stack:
  - MUSIQ, NIMA, CLIPIQA
  - DINOv2-small
  - MobileCLIP2/MobileCLIP-S1
  - MediaPipe Face Landmarker
- add benchmark fixtures with face-positive, screenshot, low-quality, and near-duplicate groups
- add provider probing for Intel GPU access under Linux containers
- create a small fixture benchmark for group top-1, pairwise preference, and reject false-negative rate
- quarantine or delete copied OMLX/Ollama commands after equivalent local diagnostics exist

## Later

- add NVIDIA CUDA image tag
- investigate AMD MIGraphX image tag on supported ROCm hardware
- add native Apple Silicon install profile using CoreML, MLX, or MPS
- evaluate Docker Model Runner as an optional Apple host-service bridge
- add a local label store for keep/review/reject and pairwise group preferences
- train a small ranking/regression head on frozen embeddings after enough labels exist

## Deferred Or Not In Scope

- making Ollama or OMLX a required dependency again
- building one giant Docker image that includes every vendor runtime
- training a full visual backbone from scratch
- depending on Apple Metal GPU passthrough inside a normal Linux container
