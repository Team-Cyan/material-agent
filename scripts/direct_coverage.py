"""Experimental CPU relation/selection baseline. Never used by production grouping."""

from dataclasses import asdict, dataclass
import math
import time

import cv2
import imagehash
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Protocol:
    window_seconds: float = 10.0
    neighbors_forward: int = 3
    max_frames: int = 256
    max_pairs: int = 600
    max_seconds: float = 90.0
    max_side: int = 512
    keypoints: int = 600
    ratio: float = 0.7
    min_matches: int = 20
    min_inlier_ratio: float = 0.75
    min_hull_fraction: float = 0.30
    min_overlap: float = 0.98
    min_dynamic_range: float = 16.0
    max_clipped_fraction: float = 0.40
    mean_residual: float = 2.0
    p95_residual: float = 6.0
    tile_residual: float = 4.0
    tile_grid: int = 8
    quality_sharpness_ratio: float = 0.95
    quality_exposure_tolerance: float = 0.5

    def __post_init__(self):
        for name, value in asdict(self).items():
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"invalid protocol parameter: {name}")
        for name in (
            "neighbors_forward",
            "max_frames",
            "max_pairs",
            "max_side",
            "keypoints",
            "min_matches",
            "tile_grid",
        ):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be integer")
        if any(
            getattr(self, n) > 1
            for n in (
                "ratio",
                "min_inlier_ratio",
                "min_hull_fraction",
                "min_overlap",
                "max_clipped_fraction",
                "quality_sharpness_ratio",
            )
        ):
            raise ValueError("fraction exceeds one")


def candidates(frames, protocol):
    """Time-only eligibility, deterministic nearest-forward cap; hash never filters."""
    if len(frames) > protocol.max_frames:
        raise ValueError("frame budget exceeded")
    if len({f["id"] for f in frames}) != len(frames):
        raise ValueError("duplicate frame id")
    if any(not math.isfinite(f["seconds"]) for f in frames):
        raise ValueError("nonfinite capture time")
    ordered = sorted(frames, key=lambda f: (f["seconds"], f["id"]))
    pairs = []
    omitted = 0
    for i, frame in enumerate(ordered):
        eligible = [
            other
            for other in ordered[i + 1 :]
            if other["seconds"] - frame["seconds"] <= protocol.window_seconds
        ]
        for j, other in enumerate(eligible):
            if j >= protocol.neighbors_forward or len(pairs) >= protocol.max_pairs:
                omitted += 1
            else:
                pairs.append((frame["id"], other["id"]))
    return pairs, omitted


def prepare(rgb, protocol):
    start = time.perf_counter()
    image = Image.fromarray(rgb).convert("RGB")
    image.thumbnail((protocol.max_side, protocol.max_side))
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    low, high = np.percentile(gray, [5, 95])
    clipped = float(np.mean((gray <= 3) | (gray >= 252)))
    observable = (
        high - low >= protocol.min_dynamic_range and clipped <= protocol.max_clipped_fraction
    )
    normalized = cv2.equalizeHist(gray)
    feature_start = time.perf_counter()
    points, descriptors = np.empty((0, 2), np.float32), None
    feature_error = False
    if observable:
        try:
            kp, descriptors = cv2.SIFT_create(nfeatures=protocol.keypoints).detectAndCompute(
                normalized, None
            )
            points = np.float32([k.pt for k in kp]).reshape(-1, 2)
        except cv2.error:
            feature_error = True
    return {
        "gray": gray,
        "points": points,
        "descriptors": descriptors,
        "observable": bool(observable),
        "feature_error": feature_error,
        "clipped_fraction": clipped,
        "dynamic_range": float(high - low),
        "phash": imagehash.phash(image),
        "feature_seconds": time.perf_counter() - feature_start,
        "prepare_seconds": time.perf_counter() - start,
    }


