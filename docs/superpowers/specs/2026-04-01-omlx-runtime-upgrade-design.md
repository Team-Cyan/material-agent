# OMLX 0.3 Runtime Upgrade Design

## Goal

Promote OMLX 0.3+ from an OpenAI-compatible backend into the primary inference runtime for `material-agent`, with strict `structured_outputs` + xgrammar enforcement, dedicated-instance validation, better diagnostics, and cleaner on-disk state layout.

This is a deliberate breaking upgrade for the OMLX path. Old OMLX contract compatibility is out of scope. If historical data becomes unreliable after prompt or schema changes, the supported path is to rerun with current code or use an older release branch.

## Non-Goals

- Do not make Ollama feature-parity with OMLX 0.3.
- Do not add multimodal embeddings in this project.
- Do not support old OMLX contract parsing or old runtime artifact compatibility.
- Do not split state into multiple SQLite database files.
- Do not add performance dashboards or historical telemetry UIs.

This does not mean Ollama can regress silently. Basic fallback usability must remain covered by regression tests.

## Product Direction

### Primary Runtime

- `backend: omlx` becomes the primary production path.
- `backend: ollama` stays available as a fallback path for future Windows/macOS scenarios, but it does not participate in this upgrade's capability model.
- Structured scoring reliability is treated as a runtime contract, not a best-effort prompt behavior.
- Ollama must remain basically usable as a fallback backend after the OMLX upgrade lands.

### Backend Selection Rule

- Only run OMLX capability checks when `config.backend == "omlx"`.
- If `config.backend == "ollama"`, skip all OMLX probe logic.
- `rescore` / `rejudge` and `rewrite-xmp` do not require OMLX and must never trigger OMLX probe logic.

## Architecture

### Runtime Contract

When `backend: omlx` is selected, `material-agent` must treat the target server as a required-capability runtime instead of a generic chat endpoint.

The OMLX runtime is considered valid only if all of the following are true:

- OMLX version is `>= 0.3.0`
- `structured_outputs` is available
- xgrammar support is available
- the running instance matches the expected dedicated instance and configured model set

If any requirement fails, `run` must fail fast before any photo scoring begins.

### Main Runtime Flow

For `backend: omlx`, the run flow becomes:

1. Load config
2. Resolve dedicated runtime expectations
3. Probe OMLX capability and instance state
4. Validate capability contract
5. If valid, build OMLX runtime client and execute the review job
6. If invalid, stop immediately and show a targeted install/fix guide

For `backend: ollama`, the existing backend flow remains available without OMLX-specific probing.

### Capability Probe

Introduce an `OMLXCapabilityProfile` that represents the current runtime state, including:

- server version
- structured output availability
- xgrammar availability
- served model set
- dedicated instance match
- relevant settings drift

This profile is runtime evidence for the current execution only. It is not versioned for historical compatibility.

## Structured Output Strategy

### Contract Policy

For OMLX, structured calls must use `structured_outputs` as the only formal contract path.

- `response_format` is no longer the primary implementation for OMLX
- prompt wording still matters for semantics, but not for output-shape enforcement
- prose fallback parsing is no longer a success path for the OMLX backend

### Stable Schema Names

Use stable schema names without embedded version suffixes:

- `material_agent.full_score`
- `material_agent.group_commentary`
- `material_agent.post_commentary`

Schema names stay stable. This branch only supports the current contract implementation.

### Request Defaults

For OMLX structured requests, default to:

- `enable_thinking = false`
- `temperature = 0.0`
- `xtc_probability = 0.0`

The first implementation should use JSON grammar only. Regex, choice, or custom grammar variants are out of scope for this phase.

### Prompt Boundary

Prompt files should describe task semantics only:

- scoring dimension meaning
- anti-double-counting guidance
- non-portrait handling rules
- language and tone requirements for commentary

Transport / contract code should own:

- `structured_outputs` payload construction
- schema registration and dispatch
- parsed-body extraction
- capability-aware request execution

## Configuration Design

Restructure the OMLX config surface into three responsibility groups.

### `omlx.runtime`

- `required_version: ">=0.3.0"`
- `require_structured_outputs: true`
- `require_xgrammar: true`
- `probe_on_run: true`
- `enforce_dedicated_instance: true`

### `omlx.requests`

- `vision_schema: material_agent.full_score`
- `group_commentary_schema: material_agent.group_commentary`
- `post_commentary_schema: material_agent.post_commentary`
- `enable_thinking: false`
- `temperature: 0.0`
- request token caps

### `omlx.admin`

- `instance_root`
- `expected_models`
- `expected_model_settings`
- cache policy

The config should not expose any historical contract version switch.

## Failure UX

Probe failure should not stop at a raw exception. It must produce targeted guidance.

