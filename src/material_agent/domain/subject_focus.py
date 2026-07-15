from __future__ import annotations

import math
import time

import cv2
import numpy as np


def analyze_subject_focus(
    gray: np.ndarray,
    *,
    detection: dict | None,
    focus_config: dict,
    sharpness_config: dict,
) -> dict:
    """Measure global blur separately from authoritative subject/eye focus."""

    started = time.perf_counter()
    image = np.asarray(gray, dtype=np.uint8)
    global_variance = _laplacian_variance(_normalize_patch(image, 512))
    global_score = _variance_score(global_variance, sharpness_config)
    primary = detection.get("primary_subject") if isinstance(detection, dict) else None
    faces = detection.get("faces", []) if isinstance(detection, dict) else []
    bbox = primary.get("bbox") if isinstance(primary, dict) else None
    person_bbox = bbox if isinstance(primary, dict) and primary.get("label") == "person" else None
    source = "detected_object"
    confidence = float(primary.get("confidence", 0.0)) if isinstance(primary, dict) else 0.0
    if bbox is None and faces:
        face = _select_primary_face(faces)
        bbox = _expand_bbox(face["bbox"], 0.75)
        source = "detected_face"
        confidence = float(face.get("confidence", 0.0))
    if bbox is None:
        bbox = _saliency_bbox(image)
        source = "saliency_fallback"
        confidence = 0.35
    bbox = _expand_bbox(bbox, float(focus_config.get("roi_expand_ratio", 0.12)))
    subject_patch = _crop_normalized(image, bbox)
    subject_variance = _laplacian_variance(_normalize_patch(subject_patch, 512))
    subject_absolute = _variance_score(subject_variance, sharpness_config)
    relative_score = _relative_focus_score(subject_variance, global_variance)
    subject_score = round(subject_absolute * 0.75 + relative_score * 0.25, 4)

    eye_scores = []
    eye_variances = []
    primary_face = _select_primary_face(faces, subject_bbox=person_bbox) if faces else None
    if primary_face is not None:
        face_width = max(0.01, primary_face["bbox"][2] - primary_face["bbox"][0])
        eye_radius = max(0.012, face_width * float(focus_config.get("eye_roi_ratio", 0.16)))
        for name in ("left_eye", "right_eye"):
            point = primary_face.get("landmarks", {}).get(name)
            if not point:
                continue
            eye_bbox = [
                point[0] - eye_radius,
                point[1] - eye_radius,
                point[0] + eye_radius,
                point[1] + eye_radius,
            ]
            patch = _crop_normalized(image, eye_bbox)
            if patch.size < 64:
                continue
            variance = _laplacian_variance(_normalize_patch(patch, 192))
            eye_variances.append(round(variance, 6))
            eye_scores.append(_variance_score(variance, sharpness_config))
    eye_score = round(float(np.mean(eye_scores)), 4) if eye_scores else None
    final_score = subject_score
    if eye_score is not None:
        final_score = round(subject_score * 0.4 + eye_score * 0.6, 4)
        source = "eye_roi"
        confidence = max(confidence, 0.75)

    return {
        "mode": "subject_roi",
        "score": max(0.0, min(10.0, final_score)),
        "global_blur_score": round(global_score, 4),
        "subject_focus_score": subject_score,
        "eye_focus_score": eye_score,
        "global_laplacian_variance": round(global_variance, 6),
        "subject_laplacian_variance": round(subject_variance, 6),
        "eye_laplacian_variances": eye_variances,
        "face_bbox": primary_face.get("bbox") if primary_face is not None else None,
        "bbox": [round(float(value), 6) for value in bbox],
        "source": source,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "global_blur_guard_failed": global_score
        < float(focus_config.get("global_blur_reject_below", 0.25)),
        "timing_seconds": round(time.perf_counter() - started, 6),
    }