def relation(source, target, protocol):
    """Directed tentative content coverage; quality is not consulted here."""
    started = time.perf_counter()
    evidence = {"hash_distance": int(source["phash"] - target["phash"])}
    evidence["route"] = (
        "unobservable_temporal_bypass"
        if not source["observable"] or not target["observable"]
        else "hash_prior"
        if evidence["hash_distance"] <= 10
        else "high_hash_temporal_bypass"
    )

    def answer(status, reason):
        return {
            "relation": status,
            "reason": reason,
            "evidence": evidence,
            "match_seconds": time.perf_counter() - started,
        }

    if source.get("feature_error") or target.get("feature_error"):
        return answer("unknown", "opencv_feature_failure")
    if not source["observable"] or not target["observable"]:
        return answer("unknown", "insufficient_detail_or_clipping")
    if (
        source["descriptors"] is None
        or target["descriptors"] is None
        or min(len(source["points"]), len(target["points"])) < protocol.min_matches
    ):
        return answer("unknown", "insufficient_features")
    try:
        matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(
            source["descriptors"], target["descriptors"], k=2
        )
        good = [
            pair[0]
            for pair in matches
            if len(pair) == 2 and pair[0].distance < protocol.ratio * pair[1].distance
        ]
        # One source and target observation per match; repeated texture is not independent support.
        unique = {}
        for m in sorted(good, key=lambda m: (m.distance, m.queryIdx, m.trainIdx)):
            unique.setdefault(m.trainIdx, m)
        good = list(unique.values())
        evidence["matches"] = len(good)
        if len(good) < protocol.min_matches:
            return answer("unknown", "insufficient_matches")
        a = np.float32([source["points"][m.queryIdx] for m in good])
        b = np.float32([target["points"][m.trainIdx] for m in good])
        cv2.setRNGSeed(0)
        transform, mask = cv2.findHomography(a, b, cv2.RANSAC, 3.0, maxIters=1000, confidence=0.995)
        if transform is None or mask is None or not np.isfinite(transform).all():
            return answer("unknown", "geometry_failed")
        inliers = mask.ravel().astype(bool)
        evidence["inlier_ratio"] = float(inliers.mean())
        fractions = [
            float(cv2.contourArea(cv2.convexHull(p[inliers])) / f["gray"].size)
            for p, f in [(a, source), (b, target)]
        ]
        evidence["inlier_hull_fractions"] = fractions
        if (
            evidence["inlier_ratio"] < protocol.min_inlier_ratio
            or min(fractions) < protocol.min_hull_fraction
        ):
            return answer("unknown", "weak_or_localized_geometry")
        shape = target["gray"].shape
        warped = cv2.warpPerspective(source["gray"], transform, (shape[1], shape[0]))
        support = cv2.warpPerspective(
            np.ones_like(source["gray"]), transform, (shape[1], shape[0]), flags=cv2.INTER_NEAREST
        )
        valid = cv2.erode(support, np.ones((5, 5), np.uint8)).astype(bool)
        overlap = float(valid.mean())
        evidence["target_overlap"] = overlap
        if overlap < 0.4:
            return answer("different", "target_view_not_covered")
        if overlap < protocol.min_overlap:
            return answer("unknown", "occlusion_crop_or_parallax")
        x, y = warped[valid].astype(float), target["gray"][valid].astype(float)
        xs, ys = np.percentile(x, [10, 90]), np.percentile(y, [10, 90])
        if xs[1] - xs[0] < protocol.min_dynamic_range:
            return answer("unknown", "unobservable_registered_region")
        gain = float((ys[1] - ys[0]) / (xs[1] - xs[0]))
        offset = float(np.median(y) - gain * np.median(x))
        evidence["photometric_gain"] = gain
        if not 0.2 <= gain <= 5:
            return answer("unknown", "extreme_photometric_mapping")
        residual = np.abs(np.clip(warped.astype(float) * gain + offset, 0, 255) - target["gray"])
        values = residual[valid]
        tiles = []
        for ys0 in np.array_split(np.arange(shape[0]), protocol.tile_grid):
            for xs0 in np.array_split(np.arange(shape[1]), protocol.tile_grid):
                v = valid[np.ix_(ys0, xs0)]
                tile = residual[np.ix_(ys0, xs0)]
                if v.size and v.mean() >= 0.9:
                    tiles.append(float(tile[v].mean()))
        if not tiles:
            return answer("unknown", "insufficient_residual_support")
        evidence.update(
            {
                "residual_mean": float(values.mean()),
                "residual_p95": float(np.percentile(values, 95)),
                "maximum_tile_residual": max(tiles),
            }
        )
        if (
            evidence["residual_mean"] <= protocol.mean_residual
            and evidence["residual_p95"] <= protocol.p95_residual
            and evidence["maximum_tile_residual"] <= protocol.tile_residual
        ):
            return answer("cover", "geometry_and_photometric_consistency")
        # Residual may be motion, shadows, noise, water/leaves or registration error.
        return answer("unknown", "unexplained_local_change")
    except cv2.error:
        return answer("unknown", "opencv_geometry_failure")


