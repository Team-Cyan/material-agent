"""Execute the locked residual hypothesis on frozen, previously unseen RAW events."""

import argparse
import asyncio
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time

import cv2
import numpy as np
from PIL import Image
from material_agent.clients.local import AsyncLocalClient
from material_agent.domain.grouper import read_exif_datetimes
from material_agent.domain.scoring_engine import decode_raw, compute_scores
from benchmark_coverage_observability import evaluate_relation
from direct_coverage import Protocol, candidates, prepare, relation, select, audit


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_rows(rows, pair_limit):
    events = {r["event"] for r in rows}
    if len(events) != 2 or len(rows) != 6:
        raise ValueError("frozen holdout requires two events and six frames")
    if len({(r["event"], r["file"]) for r in rows}) != len(rows):
        raise ValueError("duplicate holdout input")
    if any(sum(r["event"] == event for r in rows) != 3 for event in events):
        raise ValueError("each holdout event requires three frames")
    if 6 > pair_limit:
        raise ValueError("holdout pair budget exceeded")


async def evaluate(args):
    root = args.photos.resolve()
    output = args.output.resolve()
    if output.exists() or root in output.parents:
        raise ValueError("output must be new and outside photos")
    plan = json.loads(args.plan.read_text())
    development = json.loads(args.development.read_text())
    if not development["summary"]["development_pass"]:
        raise ValueError("development gate failed")
    implementation = Path(__file__).with_name("benchmark_coverage_observability.py")
    if development["script_sha256"] != sha(implementation) or development["plan_sha256"] != sha(
        args.plan
    ):
        raise ValueError("implementation or protocol changed after development")
    manifest = json.loads(args.inputs.read_text())
    config = json.loads(args.config.read_text())
    cv2.setNumThreads(1)
    client = AsyncLocalClient(config["local"])
    rows = manifest["images"]
    validate_rows(rows, plan["protocol"]["maximum_candidate_pairs"])
    paths = {}
    for r in rows:
        path = (root / r["event"] / r["file"]).resolve()
        if root not in path.parents or sha(path) != r["sha256"]:
            raise ValueError("source fingerprint/path mismatch")
        paths[r["event"], r["file"]] = path
    times = read_exif_datetimes([str(p) for p in paths.values()])
    if any(value is None for value in times.values()):
        raise ValueError("missing actual capture time")
    results = []
    for event in sorted({r["event"] for r in rows}):
        started = time.perf_counter()
        frames = []
        decode_seconds = score_seconds = 0.0
        items = [r for r in rows if r["event"] == event]
        origin = min(times[str(paths[event, r["file"]])] for r in items)
        for i, r in enumerate(items):
            t = time.perf_counter()
            decoded = decode_raw(str(paths[event, r["file"]]), config["preview"])
            rgb = np.asarray(Image.open(io.BytesIO(decoded.jpeg_bytes)).convert("RGB"))
            decode_seconds += time.perf_counter() - t
            t = time.perf_counter()
            scores = await compute_scores(decoded, client, config)
            score_seconds += time.perf_counter() - t
            frames.append(
                {
                    "id": str(i),
                    "seconds": (times[str(paths[event, r["file"]])] - origin).total_seconds(),
                    "rgb": rgb,
                    "preview_sha256": hashlib.sha256(decoded.jpeg_bytes).hexdigest(),
                    "quality": {
                        "total": scores.total,
                        "sharpness": scores.scores.get("sharpness"),
                        "exposure": scores.scores.get("exposure"),
                    },
                }
            )
        p = Protocol()
        pairs, omitted = candidates(frames, p)
        by_id = {f["id"]: f for f in frames}
        prepared = {f["id"]: prepare(f["rgb"], p) for f in frames}
        baseline = {}
        proposed = {}
        overrun = False
        for a, b in pairs:
            for source, target in [(a, b), (b, a)]:
                baseline[source, target] = relation(prepared[source], prepared[target], p)
                proposed[source, target] = evaluate_relation(
                    by_id[source]["rgb"], by_id[target]["rgb"], plan["protocol"]
                )
                e = proposed[source, target]
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
                    1 if sys.platform == "darwin" else 1024
                )
                if (
                    e["seconds"] > plan["protocol"]["maximum_case_seconds"]
                    or peak > plan["protocol"]["process_rss_limit_bytes"]
                ):
                    e.update(relation="unknown", reason="resource_budget")
                    overrun = True
        variants = {}
        for name, edges in [("frozen_sift", baseline), ("observability", proposed)]:
            decisions = select(frames, edges, p)
            variants[name] = {
                "decisions": decisions,
                "kept": sum(v["decision"] == "keep" for v in decisions.values()),
                "audit_before_independent_references": audit(decisions, edges, {}),
                "edges": [{"source": a, "target": b, **e} for (a, b), e in edges.items()],
            }
        results.append(
            {
                "event": event,
                "frames": [{k: v for k, v in f.items() if k != "rgb"} for f in frames],
                "variants": variants,
                "candidate_pairs": len(pairs),
                "omitted_pairs": omitted,
                "resource_overrun": overrun,
                "timing": {
                    "decode_seconds": decode_seconds,
                    "score_seconds": score_seconds,
                    "total_seconds": time.perf_counter() - started,
                    "process_peak_rss_bytes": peak,
                },
            }
        )
    assert all(sha(paths[r["event"], r["file"]]) == r["sha256"] for r in rows)
    payload = {
        "schema": plan["schema"],
        "stage": "independent_holdout",
        "sources_unchanged": True,
        "baseline_protocol": asdict(Protocol()),
        "fingerprints": {
            k: sha(v)
            for k, v in {
                "plan": args.plan,
                "development": args.development,
                "inputs": args.inputs,
                "config": args.config,
                "implementation": implementation,
                "runner": Path(__file__),
            }.items()
        },
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            [
                {
                    "event": r["event"],
                    "kept": {k: v["kept"] for k, v in r["variants"].items()},
                    "seconds": r["timing"]["total_seconds"],
                }
                for r in results
            ]
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["photos", "output", "plan", "development", "inputs", "config"]:
        parser.add_argument("--" + key, type=Path, required=True)
    asyncio.run(evaluate(parser.parse_args()))


if __name__ == "__main__":
    main()
