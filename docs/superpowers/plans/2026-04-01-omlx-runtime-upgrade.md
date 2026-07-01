# OMLX 0.3 Runtime Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote OMLX 0.3+ into the primary `material-agent` runtime with fail-fast capability probing, `structured_outputs`-first requests, a cleaner `<input_dir>/.material-agent/` runtime layout, and explicit Ollama fallback regression coverage.

**Architecture:** Add an OMLX runtime probe layer that only runs when `backend: omlx`, reject invalid runtimes with actionable install/fix guidance, and route all OMLX structured calls through a single `structured_outputs` contract path. Keep one SQLite database, move runtime files under `<input_dir>/.material-agent/`, reuse existing runtime `artifacts/events`, and preserve Ollama as a runnable fallback backend with minimal regression tests.

**Tech Stack:** Python 3.14, SQLite, httpx, pytest, ruff, OMLX OpenAI-compatible API, existing `material_agent` app/runtime architecture.

---

## File Structure

### New Files

- Create: `src/material_agent/adapters/models/omlx/probe.py`
  Purpose: detect OMLX runtime capabilities and build `OMLXCapabilityProfile`.
- Create: `src/material_agent/adapters/models/omlx/failure_guidance.py`
  Purpose: convert probe/runtime failures into install/fix guidance for CLI and runtime events.
- Create: `src/material_agent/utils/runtime_paths.py`
  Purpose: centralize `<input_dir>/.material-agent/` path creation for `state.db`, `run.log`, and related files.
- Create: `tests/test_omlx_probe.py`
  Purpose: unit coverage for capability probe parsing and validation.
- Create: `tests/test_runtime_paths.py`
  Purpose: unit coverage for hidden workdir layout and path resolution.

### Existing Files To Modify

- Modify: `src/material_agent/commands/scoring.py`
  Purpose: use runtime paths, gate OMLX probe only for `backend: omlx`, and emit guidance on failure.
- Modify: `src/material_agent/app/review_runtime.py`
  Purpose: persist probe/failure diagnostics into runtime events or artifacts before scoring proceeds.
- Modify: `src/material_agent/clients/omlx.py`
  Purpose: make `structured_outputs` the primary OMLX contract path and remove OMLX prose-success fallback behavior.
- Modify: `src/material_agent/adapters/models/omlx/contracts.py`
  Purpose: build `structured_outputs` payload fragments and parsed response extraction helpers.
- Modify: `src/material_agent/adapters/models/omlx/transport.py`
  Purpose: support `extra_body.structured_outputs` payload transport where needed.
- Modify: `src/material_agent/app/omlx_instance_service.py`
  Purpose: enrich `status()` with capability diagnostics and dedicated-instance checks.
- Modify: `src/material_agent/commands/omlx_runtime.py`
  Purpose: expose richer `omlx-status` output and optional `--json`.
- Modify: `src/material_agent/utils/config_validator.py`
  Purpose: normalize and validate `omlx.runtime`, `omlx.requests`, and `omlx.admin` config groups.
- Modify: `src/material_agent/adapters/models/omlx/instance.py`
  Purpose: align generated instance settings with the new config grouping and diagnostics.
- Modify: `src/material_agent/adapters/state/processed_sqlite.py`
  Purpose: switch DB path resolution to `<input_dir>/.material-agent/state.db`.
- Modify: `src/material_agent/adapters/state/sqlite_runtime.py`
  Purpose: operate on the same hidden workdir DB path and keep runtime tables unchanged.
- Modify: `src/material_agent/shells/cli/main.py`
  Purpose: add `--json` for `omlx-status` if parser wiring is needed there.
- Modify: `README.md`
  Purpose: document OMLX-first runtime, hidden workdir layout, and fallback Ollama status.
- Modify: `config.yaml`
  Purpose: move OMLX settings into `runtime/requests/admin` groups.

### Tests To Modify

- Modify: `tests/test_architecture_refine.py`
- Modify: `tests/test_omlx_instance_service.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_app_services.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_omlx_live.py`
- Modify: `tests/test_ollama_client.py`

## Task 1: Add Hidden Runtime Path Utilities

