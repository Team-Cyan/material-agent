"""Frozen experiment contracts; labels are metrics only, never grouping inputs."""

import hashlib
import json
import math
from datetime import datetime, timedelta
from unittest.mock import patch

from material_agent.domain.grouper import Grouper
from material_agent.domain.layered_decision import apply_group_best_candidate_review


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_plan(plan, inputs, manifest, paths):
    if plan.get("schema") != "material-agent.cooking-sequence.v1":
        raise ValueError("unsupported frozen plan schema")
    for key in ("inputs", "manifest", "config"):
        if plan["fingerprints"].get(key) != fingerprint(paths[key]):
            raise ValueError(f"{key} fingerprint mismatch")
    parameters = plan["parameters"]
    if parameters["variants"] != ["phash", "equalized_phash", "dhash"]:
        raise ValueError("unsupported candidate list")
    if parameters["preprocessing"] != {"preview_max": 1024, "jpeg_quality": 85, "hash_max": 256}:
        raise ValueError("unsupported preprocessing")
    threshold = parameters["hash_threshold"]
    gap = parameters["time_gap_seconds"]
    if type(threshold) is not int or not 0 <= threshold <= 64:
        raise ValueError("invalid hash threshold")
    if type(gap) not in (int, float) or not math.isfinite(gap) or gap < 0:
        raise ValueError("invalid time gap")
    if not math.isfinite(inputs["frame_rate"]) or inputs["frame_rate"] <= 0:
        raise ValueError("invalid frame rate")
    videos = [r["sequence"] for r in manifest]
    if len(videos) != len(set(videos)) or set(videos) != set(plan["videos"]):
        raise ValueError("video manifest does not match plan")
    if {s["sequence"] for s in inputs["sequences"]} != set(videos):
        raise ValueError("sequence inputs do not match videos")
    sampling = plan["sampling"]
    if (
        sampling["step_seconds"] != 1
        or sampling["through_second"] != 120
        or sampling["max_frames_per_video"] != 121
    ):
        raise ValueError("unsupported frozen sampling rule")
    seen = set()
    for seq in inputs["sequences"]:
        frames = [r["frame"] for r in seq["samples"]]
        if (
            seq["sequence"] in seen
            or not frames
            or frames != sorted(set(frames))
            or any(type(n) is not int or n < 0 for n in frames)
            or len(frames) > plan["sampling"]["max_frames_per_video"]
        ):
            raise ValueError("invalid sequence sampling")
        expected = [
            round(t * inputs["frame_rate"])
            for t in range(121)
            if round(t * inputs["frame_rate"]) < seq["frame_count"]
        ]
        if frames != expected:
            raise ValueError("frames do not follow frozen sampling rule")
        seen.add(seq["sequence"])
    return parameters


def evaluate_sequence(records, parameters, variant):
    """Run a whole ordered sequence through actual adjacent grouping and selection."""
    keys = [r["id"] for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate frame identifiers")
    by_id = {r["id"]: r for r in records}
    hashes = {r["id"]: r["hashes"][variant] for r in records}
    times = {r["id"]: datetime(2026, 1, 1) + timedelta(seconds=r["seconds"]) for r in records}
    with patch.object(Grouper, "_hash_file", side_effect=hashes.get):
        groups = Grouper(parameters)._group_with_times(keys, times)
    values = json.loads(json.dumps({r["id"]: r["score"] for r in records}))
    selected = {
        k: v
        for group in groups
        for k, v in apply_group_best_candidate_review([(k, values[k]) for k in group])
    }
    retained = {k for k, v in selected.items() if v["decision"] != "reject"}
    keep = {k for k, v in selected.items() if v["decision"] == "keep"}

    def references(ids, field):
        return {label for k in ids for label in by_id[k].get(field, [])}

    actions = references(keys, "actions")
    segments = references(keys, "segments")
    detail = []
    for group in groups:
        distance = int(hashes[group[0]] - hashes[group[-1]])
        diameter = max(int(hashes[a] - hashes[b]) for a in group for b in group)
        detail.append(
            {
                "members": group,
                "actions": sorted(references(group, "actions")),
                "segments": sorted(references(group, "segments")),
                "endpoint_distance": distance,
                "maximum_pair_distance": diameter,
                "endpoint_exceeds_threshold": parameters["hash_threshold"] > 0
                and distance > parameters["hash_threshold"],
            }
        )
    return {
        "group_sizes": [len(g) for g in groups],
        "groups": detail,
        "cross_action_groups": sum(len(g["actions"]) > 1 for g in detail),
        "chain_endpoint_exceedances": sum(g["endpoint_exceeds_threshold"] for g in detail),
        "reference_actions": sorted(actions),
        "lost_actions": sorted(actions - references(retained, "actions")),
        "reference_segments": sorted(segments),
        "lost_segments": sorted(segments - references(retained, "segments")),
        "explicit_keep_actions": sorted(references(keep, "actions")),
        "unlabeled_frames": sum(not r.get("actions") for r in records),
        "selection": {k: v["decision"] for k, v in selected.items()},
        "quality": {k: v["meta"]["quality_assessment"]["decision"] for k, v in selected.items()},
        "scores": {k: v["score_total"] for k, v in selected.items()},
    }
