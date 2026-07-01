# Localize Final Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove model-owned overall scores from both full scoring and fast screening so the model only returns signals, while local rules own final scoring and keep/review/reject decisions.

**Architecture:** Keep the existing three-stage pipeline shape, but tighten responsibilities. Full-score requests return scene plus dimension values only; fast screening returns a small risk/usability signal object; local domain code converts those signals into `screening_prior`, final `total_score`, and `decision`.

**Tech Stack:** Python, pytest, OMLX/Ollama structured JSON contracts, SQLite state, `uv`, `make`

---

## File Map

**Modify**
- `src/material_agent/clients/prompts.py`
- `src/material_agent/clients/protocol.py`
- `src/material_agent/clients/omlx.py`
- `src/material_agent/clients/ollama.py`
- `src/material_agent/domain/scoring_engine.py`
- `src/material_agent/domain/layered_decision.py`
- `src/material_agent/adapters/models/omlx/contracts.py`
- `src/material_agent/utils/config_validator.py`
- `config.yaml`
- `README.md`
- `tests/test_architecture_refine.py`
- `tests/test_musiq_screening.py`
- `tests/test_pipeline.py`
- `tests/test_rescore.py`
- `tests/test_main.py`

**Optional modify if needed after red tests expose coupling**
- `src/material_agent/app/review_runtime.py`
- `src/material_agent/app/omlx_harness_service.py`
- `tests/test_omlx_harness.py`

**Create**
- No new production file required unless fast-screening signal parsing becomes too large; if so, create `src/material_agent/domain/fast_screening.py` and matching tests.

---

### Task 1: Lock In Contract Expectations With Failing Tests

**Files:**
- Modify: `tests/test_architecture_refine.py`
- Modify: `tests/test_musiq_screening.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests for full-score contract ownership**

```python
def test_async_omlx_full_request_schema_does_not_require_overall():
    client = AsyncOMLXClient(base_url="http://localhost:11434", model="Qwen", api_key=None)
    payload = client._build_full_request_payload(b"jpeg")
    schema = payload["response_format"]["json_schema"]["schema"]

    assert "overall" not in schema["properties"]
    assert "overall" not in schema["required"]
    assert "scene" in schema["required"]
    assert "composition" in schema["required"]


def test_compute_scores_ignores_model_overall_for_final_score():
    class _FakeClient:
        async def score_image(self, _jpeg_bytes):
            return {
                "overall": 9.9,
                "scene": "animal",
                "scene_raw": "动物",
                "composition": 6.0,
                "lighting": 6.0,
                "color": 6.0,
                "clarity": 6.0,
                "depth": 6.0,
                "mood": 6.0,
                "subject": 6.0,
            }

    bundle = asyncio.run(compute_scores(_fake_frame(), _FakeClient(), _config(), fast_screening=None))

    assert bundle.total < 9.9
    assert bundle.scores["composition"] == 6.0
```

- [ ] **Step 2: Write the failing tests for fast-screening signal ownership**

```python
def test_parse_fast_screening_requires_signal_object_not_overall():
    data = parse_fast_screening(
        '{"technical_ok": 0.2, "subject_clear": 0.4, "composition_ok": 0.3, "usable_for_selection": 0.1}'
    )
    assert data["technical_ok"] == 0.2
    assert "overall" not in data


def test_compute_scores_uses_fast_screening_signals_as_prior_not_final_total():
    class _FastPort:
        async def score_image_fast(self, _jpeg_bytes):
            return {
                "technical_ok": 0.1,
                "subject_clear": 0.2,
                "composition_ok": 0.2,
                "usable_for_selection": 0.1,
            }

    class _FullClient:
        async def score_image(self, _jpeg_bytes):
            return {
                "scene": "animal",
                "scene_raw": "动物",
                "composition": 7.0,
                "lighting": 7.0,
                "color": 7.0,
                "clarity": 7.0,
                "depth": 7.0,
                "mood": 7.0,
                "subject": 7.0,
            }

    bundle = asyncio.run(compute_scores(_fake_frame(), _FullClient(), _config(), fast_screening=_FastPort()))

    assert bundle.screening_prior is not None
    assert bundle.total != bundle.screening_prior
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
uv run python -m pytest \
  tests/test_architecture_refine.py \
  tests/test_musiq_screening.py \
  tests/test_pipeline.py -q
