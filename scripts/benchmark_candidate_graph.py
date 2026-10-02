"""Bounded constructed graphs only; no image, model, XMP or runtime-state IO.

Event IDs and directed oracle labels are constructed inputs, never human gold.
The historical module is imported only for its candidate and selector functions.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import sys

# Resolve the sibling explicitly: test order, cwd and PYTHONPATH cannot substitute
# another module called direct_coverage. No historical image functions are called.
_spec = importlib.util.spec_from_file_location(
    "_candidate_graph_historical", Path(__file__).with_name("direct_coverage.py")
)
historical = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = historical
_spec.loader.exec_module(historical)
Protocol = historical.Protocol
historical_candidates = historical.candidates
quality_allows = historical.quality_allows
select = historical.select


SCHEMA = "material-agent.constructed-candidate-graph.v1"
MODES = ("historical", "all_eligible", "per_event")
MAX_FRAMES = 64
MAX_CASES = 32
MAX_INPUT_BYTES = 1_048_576


@dataclass(frozen=True)
class Budget:
    window_seconds: float = 10.0
    global_pairs: int = 4
    event_pairs: int = 4
    max_component_frames: int = 64

    def __post_init__(self):
        if (
            type(self.window_seconds) not in (int, float)
            or not math.isfinite(self.window_seconds)
            or not 0 < self.window_seconds <= 86_400
        ):
            raise ValueError("invalid window_seconds")
        for name in ("global_pairs", "event_pairs", "max_component_frames"):
            value = getattr(self, name)
            maximum = MAX_FRAMES if name == "max_component_frames" else 2016
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"invalid {name}")

    def protocol(self):
        return Protocol(
            window_seconds=self.window_seconds,
            max_pairs=self.global_pairs,
            max_frames=MAX_FRAMES,
            neighbors_forward=3,
        )


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def identifier(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 80
        and all(c.isascii() and (c.isalnum() or c in "_-.") for c in value)
    )


def validate_case(case):
    if not isinstance(case, dict) or set(case) != {"id", "frames", "oracle"}:
        raise ValueError("case requires only id, frames, oracle")
    if not identifier(case["id"]):
        raise ValueError("invalid case id")
    frames = case["frames"]
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError("frame budget exceeded or empty")
    ids = set()
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"id", "event", "seconds", "quality"}:
            raise ValueError("frame requires only id, event, seconds, quality")
        if not identifier(frame["id"]) or not identifier(frame["event"]):
            raise ValueError("invalid frame/event id")
        if frame["id"] in ids:
            raise ValueError("duplicate frame id")
        ids.add(frame["id"])
        seconds = frame["seconds"]
        if seconds is not None and (not finite_number(seconds) or abs(seconds) > 1e9):
            raise ValueError("invalid capture time")
        q = frame["quality"]
        if not isinstance(q, dict) or not set(q) <= {"total", "sharpness", "exposure"}:
            raise ValueError("invalid quality fields")
        if any(v is not None and (not finite_number(v) or not 0 <= v <= 100) for v in q.values()):
            raise ValueError("invalid quality value")
    oracle = case["oracle"]
    if not isinstance(oracle, list) or len(oracle) > len(frames) * (len(frames) - 1):
        raise ValueError("oracle budget exceeded")
    seen = set()
    for edge in oracle:
        if not isinstance(edge, dict) or set(edge) != {"source", "target", "relation"}:
            raise ValueError("invalid oracle fields")
        pair = (edge["source"], edge["target"])
        if any(not identifier(k) or k not in ids for k in pair) or pair[0] == pair[1]:
            raise ValueError("invalid oracle endpoints")
        if pair in seen or edge["relation"] not in ("cover", "different", "unknown"):
            raise ValueError("duplicate or invalid oracle relation")
        seen.add(pair)
    return case


def enumerate_pairs(frames, budget, mode):
    """All policies share time-only eligibility; missing time provides no candidate.

    Each per-event pair is charged to the earlier endpoint's supplied event ID.
    Shortest time distance, then capture time and IDs resolve budget ties. This
    also defines cross-event pairs without pretending to infer event membership.
    """
    if mode not in MODES:
        raise ValueError("invalid mode")
    ordered = sorted(
        (f for f in frames if f["seconds"] is not None), key=lambda f: (f["seconds"], f["id"])
    )
    by_id = {f["id"]: f for f in frames}
    eligible, excluded, forward_rank = [], [], {}
    for a, b in itertools.combinations(sorted(by_id), 2):
        if by_id[a]["seconds"] is None or by_id[b]["seconds"] is None:
            excluded.append({"pair": [a, b], "reason": "missing_time"})
        elif abs(by_id[a]["seconds"] - by_id[b]["seconds"]) > budget.window_seconds:
            excluded.append({"pair": [a, b], "reason": "outside_time_window"})
    for i, frame in enumerate(ordered):
        near = [
            other
            for other in ordered[i + 1 :]
            if other["seconds"] - frame["seconds"] <= budget.window_seconds
        ]
        for rank, other in enumerate(near):
            pair = (frame["id"], other["id"])
            eligible.append(pair)
            forward_rank[pair] = rank
    if mode == "historical":
        # Exact historical function, including cap ordering. Missing-time frames
        # are conservatively isolated by this harness; legacy rejects such input.
        selected, omitted_count = historical_candidates(ordered, budget.protocol())
    elif mode == "all_eligible":
        selected = eligible[:]
    else:
        buckets = defaultdict(list)
        for a, b in eligible:
            buckets[by_id[a]["event"]].append((a, b))
        selected = []
        for event in sorted(buckets):
            pairs = sorted(
                buckets[event],
                key=lambda p: (
                    by_id[p[1]]["seconds"] - by_id[p[0]]["seconds"],
                    by_id[p[0]]["seconds"],
                    p[0],
                    p[1],
                ),
            )
            selected.extend(pairs[: budget.event_pairs])
    chosen = set(selected)
    omitted = [
        {
            "pair": list(pair),
            "reason": (
                "nearest_forward_3"
                if mode == "historical" and forward_rank[pair] >= 3
                else "global_pair_cap"
                if mode == "historical"
                else "per_event_budget"
            ),
        }
        for pair in eligible
        if pair not in chosen
    ]
    if mode == "historical" and len(omitted) != omitted_count:
        raise AssertionError("historical omission accounting mismatch")
    return {
        "eligible": eligible,
        "selected": sorted(selected),
        "omitted": omitted,
        "ineligible": excluded,
    }


def components(frames, pairs, maximum):
    """Undirected temporal eligibility components, including isolated frames."""
    adjacency = {f["id"]: set() for f in frames}
    for a, b in pairs:
        adjacency[a].add(b)
        adjacency[b].add(a)
    unseen, result = set(adjacency), []
    while unseen:
        pending, found = [min(unseen)], set()
        while pending:
            node = pending.pop()
            if node in found:
                continue
            found.add(node)
            if len(found) > maximum:
                raise ValueError("component budget exceeded")
            pending.extend(adjacency[node] - found)
        unseen -= found
        result.append(sorted(found))
    return result


def evaluate(case, budget, mode):
    validate_case(case)
    frames = case["frames"]
    pairs = enumerate_pairs(frames, budget, mode)
    groups = components(frames, pairs["eligible"], budget.max_component_frames)
    labels = {(e["source"], e["target"]): e["relation"] for e in case["oracle"]}
    edges = {}
    for a, b in pairs["selected"]:
        for pair in ((a, b), (b, a)):
            edges[pair] = {
                "relation": labels.get(pair, "unknown"),
                "reason": "constructed_label" if pair in labels else "missing_relation",
            }
    protocol = budget.protocol()
    full = select(frames, edges, protocol)
    recomputed = {}
    for group in groups:
        members = set(group)
        recomputed.update(
            select(
                [f for f in frames if f["id"] in members],
                {p: e for p, e in edges.items() if p[0] in members and p[1] in members},
                protocol,
            )
        )
    by_id = {f["id"]: f for f in frames}
    witnesses, violations = [], []
    for target, decision in full.items():
        if decision["decision"] != "reject":
            continue
        source = decision["covered_by"]
        valid = (
            full[source]["decision"] == "keep"
            and edges.get((source, target), {}).get("relation") == "cover"
            and quality_allows(by_id[source]["quality"], by_id[target]["quality"], protocol)
        )
        witnesses.append(
            {
                "source": source,
                "target": target,
                "relation": edges[source, target]["relation"],
                "quality_allows": valid,
                "label_origin": "constructed",
            }
        )
        if not valid:
            violations.append(target)
    selected_directions = set(edges)
    reachable = sum(labels.get(p) == "cover" for p in selected_directions)
    eligible_directions = {p for a, b in pairs["eligible"] for p in ((a, b), (b, a))}
    return {
        **pairs,
        "counts": {
            "eligible": len(pairs["eligible"]),
            "selected": len(pairs["selected"]),
            "omitted": len(pairs["omitted"]),
            "omitted_reasons": dict(Counter(e["reason"] for e in pairs["omitted"])),
            "reachable_constructed_cover_directions": reachable,
            "eligible_constructed_cover_directions": sum(
                labels.get(p) == "cover" for p in eligible_directions
            ),
        },
        "relations": [{"source": a, "target": b, **e} for (a, b), e in sorted(edges.items())],
        "decisions": full,
        "direct_witnesses": witnesses,
        "witness_violations": violations,
        "components": groups,
        "max_component_frames": max(map(len, groups)),
        "component_recompute_equals_full_selection": recomputed == full,
    }


def run_manifest(manifest, budget):
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema", "label_origin", "cases"}
        or manifest["schema"] != SCHEMA
        or manifest["label_origin"] != "constructed"
    ):
        raise ValueError("invalid constructed manifest")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("case budget exceeded")
    for case in cases:
        validate_case(case)
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("duplicate case id")
    results = []
    for case in cases:
        modes = {mode: evaluate(case, budget, mode) for mode in MODES}
        oracle = modes["all_eligible"]["decisions"]
        for mode, value in modes.items():
            value["equals_all_eligible_oracle_selection"] = value["decisions"] == oracle
            value["decision_differences_from_all_eligible"] = sorted(
                k for k in oracle if oracle[k] != value["decisions"][k]
            )
        results.append({"id": case["id"], "modes": modes})
    return {
        "schema": SCHEMA,
        "label_origin": "constructed",
        "budget": asdict(budget),
        "limits": {
            "max_frames": MAX_FRAMES,
            "max_cases": MAX_CASES,
            "max_input_bytes": MAX_INPUT_BYTES,
        },
        "scope": "Structural constructed graphs only; G1 pending; full G2 not established.",
        "cases": results,
    }


def check_invariants(case, budget):
    """Bounded exhaustive permutations (<= 6 frames), otherwise 12 seeded shuffles."""
    frames = case["frames"]
    if len(frames) <= 6:
        orders = itertools.permutations(frames)
    else:
        rng = random.Random(20260927)
        orders = [rng.sample(frames, len(frames)) for _ in range(12)]
    expected = {m: evaluate(case, budget, m) for m in MODES}
    count = 0
    for order in orders:
        shuffled = {**case, "frames": list(order), "oracle": list(reversed(case["oracle"]))}
        for mode in MODES:
            if evaluate(shuffled, budget, mode) != expected[mode]:
                raise AssertionError(f"permutation instability: {case['id']} {mode}")
        count += 1
    return {"permutations_checked": count, "exhaustive": len(frames) <= 6}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--window-seconds", type=float, default=10)
    parser.add_argument("--global-pairs", type=int, default=4)
    parser.add_argument("--event-pairs", type=int, default=4)
    parser.add_argument("--max-component-frames", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        budget = Budget(
            args.window_seconds, args.global_pairs, args.event_pairs, args.max_component_frames
        )
        source, output = args.manifest.resolve(), args.output_dir.resolve()
        # A fresh directory prevents clobbering inputs, reports, symlinks or hardlinks.
        if output.exists() or output == source or output in source.parents:
            raise ValueError("output directory must be new and must not contain the manifest")
        with source.open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("manifest byte budget exceeded")
        result = run_manifest(json.loads(raw), budget)
        for case, case_result in zip(json.loads(raw)["cases"], result["cases"], strict=True):
            case_result["permutation_check"] = check_invariants(case, budget)
        if any(
            v["witness_violations"] or not v["component_recompute_equals_full_selection"]
            for c in result["cases"]
            for v in c["modes"].values()
        ):
            raise ValueError("structural invariant failed")
        result["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        result["historical_script_sha256"] = hashlib.sha256(
            Path(__file__).with_name("direct_coverage.py").read_bytes()
        ).hexdigest()
        encoded = json.dumps(result, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n"
        output.mkdir(parents=True, exist_ok=False)
        (output / "results.json").write_text(encoded)
        print(
            json.dumps(
                {
                    "cases": len(result["cases"]),
                    "result": str(output / "results.json"),
                    "scope": result["scope"],
                }
            )
        )
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
