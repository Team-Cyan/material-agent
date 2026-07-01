# oMLX Structured Output Notes

This note records the external references we checked while debugging local oMLX + Qwen vision structured output, plus the local project settings that were verified against a real OMLX server.

## Sources

- Qwen structured output guidance: <https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output>
- LM Studio structured output docs: <https://lmstudiodocs/ai/docs/developer/openai-compat/structured-output>
- LM Studio 0.3.6 release notes: <https://lmstudiodocs/ai/blog/lmstudio-v0.3.6>
- oMLX official site: <https://omlxdocs/ai/>
- Raw oMLX README: <https://raw.githubusercontent.com/jundot/omlx/main/README.md>

## What The Official Docs Say

### Qwen

- Qwen officially supports structured output using JSON-oriented formats and schema-constrained decoding.
- Structured output is not compatible with thinking mode. Keep `enable_thinking=false`.
- Too-small `max_tokens` can truncate structured output, even when the request format is correct.
- Prompt instructions still matter; structured output should not be treated as a complete substitute for a clear format contract.

### oMLX

- oMLX exposes an OpenAI-compatible API and explicitly documents structured output / JSON schema validation support.
- oMLX supports an `/admin` control surface and per-model settings that apply without a full reinstall.
- CLI and admin settings persist into `~/.omlx/settings.json` / `~/.omlx/model_settings.json`.
- oMLX is positioned as an Apple Silicon / MLX-native local inference server with batching and cache features.

### LM Studio

- LM Studio also supports OpenAI-compatible structured output, including `json_schema`.
- LM Studio documents different structured-output backends depending on runtime (`llama.cpp` grammar for GGUF, `Outlines` for MLX).
- LM Studio explicitly warns that not every model is equally reliable at structured output, especially smaller models.
- This means a switch from oMLX to LM Studio is not guaranteed to improve Qwen 3B JSON obedience by itself.

## Current Project Guidance

- Keep the main OMLX path on oMLX unless there is a fresh regression.
- Keep `enable_thinking=false` for all vision and commentary calls.
- Treat server-side `JSON validation failed`, prose drift, and `finished: length` as first-class failure signals.
- Use `response_format_json_schema` as the current default OMLX contract path for the local DMG runtime, with strict post-parse validation in the client.
- Keep top-level `structured_outputs={"json": schema}` available for pip/Homebrew runtimes that expose structured output / xgrammar support.
- Keep full invalid-response payload logging in application logs when parsing fails.
- Do not route photo fast screening through a small VLM anymore; use a dedicated local IQA model path.

## Request Settings vs Model Settings

Use both layers, but keep them separated by responsibility.

### Put In Request Payloads

These belong to the specific task being executed and may differ between `fast` and `full` calls:

- `response_format={"type":"json_schema", ...}` for commentary and vision schemas on the local DMG runtime
- top-level `structured_outputs` for commentary and vision schemas when using a runtime that exposes xgrammar-backed structured output
- `messages`
- prompt wording
- `max_tokens`
- `temperature`
- `enable_thinking`

Reasoning:

- These settings define the contract for one call.
- `fast` and `full` already need different behavior in this repository.
- Request-level settings are easier to test and safer to evolve.
- If request settings and model settings conflict, treat the request as the source of truth.

### Put In oMLX Model Settings

These should be stable defaults for a model that is dedicated to this project:

- `force_sampling=false`
- `thinking_budget_enabled=false`
- `specprefill_enabled=false`
- pin/default metadata

Reasoning:

- These settings are closer to a long-lived runtime posture than to one task contract.
- They help keep the server from starting each request from an unfriendly baseline.
- They are reasonable to keep when the models are reserved for this application.

### Recommended Split For This Repository

- `fast` path:
  - local `MUSIQ` via helper Python when the main uv environment cannot import `torch/pyiqa`
  - no OMLX small-VLM dependency
- `full` request path:
  - `material_agent.full_score` schema sent through `response_format_json_schema` on the local DMG runtime
  - prompt focused on scoring semantics and anti-double-counting rules
  - smaller `max_tokens`
- `commentary` request path:
  - separate text call
  - `response_format_json_schema` on the local DMG runtime
  - stable schema names for group/post commentary
- shared oMLX model settings:
  - `force_sampling=false`
  - `thinking_budget_enabled=false`
  - `specprefill_enabled=false`

## Request Format Guidance That Worked

### Fast Screening

- Use `MUSIQ` as the primary fast-screening implementation.
- Feed the existing preview JPEG into the IQA model; do not redesign the RAW path.
- Normalize the raw MUSIQ score into the repository's `0.0-10.0` range via `screening.musiq.score_divisor`.
- When the main uv environment cannot import `torch/pyiqa`, run MUSIQ in a dedicated helper Python (`screening.musiq.python_bin`).

Reasoning:

- Photo pre-screening is better served by a local NR-IQA model than by a chat-oriented small VLM.
- This removes schema drift and "prompt restatement" failure modes from the fast path entirely.
- In local verification, the helper path worked once stdout noise from `pyiqa` was sanitized/ignored and the final JSON object was extracted.

### Full Vision

- Use a short, semantics-first prompt.
- Send `response_format={"type":"json_schema", ...}` by default on the local DMG runtime.
- Use transport-level top-level `structured_outputs={"json": schema}` only when the runtime reports structured output / xgrammar support and the config requires that stricter path.
- Use `temperature=0.0`.
- Keep `max_tokens` tight enough to discourage prose drift.

Reasoning:

- OMLX 0.3+ is now treated as the primary structured runtime for this repository.
- Using the same transport-level schema path for vision and commentary reduces contract drift and simplifies capability validation.
- Large token caps and back-to-back heavy calls still make the runtime easier to stall or time out, so prompt size and token budgets remain important.

