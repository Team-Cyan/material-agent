"""Constructed graph regressions; no source image or inference required."""

from copy import deepcopy
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_candidate_graph", ROOT / "scripts/benchmark_candidate_graph.py"
)
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)

MANIFEST = (
    ROOT / "docs/operations/benchmarks/2026-09-27-reference-tooling/candidate-graph/manifest.json"
)
CASES = {c["id"]: c for c in json.loads(MANIFEST.read_text())["cases"]}
BUDGET = m.Budget()


def evaluate(key, mode="all_eligible", budget=BUDGET):
    return m.evaluate(deepcopy(CASES[key]), budget, mode)


@pytest.mark.parametrize("case", list(CASES.values()), ids=list(CASES))
def test_all_permutations_and_seeded_shuffles(case):
    result = m.check_invariants(case, BUDGET)
    assert result["exhaustive"]
    assert result["permutations_checked"] == math.factorial(len(case["frames"]))


def test_larger_fixture_uses_reproducible_shuffle_check():
    case = deepcopy(CASES["global_cap_after"])
    case["frames"].append(dict(id="z", event="far", seconds=500, quality={}))
    assert m.check_invariants(case, BUDGET) == {"permutations_checked": 12, "exhaustive": False}


def test_historical_cap_displaces_disconnected_event_but_new_modes_do_not():
    before = evaluate("global_cap_before", "historical")
    after = evaluate("global_cap_after", "historical")
    assert ("b", "c") in before["selected"]
    assert ("b", "c") not in after["selected"]
    assert {"pair": ["b", "c"], "reason": "global_pair_cap"} in after["omitted"]
    assert before["decisions"]["c"]["covered_by"] == "b"
    assert after["decisions"]["c"]["decision"] == "keep"
    for mode in ("all_eligible", "per_event"):
        before, after = evaluate("global_cap_before", mode), evaluate("global_cap_after", mode)
        assert set(before["selected"]) <= set(after["selected"])
        assert all(after["decisions"][k] == d for k, d in before["decisions"].items())


@pytest.mark.parametrize("mode", ["all_eligible", "per_event"])
def test_unrelated_event_insertion_both_time_directions(mode):
    for case in CASES.values():
        baseline = m.evaluate(case, BUDGET, mode)
        for start in (-100, 1000):
            inserted = deepcopy(case)
            inserted["frames"] += [
                dict(
                    id=f"extra-{i}",
                    event="unrelated",
                    seconds=start + i,
                    quality=dict(total=99, sharpness=50, exposure=50),
                )
                for i in range(3)
            ]
            after = m.evaluate(inserted, BUDGET, mode)
            old_ids = {f["id"] for f in case["frames"]}
            assert baseline["selected"] == [p for p in after["selected"] if set(p) <= old_ids]
            assert baseline["decisions"] == {k: after["decisions"][k] for k in old_ids}


def test_nearest_three_is_separate_from_global_cap():
    result = evaluate("nearest_three_omission", "historical", m.Budget(global_pairs=100))
    assert result["omitted"] == [{"pair": ["a", "e"], "reason": "nearest_forward_3"}]
    assert result["decisions"]["e"]["decision"] == "keep"
    assert evaluate("nearest_three_omission")["decisions"]["e"]["covered_by"] == "a"


def test_chain_is_not_transitive_and_keeper_deletion_recomputes_witness():
    before, after = evaluate("chain"), evaluate("keeper_deleted")
    assert before["decisions"]["b"] == dict(decision="reject", covered_by="a")
    assert before["decisions"]["c"]["decision"] == "keep"
    assert after["decisions"]["b"]["decision"] == "keep"
    assert after["decisions"]["c"] == dict(decision="reject", covered_by="b")
    assert all(w["source"] != "a" for w in after["direct_witnesses"])


def test_cycle_tie_uses_stable_id_and_does_not_reject_all():
    result = evaluate("cycle_tied")
    assert result["decisions"] == {
        "a": dict(decision="keep", covered_by=None),
        "b": dict(decision="reject", covered_by="a"),
        "c": dict(decision="keep", covered_by=None),
    }