```

Expected:
- FAIL because the full-score schema still requires `overall`
- FAIL because fast-screening parsing still expects a single `overall`

- [ ] **Step 4: Commit the red test baseline**

```bash
git add tests/test_architecture_refine.py tests/test_musiq_screening.py tests/test_pipeline.py
git commit -m "test(scorer): capture local scoring ownership rules"
```

---

### Task 2: Remove `overall` From Full-Score Contracts

**Files:**
- Modify: `src/material_agent/clients/prompts.py`
- Modify: `src/material_agent/clients/protocol.py`
- Modify: `src/material_agent/clients/omlx.py`
- Modify: `src/material_agent/clients/ollama.py`
- Modify: `src/material_agent/adapters/models/omlx/contracts.py`
- Test: `tests/test_architecture_refine.py`

- [ ] **Step 1: Write the minimal implementation for full-score prompts and schema**

```python
FULL_SCORE_REQUIRED_FIELDS = [
    "scene",
    "scene_raw",
    "composition",
    "lighting",
    "color",
    "clarity",
    "depth",
    "mood",
    "subject",
]
```

Update the full-score prompt text so it says:

```text
Return only the requested scene label and per-dimension scores.
Do not return an overall / rating / final total score.
```

Update the full-score JSON schema so:
- `overall` is removed from `properties`
- `overall` is removed from `required`
- the vision dimensions plus `scene` stay required

- [ ] **Step 2: Keep backward compatibility in parsing without trusting `overall`**

```python
def parse_full_score(data: dict) -> dict:
    parsed = {
        "scene": normalize_scene(data.get("scene")),
        "scene_raw": normalize_scene_raw(data.get("scene_raw")),
    }
    for dim in VISION_DIMS:
        parsed[dim] = clamp_score(data.get(dim, 0.0))
    return parsed
```

Implementation rules:
- ignore `overall` if it appears
- do not fail only because `overall` is present
- still fail if required per-dimension data is missing or malformed

- [ ] **Step 3: Run the focused tests**

Run:
```bash
uv run python -m pytest tests/test_architecture_refine.py -q
```

Expected:
- PASS for schema/prompt tests
- PASS for compatibility tests that still include legacy `overall`

- [ ] **Step 4: Commit**

```bash
git add \
  src/material_agent/clients/prompts.py \
  src/material_agent/clients/protocol.py \
  src/material_agent/clients/omlx.py \
  src/material_agent/clients/ollama.py \
  src/material_agent/adapters/models/omlx/contracts.py \
  tests/test_architecture_refine.py
git commit -m "refactor(vision): drop overall from full-score contracts"
```

---

### Task 3: Replace Fast-Screening `overall` With Screening Signals

**Files:**
- Modify: `src/material_agent/clients/prompts.py`
- Modify: `src/material_agent/clients/protocol.py`
- Modify: `src/material_agent/clients/omlx.py`
- Modify: `src/material_agent/clients/ollama.py`
- Modify: `src/material_agent/domain/scoring_engine.py`
- Test: `tests/test_architecture_refine.py`
- Test: `tests/test_musiq_screening.py`

- [ ] **Step 1: Define the screening signal schema in tests and prompt text**

Use this target shape:

```json
{
  "technical_ok": 0.0,
  "subject_clear": 0.0,
  "composition_ok": 0.0,
  "usable_for_selection": 0.0
}
```

Signal meanings:
- `technical_ok`: quick confidence that exposure/focus/noise are acceptable
- `subject_clear`: quick confidence that the intended subject is readable
- `composition_ok`: quick confidence that framing is not obviously weak
- `usable_for_selection`: quick confidence the frame is worth full scoring

- [ ] **Step 2: Implement parsing and prompt/schema changes**

```python
FAST_SIGNAL_KEYS = (
    "technical_ok",
    "subject_clear",
    "composition_ok",
    "usable_for_selection",
)


def parse_fast_screening(text: str | dict) -> dict[str, float]:
    data = ensure_json_object(text)
    return {
        key: clamp_score01(data.get(key, 0.0))
        for key in FAST_SIGNAL_KEYS
    }
```

Implementation rules:
- remove fast-schema `overall`
- reject bare numeric JSON like `{"overall": 6.2}`
- accept only the signal object

- [ ] **Step 3: Convert signal object into a local `screening_prior`**

```python
def screening_prior_from_signals(signals: dict[str, float]) -> float:
    return round(
        signals["technical_ok"] * 0.35
        + signals["subject_clear"] * 0.30
        + signals["composition_ok"] * 0.15
        + signals["usable_for_selection"] * 0.20,
        4,
    )
```

Implementation rules:
- keep this in local code only
- use it for tier-2 reject and downstream `screening_prior`
- do not surface it as final `total_score`

- [ ] **Step 4: Run focused tests**

Run:
```bash
uv run python -m pytest \
  tests/test_architecture_refine.py \
  tests/test_musiq_screening.py -q
```

Expected:
- PASS for new fast-screening parse tests
- PASS for score-compute tests showing `screening_prior` is derived locally

- [ ] **Step 5: Commit**

```bash
git add \
  src/material_agent/clients/prompts.py \
  src/material_agent/clients/protocol.py \
  src/material_agent/clients/omlx.py \
  src/material_agent/clients/ollama.py \
  src/material_agent/domain/scoring_engine.py \
  tests/test_architecture_refine.py \
  tests/test_musiq_screening.py