def quality_allows(keeper, target, protocol):
    keys = ("total", "sharpness", "exposure")
    if any(
        not isinstance(q.get(k), (int, float)) or not math.isfinite(q[k])
        for q in (keeper, target)
        for k in keys
    ):
        return False
    return (
        keeper["total"] >= target["total"]
        and keeper["sharpness"] >= target["sharpness"] * protocol.quality_sharpness_ratio
        and keeper["exposure"] >= target["exposure"] - protocol.quality_exposure_tolerance
    )


def select(frames, edges, protocol):
    """Keep-first deterministic order; a keeper is never later rejected."""
    if len({f["id"] for f in frames}) != len(frames):
        raise ValueError("duplicate frame id")

    def order(f):
        score = f["quality"].get("total")
        return (
            -(score if isinstance(score, (int, float)) and math.isfinite(score) else float("-inf")),
            f["id"],
        )

    keepers = []
    decisions = {}
    for frame in sorted(frames, key=order):
        witness = next(
            (
                k
                for k in keepers
                if edges.get((k["id"], frame["id"]), {}).get("relation") == "cover"
                and quality_allows(k["quality"], frame["quality"], protocol)
            ),
            None,
        )
        if witness is None:
            keepers.append(frame)
            decisions[frame["id"]] = {"decision": "keep", "covered_by": None}
        else:
            decisions[frame["id"]] = {"decision": "reject", "covered_by": witness["id"]}
    return decisions


def audit(decisions, edges, references):
    """Independent references are supplied by caller; inferred edges are not truth."""
    structural, false_cover, unknown_reference, checked = [], [], [], 0
    for target, decision in decisions.items():
        if decision["decision"] != "reject":
            continue
        source = decision["covered_by"]
        if (
            source == target
            or decisions.get(source, {}).get("decision") != "keep"
            or edges.get((source, target), {}).get("relation") != "cover"
        ):
            structural.append(target)
        reference = references.get((source, target), "unknown")
        if reference == "unknown":
            unknown_reference.append(target)
        else:
            checked += 1
            if reference == "different":
                false_cover.append(target)
    return {
        "structural_violations": structural,
        "reference_checked_rejects": checked,
        "false_covered_rejects": false_cover,
        "unjudged_rejects": unknown_reference,
    }


def run(frames, protocol):
    started = time.perf_counter()
    pairs, omitted = candidates(frames, protocol)
    prepared, edges = {}, {}
    feature_seconds = 0.0
    for a, b in pairs:
        for key in (a, b):
            if key not in prepared and time.perf_counter() - started <= protocol.max_seconds:
                frame = next(f for f in frames if f["id"] == key)
                prepared[key] = prepare(frame["rgb"], protocol)
                if frame.get("hashes", {}).get("phash") is not None:
                    prepared[key]["phash"] = frame["hashes"]["phash"]
                feature_seconds += prepared[key]["feature_seconds"]
        for source, target in [(a, b), (b, a)]:
            if (
                time.perf_counter() - started > protocol.max_seconds
                or source not in prepared
                or target not in prepared
            ):
                edge = {
                    "relation": "unknown",
                    "reason": "time_budget",
                    "evidence": {},
                    "match_seconds": 0.0,
                }
            else:
                edge = relation(prepared[source], prepared[target], protocol)
                if time.perf_counter() - started > protocol.max_seconds:
                    edge.update(relation="unknown", reason="time_budget")
            edges[(source, target)] = edge
    return {
        "decisions": select(frames, edges, protocol),
        "edges": edges,
        "feature_seconds": feature_seconds,
        "match_seconds": sum(e["match_seconds"] for e in edges.values()),
        "elapsed_seconds": time.perf_counter() - started,
        "budget_exceeded": time.perf_counter() - started > protocol.max_seconds,
        "candidate_pairs": len(pairs),
        "omitted_pairs": omitted,
    }