**Files:**
- Create: `src/material_agent/utils/runtime_paths.py`
- Modify: `src/material_agent/commands/scoring.py`
- Modify: `src/material_agent/adapters/state/processed_sqlite.py`
- Modify: `src/material_agent/adapters/state/sqlite_runtime.py`
- Test: `tests/test_runtime_paths.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing runtime-path tests**

```python
from pathlib import Path

from material_agent.utils.runtime_paths import build_runtime_paths


def test_runtime_paths_use_hidden_workdir(tmp_path):
    paths = build_runtime_paths(tmp_path)
    assert paths.work_dir == tmp_path / ".material-agent"
    assert paths.db_path == tmp_path / ".material-agent" / "state.db"
    assert paths.log_path == tmp_path / ".material-agent" / "run.log"
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `pytest tests/test_runtime_paths.py -v`  
Expected: FAIL because `material_agent.utils.runtime_paths` does not exist yet.

- [ ] **Step 3: Implement the shared runtime-path helper**

```python
@dataclass(frozen=True)
class RuntimePaths:
    work_dir: Path
    db_path: Path
    log_path: Path


def build_runtime_paths(input_dir: str | Path) -> RuntimePaths:
    root = Path(input_dir)
    work_dir = root / ".material-agent"
    return RuntimePaths(
        work_dir=work_dir,
        db_path=work_dir / "state.db",
        log_path=work_dir / "run.log",
    )
```

- [ ] **Step 4: Wire callers to use the helper**

Update:
- `cmd_run()` to use `paths.db_path` and `paths.log_path`
- `SQLiteProcessedRepository` to default to `paths.db_path`
- runtime repository call sites to use the same DB file

- [ ] **Step 5: Re-run focused state/path tests**

Run: `pytest tests/test_runtime_paths.py tests/test_state.py -v`  
Expected: PASS, including WAL-related tests now targeting `state.db`.

- [ ] **Step 6: Commit**

```bash
git add src/material_agent/utils/runtime_paths.py \
  src/material_agent/commands/scoring.py \
  src/material_agent/adapters/state/processed_sqlite.py \
  src/material_agent/adapters/state/sqlite_runtime.py \
  tests/test_runtime_paths.py tests/test_state.py
git commit -m "refactor(state): move runtime files into hidden workdir"
```

## Task 2: Normalize The New OMLX Config Groups

**Files:**
- Modify: `config.yaml`
- Modify: `src/material_agent/utils/config_validator.py`
- Test: `tests/test_config_validator.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing config tests for grouped OMLX settings**

```python
def test_normalize_config_sets_omlx_runtime_request_admin_defaults():
    normalized = normalize_config({"backend": "omlx", "omlx": {}})
    assert normalized["omlx"]["runtime"]["required_version"] == ">=0.3.0"
    assert normalized["omlx"]["requests"]["vision_schema"] == "material_agent.full_score"
```

- [ ] **Step 2: Run the focused config tests and confirm failure**

Run: `pytest tests/test_config_validator.py -v`  
Expected: FAIL because `omlx.runtime` / `omlx.requests` defaults do not exist yet.

- [ ] **Step 3: Implement normalization for the new OMLX config shape**

```python
omlx = normalized.setdefault("omlx", {})
runtime_cfg = omlx.setdefault("runtime", {})
runtime_cfg.setdefault("required_version", ">=0.3.0")
runtime_cfg.setdefault("require_structured_outputs", True)

request_cfg = omlx.setdefault("requests", {})
request_cfg.setdefault("vision_schema", "material_agent.full_score")
request_cfg.setdefault("group_commentary_schema", "material_agent.group_commentary")
request_cfg.setdefault("post_commentary_schema", "material_agent.post_commentary")
```

- [ ] **Step 4: Extend validation to reject incomplete OMLX runtime config**

Check:
- `backend: omlx` still requires `base_url`, `full_vision_model`, `commentary_model`, `timeout`
- new runtime booleans and grouped request settings are normalized before validation

- [ ] **Step 5: Update the sample config and parser expectations**

Update `config.yaml` comments so the new grouped settings are the documented/default path.

- [ ] **Step 6: Re-run focused config tests**

Run: `pytest tests/test_config_validator.py tests/test_main.py -v`  
Expected: PASS with both old essentials and new grouped settings covered.

- [ ] **Step 7: Commit**

```bash
git add config.yaml src/material_agent/utils/config_validator.py \
  tests/test_config_validator.py tests/test_main.py