def _laplacian_variance(gray: np.ndarray) -> float:
    if gray.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _variance_score(variance: float, config: dict) -> float:
    minimum = max(0.0, float(config.get("min_variance", 50.0)))
    maximum = max(minimum + 1.0, float(config.get("max_variance", 1000.0)))
    if variance <= minimum:
        return 0.0
    if variance >= maximum:
        return 10.0
    return (variance - minimum) / (maximum - minimum) * 10.0


def _relative_focus_score(subject_variance: float, global_variance: float) -> float:
    ratio = max(1e-6, subject_variance) / max(1e-6, global_variance)
    return max(0.0, min(10.0, 5.0 + 2.5 * math.log2(ratio)))


def _normalize_patch(gray: np.ndarray, max_edge: int) -> np.ndarray:
    height, width = gray.shape[:2]
    scale = min(max_edge / max(height, width), 1.0)
    if scale >= 1.0:
        return gray
    return cv2.resize(
        gray,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _crop_normalized(gray: np.ndarray, bbox) -> np.ndarray:
    height, width = gray.shape[:2]
    x1, y1, x2, y2 = _clamp_bbox(bbox)
    left = max(0, min(width - 1, int(x1 * width)))
    top = max(0, min(height - 1, int(y1 * height)))
    right = max(left + 1, min(width, int(math.ceil(x2 * width))))
    bottom = max(top + 1, min(height, int(math.ceil(y2 * height))))
    return gray[top:bottom, left:right]


def _expand_bbox(bbox, ratio: float) -> list[float]:
    x1, y1, x2, y2 = _clamp_bbox(bbox)
    width, height = x2 - x1, y2 - y1
    return _clamp_bbox(
        [x1 - width * ratio, y1 - height * ratio, x2 + width * ratio, y2 + height * ratio]
    )


def _clamp_bbox(bbox) -> list[float]:
    x1, y1, x2, y2 = [max(0.0, min(1.0, float(value))) for value in bbox]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _select_primary_face(faces: list[dict], *, subject_bbox=None) -> dict:
    def score(face: dict) -> float:
        x1, y1, x2, y2 = face["bbox"]
        area = (x2 - x1) * (y2 - y1)
        center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
        center = 1.0 - min(1.0, math.hypot(center_x - 0.5, center_y - 0.5) / 0.707)
        subject_match = _bbox_coverage(face["bbox"], subject_bbox) if subject_bbox else 0.0
        return (
            area * 0.35
            + center * 0.15
            + float(face.get("confidence", 0.0)) * 0.20
            + subject_match * 0.30
        )

    return max(faces, key=score)


def _bbox_coverage(inner, outer) -> float:
    inner_x1, inner_y1, inner_x2, inner_y2 = _clamp_bbox(inner)
    outer_x1, outer_y1, outer_x2, outer_y2 = _clamp_bbox(outer)
    intersection = max(0.0, min(inner_x2, outer_x2) - max(inner_x1, outer_x1)) * max(
        0.0, min(inner_y2, outer_y2) - max(inner_y1, outer_y1)
    )
    inner_area = max(1e-9, (inner_x2 - inner_x1) * (inner_y2 - inner_y1))
    return min(1.0, intersection / inner_area)


def _saliency_bbox(gray: np.ndarray) -> list[float]:
    small = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    spectrum = np.fft.fft2(small)
    amplitude = np.abs(spectrum)
    log_amplitude = np.log(amplitude + 1e-8)
    residual = log_amplitude - cv2.blur(log_amplitude, (3, 3))
    saliency = np.abs(np.fft.ifft2(np.exp(residual + 1j * np.angle(spectrum)))) ** 2
    saliency = cv2.GaussianBlur(saliency.astype(np.float32), (5, 5), 0)
    total = float(saliency.sum())
    if total <= 0:
        return [0.2, 0.2, 0.8, 0.8]
    yy, xx = np.mgrid[0:64, 0:64]
    center_x = float((saliency * xx).sum() / total) / 63.0
    center_y = float((saliency * yy).sum() / total) / 63.0
    half = 0.24
    return _clamp_bbox([center_x - half, center_y - half, center_x + half, center_y + half])