Examples:

- OMLX not installed: show install commands / expected setup path
- version too old: show minimum version requirement and upgrade direction
- xgrammar missing: explain how to install or use a build that bundles grammar support
- wrong shared instance: explain that the configured URL is serving a mismatched model set and suggest `omlx-setup` / `omlx-start`

This guidance should be available in:

- CLI error output
- structured runtime events
- `omlx-status` diagnostics

## State And Storage

### Single SQLite Database

Keep a single SQLite database per input root. Do not split runtime and processed state into separate DB files.

### On-Disk Layout

Move runtime files into a hidden work directory:

```text
<input_dir>/.material-agent/
  state.db
  state.db-wal
  state.db-shm
  run.log
```

Benefits:

- keeps photo roots clean
- naturally groups SQLite companion files
- provides one place for future diagnostics and temporary runtime outputs

### Tables

Do not add a family of OMLX-specific tables.

Use the existing SQLite structure:

- processed state remains in the processed repository
- runtime state remains in `sessions`, `jobs`, `job_files`, `artifacts`, `events`

For this upgrade:

- reuse `artifacts` for probe/diagnostic payloads when needed
- reuse `events` for capability failures, contract failures, and runtime diagnostics
- avoid versioned artifact parsing logic

## Observability

### `omlx-status`

Upgrade `omlx-status` into a real diagnostic command.

It should report at least:

- OMLX version
- xgrammar availability
- `structured_outputs` readiness
- served models
- dedicated instance match
- settings drift

It should support:

- human-readable default output
- `--json` output for machine consumers

### Logging

Add structured logging fields for OMLX runtime behavior where useful:

- job id
- file path or group id
- model
- schema name
- attempt
- latency
- finish reason
- failure category

The logging goal is to explain why a run failed, not to build a full telemetry platform.

## Breaking Upgrade Policy

This design explicitly drops old-contract compatibility.

- No old artifact parser branches
- No contract version fallback logic
- No attempt to reinterpret old OMLX outputs under the new runtime

Supported recovery paths:

- rerun with current code and current prompts
- use an older release branch if old behavior is required

## Ollama Positioning

Ollama stays in the codebase, but only as a fallback backend.

That means:

- keep backend abstraction and core client support
- do not force OMLX 0.3 capability parity onto Ollama
- do not design this upgrade around Ollama limitations
- do keep regression coverage that proves the Ollama path is still runnable at a basic level

If Ollama becomes meaningfully stronger on Windows or macOS later, it can get its own upgrade project.

## Milestones

### M1: Runtime Probe And Dedicated Instance Validation

- add OMLX capability probe
- wire fail-fast into `run` when `backend: omlx`
- upgrade `omlx-status`
- upgrade dedicated-instance validation and drift checks

### M2: Structured Output Primary Path

- migrate OMLX full score to `structured_outputs`
- migrate group commentary to `structured_outputs`
- migrate post commentary to `structured_outputs`
- remove OMLX dependence on prose fallback success

### M3: Observability And Guidance

- persist probe/failure diagnostics into runtime artifacts/events
- improve CLI guidance for install/fix paths
- add `omlx-status --json`
- add structured logging for runtime failures

### M4: Cleanup

- remove old OMLX contract/fallback complexity that is no longer needed
- update README and config comments
- update AI docs and live-test expectations
- document OMLX as the primary path and Ollama as fallback

## Testing Strategy

### Unit Tests

- capability probe parsing
- capability validation rules
- request contract builders
- config validation
- install-guide formatting on failure

### Integration Tests

- `run` fails fast when OMLX capability is missing and `backend: omlx`
- `run` skips OMLX probe when `backend: ollama`
- `rescore` / `rejudge` never triggers OMLX probe
- `omlx-status` reports instance mismatch and grammar absence clearly
- mocked or fixture-backed Ollama review runs still complete through the basic scoring path

### Live Tests

- full score returns valid structured output on OMLX 0.3+
- group commentary returns valid structured output
- post commentary returns valid structured output
- failure guidance is clear when grammar or structured outputs are unavailable

### Ollama Regression Coverage

Keep a small but explicit Ollama safety net:

- config can still select `backend: ollama`
- Ollama runs do not trigger OMLX probe logic
- the basic scoring path still produces parseable scores with mocked Ollama responses
- commentary and writeback integration remain minimally functional under Ollama-backed tests

The goal is not parity. The goal is to guarantee that the fallback backend still works.

## Open Questions Resolved

- OMLX capability probe is only required when `backend: omlx`
- probe failures must include install/fix guidance
- on-disk runtime files move into `<input_dir>/.material-agent/`
- no historical contract compatibility will be supported
- no runtime contract version field is introduced