### Dedicated oMLX Instance

- Generate a dedicated instance root under `~/.material-agent/omlx`.
- Link only the OMLX models that are active in `config.yaml`:
  - union of `fast_vision_model`, `full_vision_model`, and `commentary_model`
  - deduped by basename
- Enable SSD cache for the dedicated instance.
- Keep `MUSIQ` out of the OMLX model directory entirely.

Operational note:

- If a shared OMLX server is already bound to the configured `base_url`, `material-agent` should still treat it as a mismatch unless its served model set exactly matches the linked-model directory for the current config.
- `material-agent omlx-status` should show whether the reachable server exactly matches the configured linked-model set.

## Local Settings That Were Verified

### Project Config

The following project-level settings were verified with repository tests plus real local runs:

- `omlx.vision_temperature: 0.0`
- `omlx.fast_vision_max_tokens: 96`
- `omlx.vision_max_tokens: 192`
- `omlx.commentary_max_tokens: 128`
- `omlx.group_commentary_max_tokens: 160`
- `omlx.post_commentary_max_tokens: 160`
- `omlx.max_concurrent: 1`
- `omlx.instance_root: ~/.material-agent/omlx`
- `omlx.model_dir_mode: config_union`
- `omlx.cache_enabled: true`
- `omlx.requests.contract_mode: response_format_json_schema`
- `omlx.requests.prompt_preset: qwen3`
- `screening.backend: musiq`
- `screening.musiq.python_bin: ~/.material-agent/musiq-venv/bin/python`

### Local oMLX Model Settings

The following local model settings are currently expected in the dedicated `~/.material-agent/omlx` instance:

- `Qwen3-VL-4B-Instruct-4bit.is_default: true`
- `Qwen3-VL-4B-Instruct-4bit.is_pinned: true`
- `Qwen3-VL-8B-Instruct-4bit.is_pinned: true`
- `force_sampling: false`
- `thinking_budget_enabled: false`
- `specprefill_enabled: false`

Observed effect:

- The strongest observed win still came from request-side fixes (`non-thinking`, shorter prompts, commentary schemas, stricter vision prompts, and lower token caps).
- Leaving `force_sampling=false` avoided accidental interference with request-level settings.

## Local Evidence From This Repository

We now have a strict live test that checks the raw OMLX reply itself, not only the final parsed fallback path:

- `tests/test_omlx_live.py`

Verified result after the current tuning:

- Repository tests for instance setup/status, config parsing, MUSIQ fallback, and scoring integration pass.
- Real local run on `/Users/lancer/materials/test` completed with:
  - `fast` using MUSIQ locally
  - `full` vision using `Qwen3-VL-8B-Instruct-4bit`
  - commentary remaining separate from scoring
  - DB/XMP outputs staying correct

Observed server-log improvement:

- Fast path is now expected to use the same transport-level schema family as full scoring.
- Group commentary moved from `Thinking Process` drift into direct schema-oriented JSON with `response_format_json_schema` plus `temperature=0.0`.
- Post commentary moved from `Thinking Process` or placeholder JSON into direct structured JSON with the same pattern.

Observed failure mode before the latest fast-path change:

- The small VLM fast path would restate the request, describe the image, and get truncated before the actual score.
- After replacing it with MUSIQ, the main remaining fast-path issue was helper stdout pollution (`Loading pretrained model...`) before the JSON payload.
- The robust fix was:
  - redirect noisy worker stdout to stderr
  - extract the last JSON object from helper stdout on the caller side

## What Not To Assume

- Do not assume a passing parsed result means structured output is healthy. A prose fallback may still be masking drift.
- Do not assume LM Studio would automatically outperform oMLX for this project. The model family and structured-output contract matter more than the UI/runtime branding.
- Do not assume smaller token caps are always better. For Qwen VLM, too-small caps caused JSON truncation repeatedly.
- Do not assume a reachable OMLX server is the dedicated `material-agent` instance; compare the served model set with the linked-model directory.

## Next Tuning Knobs Worth Considering

Only change one at a time and re-run the strict live test after each change.

### Safe To Keep

- `force_sampling=false`
- `vision_temperature=0.0`
- `fast_vision_max_tokens=96`
- `vision_max_tokens=192`
- `commentary_max_tokens=128`
- `group_commentary_max_tokens=160`
- `post_commentary_max_tokens=160`
- `max_concurrent=1`
- `screening.backend=musiq`
- dedicated `omlx.instance_root`
- dedicated cache enabled

### Reasonable Next Experiments

- Lower `preview.max_size` from `1024` to `768` if throughput matters more than fine visual detail.
- Try a dedicated text-only commentary model later if throughput becomes commentary-bound.
- If OMLX changes its structured-output contract again in a future release, re-run the live bucket before changing the default away from `response_format_json_schema`.
- If the helper Python becomes a maintenance burden, package a dedicated `python3.13 + torch + pyiqa` bootstrap script in the repository.

### Avoid Touching Without New Evidence

- `specprefill_enabled`
- scheduler-wide settings such as `max_num_seqs` or `completion_batch_size`
- process-wide memory guards

These may affect performance, but we do not yet have local evidence that they improve structured JSON reliability for this repository.

## Why We Are Not Switching To LM Studio Right Now

- oMLX is already passing the strict raw-JSON live tests in this repository.
- oMLX is a better conceptual fit for Apple Silicon + MLX VLM serving and exposes per-model server tuning.
- LM Studio may still be worth an A/B experiment later, but there is no evidence yet that it would outperform the current working oMLX setup for this project.