def test_missing_quality_and_unique_low_score_are_kept():
    assert all(d["decision"] == "keep" for d in evaluate("missing_quality")["decisions"].values())
    result = evaluate("low_unique_high_duplicate")
    assert result["decisions"]["a"]["decision"] == "keep"
    assert result["decisions"]["c"]["covered_by"] == "b"


def test_unknown_missing_and_unevaluated_labels_never_become_witness():
    result = evaluate("unknown_and_missing_time")
    assert all(d["decision"] == "keep" for d in result["decisions"].values())
    assert result["relations"] == [
        dict(source="a", target="b", relation="unknown", reason="constructed_label"),
        dict(source="b", target="a", relation="unknown", reason="missing_relation"),
    ]
    result = evaluate("nearest_three_omission", "per_event", m.Budget(event_pairs=1))
    assert result["decisions"]["e"]["decision"] == "keep"
    assert not result["direct_witnesses"]


def test_unknown_does_not_override_an_independent_direct_witness():
    case = deepcopy(CASES["cycle_tied"])
    case["oracle"] = [
        dict(source="a", target="c", relation="unknown"),
        dict(source="b", target="c", relation="cover"),
    ]
    result = m.evaluate(case, BUDGET, "all_eligible")
    assert result["decisions"]["c"]["covered_by"] == "b"


def test_cross_event_pairs_share_temporal_eligibility_and_have_one_budget_owner():
    case = deepcopy(CASES["cycle_tied"])
    for f in case["frames"]:
        f["event"] = f["id"]
    bounded = m.evaluate(case, m.Budget(event_pairs=1), "per_event")
    oracle = m.evaluate(case, BUDGET, "all_eligible")
    assert bounded["eligible"] == oracle["eligible"]
    assert bounded["selected"] == [("a", "b"), ("b", "c")]
    assert bounded["omitted"] == [{"pair": ["a", "c"], "reason": "per_event_budget"}]


def test_bridge_merge_split_and_growth_match_full_recomputation():
    before, merged, split = [
        evaluate(k) for k in ("bridge_before", "bridge_inserted", "bridge_removed")
    ]
    assert before["components"] == [["a", "b"], ["c", "d"]]
    assert merged["components"] == [["a", "b", "c", "d", "x"]]
    assert [r["max_component_frames"] for r in (before, merged, split)] == [2, 5, 2]
    assert split == before
    assert merged["decisions"]["d"]["decision"] == "keep"  # rejected c cannot witness d
    for result in (before, merged, split):
        assert result["component_recompute_equals_full_selection"]
    with pytest.raises(ValueError, match="component budget"):
        evaluate("bridge_inserted", budget=m.Budget(max_component_frames=4))


def test_selection_cascades_beyond_fixed_radius():
    before, after = evaluate("selection_cascade_before"), evaluate("selection_cascade_after")
    assert before["decisions"]["d"]["covered_by"] == "c"
    assert after["decisions"]["d"]["decision"] == "keep"
    assert after["decisions"]["c"]["covered_by"] == "b"


def test_complete_budget_equals_uncapped_oracle_and_reports_cap_loss():
    manifest = json.loads(MANIFEST.read_text())
    result = m.run_manifest(manifest, m.Budget(global_pairs=2016, event_pairs=2016))
    assert all(
        c["modes"]["per_event"]["equals_all_eligible_oracle_selection"] for c in result["cases"]
    )
    result = m.run_manifest(manifest, BUDGET)
    omission = next(c for c in result["cases"] if c["id"] == "nearest_three_omission")
    assert not omission["modes"]["per_event"]["equals_all_eligible_oracle_selection"]
    assert omission["modes"]["per_event"]["decision_differences_from_all_eligible"] == ["e"]


