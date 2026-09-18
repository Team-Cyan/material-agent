"""Single frozen development hypothesis; stops before holdout on failure."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from direct_coverage import Protocol, prepare, relation


def jpeg(rgb, quality):
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, format="JPEG", quality=quality)
    return np.asarray(Image.open(io.BytesIO(output.getvalue())).convert("RGB"))


def controls(seed, side, kind, params):
    rng = np.random.default_rng(seed)
    gray = cv2.GaussianBlur(rng.integers(35, 215, (side, side), dtype=np.uint8), (3, 3), 0.5)
    a = np.repeat(gray[..., None], 3, axis=2)
    b = a.copy()
    q1, q2 = params["jpeg_quality_pair"]
    if kind == "noise":
        b = np.clip(
            b.astype(float) + rng.normal(0, params["noise_standard_deviation"], b.shape), 0, 255
        ).astype(np.uint8)
    elif kind == "subpixel":
        dx, dy = params["subpixel_translation_xy"]
        b = cv2.warpAffine(
            b, np.float32([[1, 0, dx], [0, 1, dy]]), (side, side), borderMode=cv2.BORDER_REFLECT
        )
    elif kind == "exposure":
        gain, offset = params["exposure_gain_offset"]
        b = np.clip(b.astype(float) * gain + offset, 0, 255).astype(np.uint8)
    elif kind in ("small_luminance", "isoluminant_color"):
        start = side // 2
        end = start + params["small_content_patch_side"]
        if kind == "small_luminance":
            b[start:end, start:end] = 60
        else:
            a[start:end, start:end] = [200, 0, 0]
            b[start:end, start:end] = [0, 102, 0]
    elif kind not in ("identity", "jpeg"):
        raise ValueError("unknown control")
    if kind == "identity":
        q2 = q1
    return jpeg(a, q1), jpeg(b, q2)


def evaluate_relation(a, b, params):
    started = time.perf_counter()
    p = Protocol(max_side=params["max_side"])
    prepared_a, prepared_b = prepare(a, p), prepare(b, p)
    capture = {}
    original = cv2.findHomography

    def intercept(*args, **kwargs):
        answer = original(*args, **kwargs)
        capture["transform"] = answer[0]
        return answer

    with patch.object(cv2, "findHomography", side_effect=intercept):
        old = relation(prepared_a, prepared_b, p)

    def answer(status, reason, evidence):
        return {
            "relation": status,
            "reason": reason,
            "evidence": evidence,
            "seconds": time.perf_counter() - started,
        }

    if old["reason"] not in ("geometry_and_photometric_consistency", "unexplained_local_change"):
        return answer("unknown", "unchanged_geometry_or_observability_gate", {"baseline": old})
    transform = capture.get("transform")
    if transform is None:
        return answer("unknown", "missing_geometry", {})

    def resized(rgb):
        image = Image.fromarray(rgb)
        image.thumbnail((params["max_side"], params["max_side"]))
        return np.asarray(image).astype(float)

    x, y = resized(a), resized(b)
    shape = y.shape[1::-1]
    warped = cv2.warpPerspective(x, transform, shape)
    support = cv2.warpPerspective(
        np.ones(x.shape[:2], np.uint8), transform, shape, flags=cv2.INTER_NEAREST
    )
    valid = cv2.erode(support, np.ones((5, 5), np.uint8)).astype(bool)
    # Luminance-derived global gain, robust channel offsets. No local color fitting.
    gray_x = cv2.cvtColor(warped.astype(np.float32), cv2.COLOR_RGB2GRAY)
    gray_y = cv2.cvtColor(y.astype(np.float32), cv2.COLOR_RGB2GRAY)
    xx, yy = np.percentile(gray_x[valid], [10, 90]), np.percentile(gray_y[valid], [10, 90])
    gain = (yy[1] - yy[0]) / max(xx[1] - xx[0], 1.0)
    offset = np.median(y[valid], axis=0) - gain * np.median(warped[valid], axis=0)
    corrected = np.clip(warped * gain + offset, 0, 255)
    signed = corrected - y
    # Robust noise envelope is global: sparse changed content should not define it.
    centered = signed[valid] - np.median(signed[valid], axis=0)
    mad = 1.4826 * np.median(np.abs(centered), axis=0)
    threshold = np.maximum(params["local_absolute_floor"], params["local_mad_multiplier"] * mad)
    changed = (np.any(np.abs(signed) > threshold, axis=2) & valid).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(changed, 8)
    largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
    smoothed = np.max(
        np.abs(
            cv2.GaussianBlur(corrected, (0, 0), params["smoothing_sigma"])
            - cv2.GaussianBlur(y, (0, 0), params["smoothing_sigma"])
        ),
        axis=2,
    )
    mean = float(smoothed[valid].mean())
    p95 = float(np.percentile(smoothed[valid], 95))
    evidence = {
        "baseline": old,
        "noise_mad_rgb": mad.tolist(),
        "local_threshold_rgb": threshold.tolist(),
        "changed_pixels": int(changed.sum()),
        "largest_component": largest,
        "smoothed_mean": mean,
        "smoothed_p95": p95,
        "gain": float(gain),
    }
    if largest >= params["connected_component_minimum_pixels"]:
        return answer("unknown", "localized_unexplained_color_or_luminance", evidence)
    if mean > params["global_mean_limit"] or p95 > params["global_p95_limit"]:
        return answer("unknown", "global_unexplained_residual", evidence)
    return answer("cover", "bounded_residual_hypothesis", evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output must be new")
    plan = json.loads(args.plan.read_text())
    p = plan["protocol"]
    dev = plan["development"]
    cv2.setNumThreads(1)
    count = len(dev["seeds"]) * len(dev["side_lengths"]) * len(dev["controls"])
    if count > p["maximum_candidate_pairs"]:
        raise ValueError("pair budget exceeded")
    rows = []
    for seed in dev["seeds"]:
        for side in dev["side_lengths"]:
            for kind in dev["controls"]:
                started = time.perf_counter()
                a, b = controls(seed, side, kind, dev)
                result = evaluate_relation(a, b, p)
                old_protocol = Protocol()
                baseline = relation(
                    prepare(a, old_protocol), prepare(b, old_protocol), old_protocol
                )
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
                    1 if sys.platform == "darwin" else 1024
                )
                elapsed = time.perf_counter() - started
                if elapsed > p["maximum_case_seconds"] or peak > p["process_rss_limit_bytes"]:
                    result.update(relation="unknown", reason="resource_budget")
                rows.append(
                    {
                        "seed": seed,
                        "side": side,
                        "kind": kind,
                        "reference": "cover" if kind in dev["positives"] else "different",
                        "input_sha256": [hashlib.sha256(v.tobytes()).hexdigest() for v in [a, b]],
                        "result": result,
                        "frozen_512_baseline": baseline,
                        "case_seconds": elapsed,
                        "process_peak_rss_bytes": peak,
                    }
                )
    positive = [r for r in rows if r["reference"] == "cover"]
    negative = [r for r in rows if r["reference"] == "different"]
    false_cover = sum(r["result"]["relation"] == "cover" for r in negative)
    positive_fraction = sum(r["result"]["relation"] == "cover" for r in positive) / len(positive)
    passed = (
        false_cover <= plan["stopping"]["development_negative_cover_maximum"]
        and positive_fraction >= plan["stopping"]["development_positive_cover_minimum_fraction"]
        and all(r["result"]["reason"] != "resource_budget" for r in rows)
    )
    payload = {
        "schema": plan["schema"],
        "stage": "development",
        "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "opencv_version": cv2.__version__,
        "rows": rows,
        "summary": {
            "negative_false_cover": false_cover,
            "negative_pairs": len(negative),
            "positive_cover_fraction": positive_fraction,
            "positive_pairs": len(positive),
            "development_pass": passed,
            "next_stage": "independent_holdout" if passed else "stopped_without_consuming_holdout",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload["summary"]))


if __name__ == "__main__":
    main()
