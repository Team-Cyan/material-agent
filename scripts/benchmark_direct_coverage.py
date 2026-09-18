"""Bounded report-only direct-coverage experiment, with independent references."""

import argparse
import asyncio
import copy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time

import cv2
import imagehash
import numpy as np
from PIL import Image
from material_agent.clients.local import AsyncLocalClient
from material_agent.domain.grouper import Grouper
from material_agent.domain.scoring_engine import RawFrame, compute_scores, decode_raw
from material_agent.domain.layered_decision import apply_group_best_candidate_review
from cooking_sequence_protocol import evaluate_sequence
from direct_coverage import Protocol, audit, candidates, run, select


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def synthetic(variant):
    rng = np.random.default_rng(761)
    gray = rng.integers(35, 215, (320, 320), dtype=np.uint8)
    gray = cv2.GaussianBlur(gray, (3, 3), 0.5)
    base = np.repeat(gray[..., None], 3, axis=2)
    changed = base.copy()
    if variant == "exposure":
        changed = (base.astype(float) * 0.7 + 10).astype(np.uint8)
    elif variant == "noise":
        changed = np.clip(base.astype(float) + rng.normal(0, 4, base.shape), 0, 255).astype(
            np.uint8
        )
    elif variant == "shadow":
        changed[100:200] = (changed[100:200].astype(float) * 0.6).astype(np.uint8)
    elif variant in ("foliage", "water"):
        changed[100:200] = np.roll(changed[100:200], 6, axis=1)
        if variant == "water":
            for y in range(100, 200):
                changed[y] = np.roll(base[y], int(6 * np.sin(y / 5)), axis=0)
    elif variant == "parallax":
        changed[:, 160:] = np.roll(changed[:, 160:], 5, axis=0)
    elif variant == "occlusion":
        changed[100:180, 100:180] = 60
    elif variant in ("gesture", "expression"):
        # Symbolic content patch, not a claim of realistic facial/action synthesis.
        size = 12 if variant == "gesture" else 4
        changed[144 : 144 + size, 144 : 144 + size] = 60
    elif variant != "identity":
        raise ValueError("unknown synthetic variant")
    return base, changed


def encode(rgb):
    im = Image.fromarray(rgb)
    im.thumbnail((1024, 1024))
    stream = io.BytesIO()
    im.save(stream, format="JPEG", quality=85)
    data = stream.getvalue()
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return RawFrame(data, gray, focus_gray=gray)


def references(case, frames):
    result = {(r["source"], r["target"]): r["reference"] for r in case.get("references", [])}
    for a in frames:
        for b in frames:
            if a["id"] == b["id"]:
                continue
            key = (a["id"], b["id"])
            if key in result:
                continue
            acts_a, acts_b = set(a.get("actions", [])), set(b.get("actions", []))
            result[key] = (
                "different"
                if acts_a and acts_b and not acts_a & acts_b
                else case.get("reference", "unknown")
            )
    return result


def metrics(frames, decisions, edges, refs, acceptable=None):
    kept = {k for k, v in decisions.items() if v["decision"] != "reject"}
    cover_edges = [k for k, v in edges.items() if v["relation"] == "cover"]
    result = {
        "kept": len(kept),
        "rejected": len(frames) - len(kept),
        "decisions": decisions,
        "cover_edges": len(cover_edges),
        "independent_negative_cover_edges": sum(refs.get(k) == "different" for k in cover_edges),
        "unjudged_cover_edges": sum(refs.get(k, "unknown") == "unknown" for k in cover_edges),
        **audit(decisions, edges, refs),
    }
    for field in ["actions", "segments"]:
        all_labels = {label for f in frames for label in f.get(field, [])}
        kept_labels = {label for f in frames if f["id"] in kept for label in f.get(field, [])}
        result["reference_" + field] = sorted(all_labels)
        result["lost_" + field] = sorted(all_labels - kept_labels)
    # Explicit external acceptable keeper sets, never graph-derived ground truth.
    result["acceptable_keeper_set_satisfied"] = (
        any(set(s) <= kept for s in acceptable) if acceptable else None
    )
    result["extra_retention"] = (
        len(kept) - min(map(len, acceptable))
        if acceptable and result["acceptable_keeper_set_satisfied"]
        else None
    )
    result["final_unique_content_loss"] = (
        not result["acceptable_keeper_set_satisfied"]
        if acceptable
        else bool(
            len(frames) == 2 and any(v == "different" for v in refs.values()) and len(kept) < 2
        )
        if len(frames) == 2 and any(v == "different" for v in refs.values())
        else None
    )
    return result


def components(frames, edges):
    parent = {f["id"]: f["id"] for f in frames}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    for (a, b), e in edges.items():
        if e["relation"] == "cover":
            parent[root(a)] = root(b)
    groups = {}
    for f in frames:
        groups.setdefault(root(f["id"]), []).append(f["id"])
    return list(groups.values())


