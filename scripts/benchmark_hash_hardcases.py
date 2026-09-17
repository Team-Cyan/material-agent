"""Synthetic hash stress test; images remain in memory, only JSON reports are written."""

import argparse
import asyncio
import hashlib
import io
import json
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
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.output_dir.resolve()
    DATA = args.dataset.resolve()
    if ROOT == DATA or DATA in ROOT.parents:
        parser.error("output directory must be outside the source dataset")
    if ROOT.exists() and any(ROOT.iterdir()):
        parser.error("output directory must be new or empty")
    ROOT.mkdir(parents=True, exist_ok=True)
    CLASSES = ["cutting_vegetables", "cooking", "washing_dishes"]
    config = json.loads(args.config.read_text())
    sources = []
    for kind in CLASSES:
        for split in ["train", "test"]:
            for name in sorted(
                (DATA / "ImageSplits" / f"{kind}_{split}.txt").read_text().splitlines()
            )[:4]:
                assert Path(name).name == name and name.endswith(".jpg")
                path = DATA / "JPEGImages" / name
                sources.append(
                    {
                        "id": name,
                        "label": kind,
                        "split": split,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
    assert len(sources) == 24 and len({r["id"] for r in sources}) == 24
    plan = {
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "source": "http://vision.stanford.edu/Datasets/40actions.html",
        "sources": sources,
        "selection": "first four lexicographic IDs per class and official split, before scoring",
        "variants": ["phash", "equalized_phash", "dhash"],
        "threshold": 10,
        "time_gap_seconds": 10,
        "synthetic_separation_seconds": 5,
        "positive_transforms": {
            "display_brightness": [0.125, 0.5, 2, 8],
            "detail_loss": ["near_black", "near_white"],
        },
        "negative_transforms": {"replace_center_with_other_class": [0.3, 0.6]},
        "hash_input": "decode the exact JPEG bytes passed to scoring, then production 256px thumbnail",
        "negative_label": "different central content by construction; no human photographic preference ground truth",
        "partition": "official train calibration and official test holdout; no tuning",
        "constraints": "in-memory transformed pixels only; original files immutable; no DB/writer",
    }
    (ROOT / "plan.json").write_text(json.dumps(plan, indent=2))

    def jpeg(im):
        b = io.BytesIO()
        im.save(b, format="JPEG", quality=85)
        return b.getvalue()

    def hs(im):
        im = Image.open(io.BytesIO(jpeg(im)))
        im.thumbnail((256, 256))
        g = im.convert("L")
        return {
            "phash": imagehash.phash(im),
            "equalized_phash": imagehash.phash(ImageOps.equalize(g)),
            "dhash": imagehash.dhash(g),
        }

    async def score(im, client):
        data = jpeg(im)
        gray = cv2.cvtColor(
            cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY
        )
        b = await compute_scores(RawFrame(data, gray, focus_gray=gray), client, config)
        return {
            "score_total": b.total,
            "scores": b.scores,
            "scene": b.scene,
            "decision": b.decision,
            "decision_reasons": b.decision_reasons,
            "meta": b.meta,
        }

    async def run():
        client = AsyncLocalClient(config["local"])
        out = []
        summary = {}
        for source in sources:
            im = Image.open(DATA / "JPEGImages" / source["id"]).convert("RGB")
            im.thumbnail((768, 768))
            a = np.asarray(im)
            original = await score(im, client)
            original_hash = hs(im)
            cases = []
            for factor in plan["positive_transforms"]["display_brightness"]:
                cases.append(
                    (
                        f"brightness_{factor}",
                        True,
                        Image.fromarray(np.clip(a.astype(float) * factor, 0, 255).astype("uint8")),
                        None,
                    )
                )
            cases += [
                (
                    "near_black",
                    True,
                    Image.fromarray((a.astype(float) * 0.002).astype("uint8")),
                    None,
                ),
                (
                    "near_white",
                    True,
                    Image.fromarray((254 + a.astype(float) * 0.002).astype("uint8")),
                    None,
                ),
            ]
            target = next(
                x
                for x in sources
                if x["split"] == source["split"]
                and x["label"] == CLASSES[(CLASSES.index(source["label"]) + 1) % 3]
            )
            donor = Image.open(DATA / "JPEGImages" / target["id"]).convert("RGB")
            for fraction in [0.3, 0.6]:
                w, h = im.size
                pw, ph = round(w * fraction), round(h * fraction)
                composite = im.copy()
                composite.paste(ImageOps.fit(donor, (pw, ph)), ((w - pw) // 2, (h - ph) // 2))
                cases.append((f"center_replace_{fraction}", False, composite, target["id"]))
            for transform, same, altered, targetid in cases:
                altered_score = await score(altered, client)
                ah = hs(altered)
                row = {
                    "source": source["id"],
                    "split": source["split"],
                    "transform": transform,
                    "expected_same_group": same,
                    "donor": targetid,
                    "preview_sha256": hashlib.sha256(jpeg(altered)).hexdigest(),
                    "quality": {
                        "original": {
                            "score": original["score_total"],
                            "decision": original["decision"],
                        },
                        "altered": {
                            "score": altered_score["score_total"],
                            "decision": altered_score["decision"],
                        },
                    },
                    "variants": {},
                }
                for variant in plan["variants"]:
                    hashes = {"altered": ah[variant], "original": original_hash[variant]}
                    times = {
                        "altered": datetime(2026, 1, 1),
                        "original": datetime(2026, 1, 1) + timedelta(seconds=5),
                    }
                    with patch.object(Grouper, "_hash_file", side_effect=hashes.get):
                        groups = Grouper(
                            {"time_gap_seconds": 10, "hash_threshold": 10}
                        )._group_with_times(["altered", "original"], times)
                    # Fresh metadata copies avoid selection results leaking between variants.
                    values = json.loads(
                        json.dumps({"altered": altered_score, "original": original})
                    )
                    selected = {
                        k: v
                        for group in groups
                        for k, v in apply_group_best_candidate_review(
                            [(key, values[key]) for key in group]
                        )
                    }
                    row["variants"][variant] = {
                        "distance": int(ah[variant] - original_hash[variant]),
                        "groups": groups,
                        "selection": {
                            k: v["meta"]["selection"]["decision"] for k, v in selected.items()
                        },
                        "quality": {
                            k: v["meta"]["quality_assessment"]["decision"]
                            for k, v in selected.items()
                        },
                    }
                out.append(row)
            assert (
                hashlib.sha256((DATA / "JPEGImages" / source["id"]).read_bytes()).hexdigest()
                == source["sha256"]
            )
        for split in ["train", "test"]:
            summary[split] = {}
            for variant in plan["variants"]:
                stats = {}
                for row in out:
                    if row["split"] != split:
                        continue
                    bucket = row["transform"].split("_")[0]
                    s = stats.setdefault(
                        bucket,
                        {
                            "pairs": 0,
                            "false_split": 0,
                            "false_merge": 0,
                            "altered_quality_reject_selected_keep": 0,
                            "altered_selected_reject": 0,
                            "original_selected_reject": 0,
                            "merged_lost_content": 0,
                        },
                    )
                    v = row["variants"][variant]
                    merged = len(v["groups"]) == 1
                    s["pairs"] += 1
                    s["false_split"] += row["expected_same_group"] and not merged
                    s["false_merge"] += not row["expected_same_group"] and merged
                    s["altered_quality_reject_selected_keep"] += (
                        v["quality"]["altered"] == "reject" and v["selection"]["altered"] == "keep"
                    )
                    s["altered_selected_reject"] += v["selection"]["altered"] == "reject"
                    s["original_selected_reject"] += v["selection"]["original"] == "reject"
                    s["merged_lost_content"] += (
                        not row["expected_same_group"]
                        and merged
                        and "reject" in v["selection"].values()
                    )
                summary[split][variant] = stats
        for item in sources:
            assert (
                hashlib.sha256((DATA / "JPEGImages" / item["id"]).read_bytes()).hexdigest()
                == item["sha256"]
            )
        (ROOT / "results.json").write_text(
            json.dumps(
                {
                    "plan_sha256": hashlib.sha256((ROOT / "plan.json").read_bytes()).hexdigest(),
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