git commit -m "feat(config): group OMLX runtime request settings"
```

## Task 3: Add OMLX Capability Probe And Failure Guidance

**Files:**
- Create: `src/material_agent/adapters/models/omlx/probe.py`
- Create: `src/material_agent/adapters/models/omlx/failure_guidance.py`
- Modify: `src/material_agent/app/omlx_instance_service.py`
- Modify: `src/material_agent/commands/omlx_runtime.py`
- Test: `tests/test_omlx_probe.py`
- Test: `tests/test_omlx_instance_service.py`

- [ ] **Step 1: Write failing probe tests**

```python
def test_probe_rejects_old_omlx_version():
    profile = OMLXCapabilityProfile(
        version="0.2.24",
        structured_outputs=True,
        xgrammar=True,
        instance_matches=True,
    )
    valid, reason = validate_omlx_capability(profile, required_version=">=0.3.0")
    assert valid is False
    assert reason.code == "version_too_old"
```

- [ ] **Step 2: Run the focused probe tests and confirm failure**

Run: `pytest tests/test_omlx_probe.py tests/test_omlx_instance_service.py -v`  
Expected: FAIL because probe helpers do not exist yet.

- [ ] **Step 3: Implement capability profile and validation**

```python
@dataclass(frozen=True)
class OMLXCapabilityProfile:
    version: str | None
    structured_outputs: bool
    xgrammar: bool
    served_models: list[str]
    instance_matches: bool
    settings_drift: list[str]
```

Include helpers to:
- query runtime endpoints or diagnostic payloads
- detect `structured_outputs` readiness
- detect xgrammar availability
- validate `>=0.3.0`

- [ ] **Step 4: Implement actionable failure guidance**

Map failure codes such as:
- `omlx_unreachable`
- `version_too_old`
- `structured_outputs_missing`
- `xgrammar_missing`
- `instance_mismatch`

to short install/fix instructions for CLI output.

- [ ] **Step 5: Upgrade `OMLXInstanceService.status()` to include capability fields**

Expose:
- `version`
- `structured_outputs`
- `xgrammar`
- `served_models`
- `instance_matches`
- `settings_drift`

- [ ] **Step 6: Re-run focused probe/status tests**

Run: `pytest tests/test_omlx_probe.py tests/test_omlx_instance_service.py -v`  
Expected: PASS with old-version rejection and guidance formatting covered.

- [ ] **Step 7: Commit**

```bash
git add src/material_agent/adapters/models/omlx/probe.py \
  src/material_agent/adapters/models/omlx/failure_guidance.py \
  src/material_agent/app/omlx_instance_service.py \
  src/material_agent/commands/omlx_runtime.py \
  tests/test_omlx_probe.py tests/test_omlx_instance_service.py
git commit -m "feat(vision): add OMLX capability probe and guidance"
```

## Task 4: Gate `run` On OMLX Probe Only When Needed

**Files:**
- Modify: `src/material_agent/commands/scoring.py`
- Modify: `src/material_agent/app/review_runtime.py`
- Test: `tests/test_main.py`
- Test: `tests/test_app_services.py`

- [ ] **Step 1: Write failing run-gating tests**

```python
def test_cmd_run_probes_omlx_only_for_omlx_backend(monkeypatch):
    seen = {"called": False}
    monkeypatch.setattr("material_agent.commands.scoring.probe_omlx_runtime", lambda config: seen.__setitem__("called", True))
    cmd_run(args, {"backend": "ollama", "ollama": {...}})
    assert seen["called"] is False
```

- [ ] **Step 2: Run focused command tests and confirm failure**

Run: `pytest tests/test_main.py tests/test_app_services.py -v`  
Expected: FAIL because `cmd_run()` does not gate OMLX setup/probe yet.

- [ ] **Step 3: Add the fail-fast OMLX gate to `cmd_run()`**

Pseudo-flow:

```python
if config["backend"] == "omlx":
    profile = probe_omlx_runtime(config)
    valid, failure = validate_omlx_capability(profile, ...)
    if not valid:
        raise RuntimeError(format_omlx_failure_guidance(failure, config))