def old_selection(frames, groups):
    scores = {f["id"]: copy.deepcopy(f["score"]) for f in frames}
    return {
        k: {"decision": s["decision"], "covered_by": None}
        for group in groups
        for k, s in apply_group_best_candidate_review([(k, scores[k]) for k in group])
    }


def plain(frames):
    return [{k: v for k, v in f.items() if k not in ("rgb", "hashes")} for f in frames]


def peak_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )


def remaining_protocol(protocol, started, budgets):
    remaining = min(
        protocol.max_seconds, budgets["case_wall_seconds"] - (time.perf_counter() - started)
    )
    if remaining <= 0 or peak_rss() > budgets["process_peak_rss_bytes"]:
        raise TimeoutError("case resource budget exhausted; abort without acceptance result")
    return replace(protocol, max_seconds=remaining)


def perturbations(frames, original, protocol, started, budgets):
    if len(frames) < 3:
        return None
    removed = frames[len(frames) // 2]["id"]
    subset = [f for f in frames if f["id"] != removed]
    # Full recomputation: deletion changes nearest-forward candidate eligibility.
    deleted = run(subset, remaining_protocol(protocol, started, budgets))
    restored = run(list(reversed(frames)), remaining_protocol(protocol, started, budgets))

    def changes(before, after):
        return sorted(k for k in before.keys() & after.keys() if before[k] != after[k])

    return {
        "removed_id": removed,
        "deletion_changed_survivors": changes(original, deleted["decisions"]),
        "reinsertion_changed_survivors": changes(deleted["decisions"], restored["decisions"]),
        "reversed_reinserted_equals_original": restored["decisions"] == original,
        "full_recompute_seconds": deleted["elapsed_seconds"] + restored["elapsed_seconds"],
        "budget_exceeded": deleted["budget_exceeded"] or restored["budget_exceeded"],
        "local_recomputation_guarantee": False,
    }


async def evaluate(args):
    plan = json.loads(args.plan.read_text())
    inputs = json.loads(args.inputs.read_text())
    config = json.loads(args.config.read_text())
    p = Protocol(**plan["protocol"])
    if sha(args.config) != inputs["fingerprints"]["config"]:
        raise ValueError("frozen config mismatch")
    if inputs["preprocessing"] != {
        "synthetic_seed": 761,
        "synthetic_side": 320,
        "video_preview_max": 1024,
        "video_jpeg_quality": 85,
        "hash_max": 256,
        "relation_max": 512,
        "raw": "production decode_raw with frozen preview config",
    }:
        raise ValueError("unsupported preprocessing")
    if p.max_side != 512:
        raise ValueError("relation preprocessing differs from frozen inputs")
    roots = {k: getattr(args, k).resolve() for k in ["videos", "exposure", "holdout"]}
    output = args.output_dir.resolve()
    if any(output == r or r in output.parents for r in roots.values()):
        raise ValueError("output must be outside all photo/video roots")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be new or empty")
    sources = {}
    for case in inputs["cases"]:
        candidates(case["frames"], p)
        for item in (
            [case] if case["kind"] == "video" else case["frames"] if case["kind"] == "raw" else []
        ):
            root = roots[case["root"]]
            path = (root / item["file"]).resolve()
            if root not in path.parents:
                raise ValueError("source escapes dataset root")
            sources[path] = item["sha256"]
    for path, digest in sources.items():
        if sha(path) != digest:
            raise ValueError("source fingerprint mismatch")
    cv2.setNumThreads(1)
    client = AsyncLocalClient(config["local"])
    results = []
    for case in inputs["cases"]:
        started = time.perf_counter()
        frames = []
        decode_seconds = score_seconds = 0.0
        synthetic_images = synthetic(case["variant"]) if case["kind"] == "synthetic" else None
        cap = None
        if case["kind"] == "video":
            cap = cv2.VideoCapture(str(roots["videos"] / case["file"]))
            if not cap.isOpened() or abs(cap.get(cv2.CAP_PROP_FPS) - case["fps"]) > 1e-6:
                raise ValueError("video frame rate mismatch")
        try:
            for i, item in enumerate(case["frames"]):
                remaining_protocol(p, started, plan["budgets"])
                decode_start = time.perf_counter()
                if case["kind"] == "raw":
                    decoded = decode_raw(str(roots[case["root"]] / item["file"]), config["preview"])
                elif cap is not None:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, item["frame"])
                    ok, bgr = cap.read()
                    if not ok or abs(cap.get(cv2.CAP_PROP_POS_FRAMES) - item["frame"] - 1) > 0.1:
                        raise ValueError("video seek failed")
                    decoded = encode(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                else:
                    decoded = encode(synthetic_images[i])
                rgb_image = Image.open(io.BytesIO(decoded.jpeg_bytes)).convert("RGB")
                h_image = rgb_image.copy()
                h_image.thumbnail((256, 256))
                hashes = {"phash": imagehash.phash(h_image)}
                if case["kind"] == "raw":
                    hashes["phash"] = Grouper._hash_file(str(roots[case["root"]] / item["file"]))
                    if hashes["phash"] is None:
                        raise ValueError("production RAW hash unavailable")
                rgb_image.thumbnail((p.max_side, p.max_side))
                rgb = np.asarray(rgb_image).copy()
                decode_seconds += time.perf_counter() - decode_start
                score_start = time.perf_counter()
                bundle = await compute_scores(decoded, client, config)
                score_seconds += time.perf_counter() - score_start
                score = dict(
                    score_total=bundle.total,
                    scores=bundle.scores,
                    scene=bundle.scene,
                    decision=bundle.decision,
                    decision_reasons=bundle.decision_reasons,
                    meta=bundle.meta,
                )
                frames.append(
                    {
                        **item,
                        "rgb": rgb,
                        "hashes": hashes,
                        "score": score,
                        "preview_sha256": hashlib.sha256(decoded.jpeg_bytes).hexdigest(),
                        "quality": {
                            "total": bundle.total,
                            "sharpness": bundle.scores.get("sharpness"),
                            "exposure": bundle.scores.get("exposure"),
                        },
                    }
                )
        finally:
            if cap is not None:
                cap.release()
        result = run(frames, remaining_protocol(p, started, plan["budgets"]))
        mutations = perturbations(frames, result["decisions"], p, started, plan["budgets"])
        refs = references(case, frames)
        acceptable = case.get("acceptable_keeper_sets")
        if case["kind"] == "synthetic" and case["reference"] == "cover":
            acceptable = [[f["id"]] for f in frames]
        direct = metrics(frames, result["decisions"], result["edges"], refs, acceptable)
        pairs, _ = candidates(frames, p)
        by_id = {f["id"]: f for f in frames}
        phash_edges = {
            (a, b): {
                "relation": "cover"
                if int(by_id[a]["hashes"]["phash"] - by_id[b]["hashes"]["phash"]) <= 10
                else "unknown"
            }
            for pair in pairs
            for a, b in [pair, tuple(reversed(pair))]
        }
        phash = metrics(frames, select(frames, phash_edges, p), phash_edges, refs, acceptable)
        production = evaluate_sequence(
            frames, {"time_gap_seconds": 10, "hash_threshold": 10}, "phash"
        )
        production_decisions = {
            k: {"decision": v, "covered_by": None} for k, v in production["selection"].items()
        }
        production_metrics = metrics(frames, production_decisions, {}, refs, acceptable)
        unsafe_groups = components(frames, result["edges"])
        unsafe_decisions = old_selection(frames, unsafe_groups)
        unsafe = metrics(frames, unsafe_decisions, {}, refs, acceptable)
        # Old group selectors have no direct-witness contract: do not report missing witnesses as bugs.
        for value in [production_metrics, unsafe]:
            for key in [
                "structural_violations",
                "reference_checked_rejects",
                "false_covered_rejects",
                "unjudged_rejects",
            ]:
                value[key] = None
        elapsed = time.perf_counter() - started
        peak = peak_rss()
        result.pop("decisions")
        result["edges"] = [
            {"source": a, "target": b, **e, "independent_reference": refs.get((a, b), "unknown")}
            for (a, b), e in result["edges"].items()
        ]
        case_result = {
            "id": case["id"],
            "frames": plain(frames),
            "timing": {
                "decode_seconds": decode_seconds,
                "score_seconds": score_seconds,
                "total_seconds": elapsed,
                "process_peak_rss_bytes": peak,
            },
            "case_budget_exceeded": elapsed > plan["budgets"]["case_wall_seconds"]
            or peak > plan["budgets"]["process_peak_rss_bytes"],
            "relation_run": result,
            "perturbations": mutations,
            "variants": {
                "sift_direct": direct,
                "phash_direct": phash,
                "production": {**production_metrics, "group_sizes": production["group_sizes"]},
                "sift_connected_old_selector": {
                    **unsafe,
                    "group_sizes": list(map(len, unsafe_groups)),
                },
            },
        }
        results.append(case_result)
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "frames": len(frames),
                    "kept": direct["kept"],
                    "false_cover_edges": direct["independent_negative_cover_edges"],
                    "seconds": round(elapsed, 2),
                }
            ),
            flush=True,
        )
        if case_result["case_budget_exceeded"]:
            break
    unchanged = all(sha(path) == digest for path, digest in sources.items())
    if not unchanged:
        raise ValueError("source changed during evaluation")
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "material-agent.direct-coverage.result.v1",
        "sources_unchanged": unchanged,
        "complete": len(results) == len(inputs["cases"]),
        "opencv_version": cv2.__version__,
        "opencv_threads": cv2.getNumThreads(),
        "fingerprints": {
            k: sha(v)
            for k, v in {
                "plan": args.plan,
                "inputs": args.inputs,
                "config": args.config,
                "runner": Path(__file__),
                "relation": Path(__file__).with_name("direct_coverage.py"),
            }.items()
        },
        "results": results,
    }
    (output / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["plan", "inputs", "config", "videos", "exposure", "holdout", "output-dir"]:
        parser.add_argument("--" + name, type=Path, required=True)
    asyncio.run(evaluate(parser.parse_args()))


if __name__ == "__main__":
    main()
