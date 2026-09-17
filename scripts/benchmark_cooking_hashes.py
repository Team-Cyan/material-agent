"""Read frozen cooking-video frame pairs; write only JSON hash/selection evidence."""

import argparse
import asyncio
import io
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
import cv2
import imagehash
import numpy as np
from PIL import Image, ImageOps
from material_agent.clients.local import AsyncLocalClient
from material_agent.domain.scoring_engine import RawFrame, compute_scores
from material_agent.domain.grouper import Grouper
from material_agent.domain.layered_decision import apply_group_best_candidate_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--video-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.videos.resolve()
    OUTPUT = args.output_dir.resolve()
    if OUTPUT == ROOT or ROOT in OUTPUT.parents:
        parser.error("output must be outside the video source directory")
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        parser.error("output directory must be new or empty")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(args.pairs.read_text())
    config = json.loads(args.config.read_text())
    manifest = json.loads(args.video_manifest.read_text())
    for item in manifest:
        if Path(item["sequence"]).name != item["sequence"]:
            raise ValueError("invalid video sequence name")
        assert (
            hashlib.sha256((ROOT / (item["sequence"] + ".avi")).read_bytes()).hexdigest()
            == item["sha256"]
        )
    assert {p["sequence"] for p in frozen["pairs"]} <= {r["sequence"] for r in manifest}

    def frame(seq, index):
        cap = cv2.VideoCapture(str(ROOT / (seq + ".avi")))
        assert cap.isOpened() and abs(cap.get(cv2.CAP_PROP_FPS) - frozen["frame_rate"]) < 1e-6
        assert 0 <= index < cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, a = cap.read()
        assert ok
        position = cap.get(cv2.CAP_PROP_POS_FRAMES)
        cap.release()
        assert abs(position - (index + 1)) < 0.1
        im = Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
        im.thumbnail((1024, 1024))
        b = io.BytesIO()
        im.save(b, format="JPEG", quality=85)
        data = b.getvalue()
        gray = cv2.cvtColor(
            cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY
        )
        im = Image.open(io.BytesIO(data))
        im.thumbnail((256, 256))
        g = im.convert("L")
        return (
            data,
            gray,
            {
                "phash": imagehash.phash(im),
                "equalized_phash": imagehash.phash(ImageOps.equalize(g)),
                "dhash": imagehash.dhash(g),
            },
        )

    async def run():
        client = AsyncLocalClient(config["local"])
        cache = {}
        out = []
        for pair in frozen["pairs"]:
            values = {}
            hashes = {}
            times = {}
            previews = {}
            for k, index in zip(["first", "second"], pair["frames"]):
                key = (pair["sequence"], index)
                if key not in cache:
                    data, gray, h = frame(*key)
                    b = await compute_scores(RawFrame(data, gray, focus_gray=gray), client, config)
                    cache[key] = (
                        {
                            "score_total": b.total,
                            "scores": b.scores,
                            "scene": b.scene,
                            "decision": b.decision,
                            "decision_reasons": b.decision_reasons,
                            "meta": b.meta,
                        },
                        h,
                        hashlib.sha256(data).hexdigest(),
                    )
                values[k], hashes[k], previews[k] = cache[key]
                times[k] = datetime(2026, 1, 1) + timedelta(seconds=index / frozen["frame_rate"])
            variants = {}
            for v in ["phash", "equalized_phash", "dhash"]:
                hm = {k: h[v] for k, h in hashes.items()}
                with patch.object(Grouper, "_hash_file", side_effect=hm.get):
                    groups = Grouper(
                        {"time_gap_seconds": 10, "hash_threshold": 10}
                    )._group_with_times(["first", "second"], times)
                copied = json.loads(json.dumps(values))
                selected = {
                    k: x
                    for g in groups
                    for k, x in apply_group_best_candidate_review([(k, copied[k]) for k in g])
                }
                variants[v] = {
                    "distance": int(hm["first"] - hm["second"]),
                    "groups": groups,
                    "selection": {
                        k: x["meta"]["selection"]["decision"] for k, x in selected.items()
                    },
                    "quality": {
                        k: x["meta"]["quality_assessment"]["decision"] for k, x in selected.items()
                    },
                    "scores": {k: x["score_total"] for k, x in selected.items()},
                }
            out.append({**pair, "preview_sha256": previews, "variants": variants})
        summary = {}
        for split in ["calibration", "holdout"]:
            summary[split] = {}
            for v in ["phash", "equalized_phash", "dhash"]:
                rows = [x for x in out if x["split"] == split]
                positive = [x for x in rows if x["kind"] == "same_segment"]
                negative = [x for x in rows if x["kind"] == "different_action"]
                summary[split][v] = {
                    "same_pairs": len(positive),
                    "different_pairs": len(negative),
                    "false_split": sum(len(x["variants"][v]["groups"]) > 1 for x in positive),
                    "false_merge": sum(len(x["variants"][v]["groups"]) == 1 for x in negative),
                    "distinct_action_selected_reject": sum(
                        len(x["variants"][v]["groups"]) == 1
                        and "reject" in x["variants"][v]["selection"].values()
                        for x in negative
                    ),
                    "quality_reject_selected_keep": sum(
                        sum(
                            x["variants"][v]["quality"][k] == "reject"
                            and x["variants"][v]["selection"][k] == "keep"
                            for k in ["first", "second"]
                        )
                        for x in rows
                    ),
                }
        for r in manifest:
            assert (
                hashlib.sha256((ROOT / (r["sequence"] + ".avi")).read_bytes()).hexdigest()
                == r["sha256"]
            )
        (OUTPUT / "results.json").write_text(
            json.dumps(
                {
                    "frozen_pairs_sha256": hashlib.sha256(args.pairs.read_bytes()).hexdigest(),
                    "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
                    "opencv_version": cv2.__version__,
                    "unique_frames": len(cache),
                    "summary": summary,
                    "rows": out,
                },
                indent=2,
            )
        )
        print(json.dumps(summary, indent=2))

    asyncio.run(run())


if __name__ == "__main__":
    main()