```

- [ ] **Step 4: Persist probe/failure diagnostics into runtime events**

Before launching the review job, record:
- successful probe summary
- failed probe reason and guidance

Keep this in the existing runtime event/artifact path, not a new table family.

- [ ] **Step 5: Re-run focused command/runtime tests**

Run: `pytest tests/test_main.py tests/test_app_services.py -v`  
Expected: PASS with both `backend: omlx` and `backend: ollama` behavior covered.

- [ ] **Step 6: Commit**

```bash
git add src/material_agent/commands/scoring.py src/material_agent/app/review_runtime.py \
  tests/test_main.py tests/test_app_services.py
git commit -m "feat(cli): gate OMLX runs on capability probe"
```

## Task 5: Switch OMLX Structured Calls To `structured_outputs`

**Files:**
- Modify: `src/material_agent/adapters/models/omlx/contracts.py`
- Modify: `src/material_agent/adapters/models/omlx/transport.py`
- Modify: `src/material_agent/clients/omlx.py`
- Modify: `src/material_agent/clients/prompts.py`
- Test: `tests/test_architecture_refine.py`
- Test: `tests/test_dimension_redesign.py`
- Test: `tests/test_omlx_live.py`

- [ ] **Step 1: Write failing tests for `structured_outputs` payload building**

```python
def test_async_omlx_full_request_uses_structured_outputs():
    ...
    assert payload["extra_body"]["structured_outputs"]["type"] == "json"
    assert payload["extra_body"]["structured_outputs"]["json_schema"]["name"] == "material_agent.full_score"
```

- [ ] **Step 2: Run focused OMLX client tests and confirm failure**

Run: `pytest tests/test_architecture_refine.py tests/test_dimension_redesign.py -v`  
Expected: FAIL because the client still uses `response_format` as the primary path.

- [ ] **Step 3: Add `structured_outputs` builders to OMLX contracts**

Implement helpers such as:

```python
def build_omlx_structured_outputs(schema_name: str, schema: dict) -> dict:
    return {
        "type": "json",
        "json_schema": {"name": schema_name, "schema": schema},
    }
```

- [ ] **Step 4: Update the OMLX client to use the new primary path**

For OMLX:
- full score -> `material_agent.full_score`
- group commentary -> `material_agent.group_commentary`
- post commentary -> `material_agent.post_commentary`

Remove OMLX success paths that depend on prose being reparsed after structured failure.

- [ ] **Step 5: Keep prompts semantic-only**

Trim any prompt wording that still acts like format enforcement. Keep:
- scoring semantics
- language constraints
- anti-double-counting rules

- [ ] **Step 6: Re-run focused OMLX tests**

Run: `pytest tests/test_architecture_refine.py tests/test_dimension_redesign.py tests/test_omlx_live.py -v`  
Expected: PASS, with live tests still skippable when no real server is configured.

- [ ] **Step 7: Commit**

```bash
git add src/material_agent/adapters/models/omlx/contracts.py \
  src/material_agent/adapters/models/omlx/transport.py \
  src/material_agent/clients/omlx.py src/material_agent/clients/prompts.py \
  tests/test_architecture_refine.py tests/test_dimension_redesign.py tests/test_omlx_live.py
git commit -m "feat(vision): switch OMLX to structured outputs"
```

## Task 6: Upgrade `omlx-status` Diagnostics And JSON Output

**Files:**
- Modify: `src/material_agent/commands/omlx_runtime.py`
- Modify: `src/material_agent/app/omlx_instance_service.py`
- Modify: `src/material_agent/shells/cli/main.py`
- Test: `tests/test_omlx_instance_service.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing status-output tests**

```python
def test_cmd_status_omlx_supports_json_output(capsys):
    cmd_status_omlx(SimpleNamespace(json=True), config)
    payload = json.loads(capsys.readouterr().out)
    assert "structured_outputs" in payload
```

- [ ] **Step 2: Run the focused status tests and confirm failure**

Run: `pytest tests/test_omlx_instance_service.py tests/test_main.py -v`  
Expected: FAIL because `--json` output is not implemented.

- [ ] **Step 3: Implement richer status summaries**

Expose:
- version
- xgrammar
- structured output readiness
- served models
- linked models
- instance match
- settings drift

- [ ] **Step 4: Add `--json` CLI support**

Update parser wiring and command output so `omlx-status --json` prints machine-readable JSON.

- [ ] **Step 5: Re-run focused status tests**