def test_seeded_graphs_component_oracle_and_witness_quality():
    rng = random.Random(52)
    for _ in range(24):
        frames = [
            dict(
                id=f"p{i}",
                event=f"event{i // 4}",
                seconds=(i // 4) * 100 + rng.randrange(20),
                quality=dict(total=rng.randrange(100), sharpness=50, exposure=50),
            )
            for i in range(12)
        ]
        case = dict(
            id="random",
            frames=frames,
            oracle=[
                dict(
                    source=a["id"],
                    target=b["id"],
                    relation=rng.choice(["cover", "different", "unknown"]),
                )
                for a, b in itertools.permutations(frames, 2)
            ],
        )
        for mode in m.MODES:
            result = m.evaluate(case, BUDGET, mode)
            assert result["component_recompute_equals_full_selection"]
            assert result["witness_violations"] == []
            assert result["counts"]["eligible"] == (
                result["counts"]["selected"] + result["counts"]["omitted"]
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("window_seconds", float("nan")),
        ("window_seconds", float("inf")),
        ("window_seconds", -1),
        ("window_seconds", True),
        ("window_seconds", 86401),
        ("global_pairs", 0),
        ("global_pairs", 1.5),
        ("global_pairs", 2017),
        ("event_pairs", -1),
        ("event_pairs", True),
        ("max_component_frames", 65),
    ],
)
def test_invalid_parameters_fail_closed(field, value):
    with pytest.raises(ValueError):
        m.Budget(**{field: value})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["frames"].append(c["frames"][0]),
        lambda c: c["frames"][0].update(seconds=float("inf")),
        lambda c: c["frames"][0].update(rgb="forbidden"),
        lambda c: c["frames"][0]["quality"].update(total=True),
        lambda c: c["frames"][0]["quality"].update(total=float("nan")),
        lambda c: c["oracle"].append(c["oracle"][0]),
        lambda c: c["oracle"][0].update(target="missing"),
        lambda c: c.update(frames=c["frames"] * 30),
    ],
)
def test_invalid_graphs_fail_closed(mutation):
    case = deepcopy(CASES["chain"])
    mutation(case)
    with pytest.raises(ValueError):
        m.evaluate(case, BUDGET, "all_eligible")


def test_cli_reproducible_and_input_safe(tmp_path):
    before = MANIFEST.read_bytes()
    command = [
        sys.executable,
        str(ROOT / "scripts/benchmark_candidate_graph.py"),
        "--manifest",
        str(MANIFEST),
        "--output-dir",
    ]
    outputs = []
    for name in ("first", "second"):
        completed = subprocess.run(command + [str(tmp_path / name)], capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
        outputs.append((tmp_path / name / "results.json").read_bytes())
    assert outputs[0] == outputs[1]
    assert MANIFEST.read_bytes() == before
    for output in (MANIFEST, MANIFEST.parent, tmp_path / "first"):
        completed = subprocess.run(command + [str(output)], capture_output=True, text=True)
        assert completed.returncode == 2
        assert "output directory must be new" in completed.stderr
    link = tmp_path / "alias"
    link.symlink_to(MANIFEST.parent, target_is_directory=True)
    assert subprocess.run(command + [str(link)], capture_output=True).returncode == 2
    assert MANIFEST.read_bytes() == before


def test_cli_invalid_input_creates_no_output(tmp_path):
    source, out = tmp_path / "invalid.json", tmp_path / "out"
    source.write_bytes(b" " * (m.MAX_INPUT_BYTES + 1))
    with pytest.raises(SystemExit) as exc:
        m.main(["--manifest", str(source), "--output-dir", str(out)])
    assert exc.value.code == 2
    assert not out.exists()


def test_no_photo_model_or_runtime_calls(monkeypatch):
    legacy = m.historical

    def forbidden(*args, **kwargs):
        pytest.fail("image/inference path called")

    for name in ("prepare", "relation", "run"):
        monkeypatch.setattr(legacy, name, forbidden)
    result = m.run_manifest(json.loads(MANIFEST.read_text()), BUDGET)
    assert result["label_origin"] == "constructed"
