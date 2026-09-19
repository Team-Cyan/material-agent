"""Validate blinded spatial references and assess feasibility without algorithm scores."""

import argparse
import hashlib
import json
import math
from pathlib import Path


IMPORTANCE = {"important", "nuisance", "preference_dependent", "unknown"}
CATEGORIES = {
    "water",
    "foliage",
    "illumination",
    "gesture",
    "expression",
    "object",
    "registration",
    "other",
}


def validate_panel(rows, panel, count):
    if len(rows) != count:
        raise ValueError("incomplete panel")
    for i, row in enumerate(rows):
        ids = [f"{panel}{i + 1:02}L", f"{panel}{i + 1:02}R"]
        if row["ids"] != ids or row["reference_source"] != "model_generated":
            raise ValueError("invalid neutral ids/provenance")
        if (
            row["same_scene"] not in {"yes", "no", "unknown"}
            or type(row["preference_required"]) is not bool
        ):
            raise ValueError("invalid scene/preference value")
        directions = set()
        for relation in row["directed_relations"]:
            key = (relation["source"], relation["target"])
            directions.add(key)
            if relation["reference"] not in {"cover", "different", "unknown"}:
                raise ValueError("invalid relation label")
            confidence(relation["confidence"])
        if (
            directions != {(ids[0], ids[1]), (ids[1], ids[0])}
            or len(row["directed_relations"]) != 2
        ):
            raise ValueError("need both unique directions")
        for region in row["regions"]:
            if region["importance"] not in IMPORTANCE or region["category"] not in CATEGORIES:
                raise ValueError("invalid region label")
            if region["visibility"] not in {"clear", "limited", "not_observable"}:
                raise ValueError("invalid visibility")
            confidence(region["confidence"])
            for key in ["left_box", "right_box"]:
                b = region[key]
                if b is None:
                    continue
                if (
                    len(b) != 4
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
                        for v in b
                    )
                    or b[0] >= b[2]
                    or b[1] >= b[3]
                ):
                    raise ValueError("invalid normalized box")


def confidence(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("invalid confidence")


def iou(a, b):
    if a is None or b is None:
        return 0.0
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - area
    return area / union if union > 0 else 0.0


def assess(inputs, panel_a, panel_b):
    pairs = inputs["pairs"]
    n = len(pairs)
    validate_panel(panel_a, "A", n)
    validate_panel(panel_b, "B", n)
    out = []
    for i, pair in enumerate(pairs):
        a = panel_a[i]
        b = panel_b[n - 1 - i]
        agreed = []
        matches = []
        for ia, ra in enumerate(a["regions"]):
            for ib, rb in enumerate(b["regions"]):
                overlap = min(
                    iou(ra["left_box"], rb["right_box"]), iou(ra["right_box"], rb["left_box"])
                )
                if (
                    ra["category"] == rb["category"]
                    and ra["importance"] == rb["importance"]
                    and min(ra["confidence"], rb["confidence"]) >= 0.75
                    and ra["visibility"] == rb["visibility"] == "clear"
                    and overlap >= 0.3
                ):
                    matches.append((overlap, ia, ib))
        used_a = set()
        used_b = set()
        for overlap, ia, ib in sorted(matches, reverse=True):
            if ia in used_a or ib in used_b:
                continue
            used_a.add(ia)
            used_b.add(ib)
            ra = a["regions"][ia]
            rb = b["regions"][ib]
            agreed.append(
                {
                    "a_region": ia,
                    "b_region": ib,
                    "category": ra["category"],
                    "importance": ra["importance"],
                    "minimum_box_iou": overlap,
                    "minimum_confidence": min(ra["confidence"], rb["confidence"]),
                }
            )
        relations = []
        for source_side, target_side in [("L", "R"), ("R", "L")]:
            ar = next(r for r in a["directed_relations"] if r["source"].endswith(source_side))
            br = next(r for r in b["directed_relations"] if r["source"].endswith(target_side))
            label = (
                ar["reference"]
                if ar["reference"] == br["reference"]
                and min(ar["confidence"], br["confidence"]) >= 0.75
                else "unknown"
            )
            relations.append(
                {
                    "source_side_in_a": source_side,
                    "target_side_in_a": target_side,
                    "reference": label,
                    "a_reference": ar["reference"],
                    "b_reference": br["reference"],
                    "minimum_confidence": min(ar["confidence"], br["confidence"]),
                }
            )
        pref = any(
            p["preference_required"]
            or any(r["importance"] == "preference_dependent" for r in p["regions"])
            for p in [a, b]
        )
        out.append(
            {
                "pair_id": pair["pair_id"],
                "scene_id": pair["scene_id"],
                "preference_required_by_either": pref,
                "agreed_regions": agreed,
                "unmatched_a_regions": sorted(set(range(len(a["regions"]))) - used_a),
                "unmatched_b_regions": sorted(set(range(len(b["regions"]))) - used_b),
                "relations": relations,
            }
        )
    important = [
        x["pair_id"]
        for x in out
        if any(r["importance"] == "important" for r in x["agreed_regions"])
    ]
    nuisance = [
        x["pair_id"] for x in out if any(r["importance"] == "nuisance" for r in x["agreed_regions"])
    ]
    categories = {
        r["category"]
        for x in out
        for r in x["agreed_regions"]
        if r["importance"] in {"important", "nuisance"}
    }
    groups = {
        "water_or_foliage": bool(categories & {"water", "foliage"}),
        "illumination_or_encoding": "illumination" in categories,
        "gesture_or_expression": bool(categories & {"gesture", "expression"}),
        "object_state_or_identity": "object" in categories,
    }
    pref_count = sum(x["preference_required_by_either"] for x in out)
    scenes = len({x["scene_id"] for x in out})
    reference_gaps = []
    for missing, reason in [
        (not 12 <= n <= 24, "sample_count"),
        (scenes < 4, "scene_diversity"),
        (len(important) < 2, "important_regions"),
        (len(nuisance) < 2, "nuisance_regions"),
        (not all(groups.values()), "category_coverage"),
    ]:
        if missing:
            reference_gaps.append(reason)
    preference_blocked = pref_count > n / 2
    blockers = (["reference_insufficient"] if reference_gaps else []) + (
        ["preference_blocked"] if preference_blocked else []
    )
    passed = not blockers
    return {
        "pairs": out,
        "summary": {
            "pair_count": n,
            "distinct_scene_sources": scenes,
            "preference_required_pairs": pref_count,
            "agreed_important_pairs": important,
            "agreed_nuisance_pairs": nuisance,
            "required_category_coverage": groups,
            "feasible_for_next_research_proposal": passed,
            "blockers": blockers,
            "reference_gaps": reference_gaps,
            "preference_blocked": preference_blocked,
            "decision": "reference_package_only_no_algorithm_experiment"
            if passed
            else "stop_algorithm_experiments_and_request_minimal_sample_preference"
            if preference_blocked
            else "stop_algorithm_experiments_reference_insufficient",
            "human_labels": 0,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ["inputs", "panel-a", "panel-b", "output"]:
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output must be new")
    payload = assess(
        json.loads(args.inputs.read_text()),
        json.loads(args.panel_a.read_text()),
        json.loads(args.panel_b.read_text()),
    )
    payload["fingerprints"] = {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in {
            "inputs": args.inputs,
            "panel_a": args.panel_a,
            "panel_b": args.panel_b,
            "assessor": Path(__file__),
        }.items()
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload["summary"]))


if __name__ == "__main__":
    main()