Run: `pytest tests/test_omlx_instance_service.py tests/test_main.py -v`  
Expected: PASS with both text and JSON output covered.

- [ ] **Step 6: Commit**

```bash
git add src/material_agent/commands/omlx_runtime.py \
  src/material_agent/app/omlx_instance_service.py \
  src/material_agent/shells/cli/main.py \
  tests/test_omlx_instance_service.py tests/test_main.py
git commit -m "feat(cli): expand OMLX status diagnostics"
```

## Task 7: Keep Ollama As A Working Fallback

**Files:**
- Modify: `tests/test_ollama_client.py`
- Modify: `tests/test_architecture_refine.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write or tighten Ollama fallback regression tests**

```python
def test_ollama_backend_run_does_not_trigger_omlx_probe(monkeypatch):
    seen = {"called": False}
    monkeypatch.setattr("material_agent.commands.scoring.probe_omlx_runtime", lambda config: seen.__setitem__("called", True))
    ...
    assert seen["called"] is False
```

- [ ] **Step 2: Run focused Ollama regression tests and confirm current gaps**

Run: `pytest tests/test_ollama_client.py tests/test_pipeline.py tests/test_main.py -v`  
Expected: one or more FAILs until the new OMLX gate is safely bypassed for Ollama.

- [ ] **Step 3: Adjust shared command/runtime code so Ollama still runs**

Ensure:
- Ollama config selection still works
- OMLX probe is skipped
- commentary/writeback mocks still flow through the pipeline

- [ ] **Step 4: Re-run focused Ollama regression tests**

Run: `pytest tests/test_ollama_client.py tests/test_pipeline.py tests/test_main.py -v`  
Expected: PASS with basic fallback usability preserved.

- [ ] **Step 5: Commit**

```bash
git add tests/test_ollama_client.py tests/test_architecture_refine.py \
  tests/test_pipeline.py tests/test_main.py
git commit -m "test(vision): keep Ollama fallback runnable"
```

## Task 8: Update Docs And Runtime Notes

**Files:**
- Modify: `README.md`
- Modify: `docs/ai/reference/omlx-structured-output.md`
- Modify: `config.yaml`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write doc assertions or update existing expectations**

Prefer lightweight tests that guard key repository defaults rather than snapshotting large docs.

- [ ] **Step 2: Update user-facing docs**

Document:
- OMLX 0.3+ as the preferred runtime
- `structured_outputs` + xgrammar requirements
- hidden workdir layout under `<input_dir>/.material-agent/`
- probe failure guidance
- Ollama as fallback, not feature-equal peer

- [ ] **Step 3: Re-run targeted doc/config tests**

Run: `pytest tests/test_main.py -v`  
Expected: PASS for repo-default assertions after docs/config changes.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/ai/reference/omlx-structured-output.md config.yaml tests/test_main.py
git commit -m "docs(ai): document OMLX-first runtime contract"
```

## Task 9: Final Verification And Cleanup

**Files:**
- Modify: any touched files from previous tasks
- Test: full repository verification

- [ ] **Step 1: Run the focused high-risk test buckets**

Run:

```bash
pytest tests/test_omlx_probe.py tests/test_runtime_paths.py \
  tests/test_architecture_refine.py tests/test_omlx_instance_service.py \
  tests/test_ollama_client.py tests/test_main.py -v
```

Expected: PASS with OMLX and Ollama guardrails both covered.

- [ ] **Step 2: Run repository-wide lint and tests**

Run:

```bash
make check
make test
```

Expected:
- `make check` -> `All checks passed!`
- `make test` -> repository suite passes, with live OMLX tests allowed to skip when not configured

- [ ] **Step 3: Review for dead OMLX fallback code**

Before finalizing, inspect `src/material_agent/clients/omlx.py` and related helpers to remove any code paths that still claim OMLX success after non-structured prose drift.

- [ ] **Step 4: Commit final cleanup**

```bash
git add .
git commit -m "refactor(vision): finalize OMLX runtime upgrade"
```

## Notes For Execution

- Keep changes additive until the probe and structured-output path are green.
- Do not try to redesign Ollama beyond minimal fallback safety.
- Do not add old-contract compatibility branches.
- Prefer the smallest runtime-artifact/event additions needed for diagnostics instead of creating new table families.
- Preserve existing passing layered-scoring behavior while changing the OMLX runtime.