git commit -m "refactor(scorer): replace fast overall with screening signals"
```

---

### Task 4: Make Local Rules the Only Source of Final Total and Decision

**Files:**
- Modify: `src/material_agent/domain/scoring_engine.py`
- Modify: `src/material_agent/domain/layered_decision.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_rescore.py`

- [ ] **Step 1: Add failing tests for local-only final scoring**

```python
def test_compute_scores_total_is_derived_from_local_layered_summary():
    bundle = asyncio.run(compute_scores(_fake_frame(), _full_client_with_legacy_overall(), _config()))

    assert bundle.policy_version == "layered-v1"
    assert bundle.total == bundle.extra["layered_total"]
    assert bundle.total != 9.9


def test_rescore_service_matches_full_run_when_model_overall_is_ignored():
    summary = run_rescore_fixture(...)
    assert summary.total_score == expected_local_total
```

- [ ] **Step 2: Implement the minimal scoring ownership cleanup**

```python
summary = summarize_signals(signals, scene=scene, config=config)
local_total = summary.total_score

return ScoreBundle(
    scores=scores,
    total=local_total,
    boosted=False,
    meta=meta,
    scene=scene,
    scene_raw=scene_raw,
    instructions=instructions,
    decision=summary.decision,
    decision_reasons=summary.decision_reasons,
    screening_prior=summary.screening_prior,
    visible_breakdown=summary.visible_breakdown,
    policy_version=summary.policy_version,
    signals=signals,
    extra={"aggregated_total": total, "layered_total": local_total},
)
```

Implementation rules:
- the aggregator result may remain as an intermediate input
- only the local layered summary owns the final `ScoreBundle.total`
- no model-provided single-number score may override `bundle.total`

- [ ] **Step 3: Run focused tests**

Run:
```bash
uv run python -m pytest tests/test_pipeline.py tests/test_rescore.py -q
```

Expected:
- PASS
- rescore stays consistent with the runtime path

- [ ] **Step 4: Commit**

```bash
git add \
  src/material_agent/domain/scoring_engine.py \
  src/material_agent/domain/layered_decision.py \
  tests/test_pipeline.py \
  tests/test_rescore.py
git commit -m "refactor(scorer): localize final score and decision"
```

---

### Task 5: Config, CLI, and Harness Compatibility

**Files:**
- Modify: `src/material_agent/utils/config_validator.py`
- Modify: `config.yaml`
- Modify: `tests/test_main.py`
- Optional modify: `src/material_agent/app/omlx_harness_service.py`
- Optional test: `tests/test_omlx_harness.py`

- [ ] **Step 1: Write failing tests for config compatibility**

```python
def test_normalize_config_sets_fast_vision_schema_to_signal_contract():
    cfg = normalize_config({})
    assert cfg["omlx"]["requests"]["fast_vision_schema"] == "material_agent.fast_screening_signals"


def test_legacy_full_score_payload_with_overall_remains_tolerated():
    parsed = parse_full_score({"overall": 7.8, "scene": "animal", ...})
    assert parsed["scene"] == "animal"
```

- [ ] **Step 2: Update config defaults and compatibility rules**

Rules:
- full-score schema name stays stable unless transport requires a new name
- fast-score schema should be renamed to reflect signals, for example `material_agent.fast_screening_signals`
- config normalization may alias old names to the new signal contract for one release window

- [ ] **Step 3: Check harness/report consumers**

If any harness output assumes fast/full `overall`, update it to:
- treat fast output as signals only
- keep final judged `total_score` from processed state unchanged

- [ ] **Step 4: Run focused tests**

Run:
```bash
uv run python -m pytest tests/test_main.py tests/test_omlx_harness.py -q
```

Expected:
- PASS
- no CLI/config regression

- [ ] **Step 5: Commit**

```bash
git add \
  src/material_agent/utils/config_validator.py \
  config.yaml \
  tests/test_main.py \
  src/material_agent/app/omlx_harness_service.py \
  tests/test_omlx_harness.py
git commit -m "fix(config): align runtime defaults with local scoring ownership"
```

---

### Task 6: Docs and End-to-End Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update docs**

Document these behavior changes:
- the model no longer returns a trusted final total score
- fast screening returns local screening signals, not a one-number rating
- final `keep / review / reject` comes from local rules

- [ ] **Step 2: Run full verification**

Run:
```bash
make test
```

Expected:
- `401+` tests pass
- no new failures in OMLX contract, pipeline, or state paths

- [ ] **Step 3: Smoke-check runtime help text**

Run:
```bash
uv run material-agent --help
uv run material-agent run --help
```

Expected:
- commands still load normally
- no import-time crash

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(scorer): document local scoring ownership"
```

---

## Self-Review

### Spec coverage
- Full-score no longer trusts model `overall`: covered by Tasks 1, 2, 4
- Fast screening no longer uses `overall`: covered by Tasks 1, 3, 5
- Final scoring and decision remain local: covered by Task 4
- Compatibility with runtime/config/tests: covered by Task 5
- Documentation and verification: covered by Task 6

### Placeholder scan
- No `TODO`, `TBD`, or “write tests for above” placeholders remain.

### Type consistency
- `screening_prior` remains the local field name throughout.
- `score_total` remains the runtime payload field name throughout.
- Full-score output remains dimension-based and scene-based only.

