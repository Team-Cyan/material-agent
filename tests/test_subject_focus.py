import numpy as np
import asyncio

from material_agent.domain.scoring_engine import RawFrame, compute_scores
from material_agent.domain.subject_focus import analyze_subject_focus


_SHARPNESS = {"min_variance": 10, "max_variance": 1000}
_FOCUS = {
    "roi_expand_ratio": 0.0,
    "eye_roi_ratio": 0.16,
    "global_blur_reject_below": 0.25,
}


def _checkerboard(size: int) -> np.ndarray:
    yy, xx = np.mgrid[:size, :size]
    return ((xx + yy) % 2 * 255).astype(np.uint8)


def test_subject_focus_uses_detected_object_roi():
    gray = np.full((256, 256), 128, dtype=np.uint8)
    gray[64:192, 64:192] = _checkerboard(128)
    detection = {
        "primary_subject": {"label": "dog", "confidence": 0.91, "bbox": [0.25, 0.25, 0.75, 0.75]},
        "faces": [],
    }

    result = analyze_subject_focus(
        gray, detection=detection, focus_config=_FOCUS, sharpness_config=_SHARPNESS
    )

    assert result["source"] == "detected_object"
    assert result["confidence"] == 0.91
    assert result["subject_focus_score"] >= result["global_blur_score"]
    assert result["timing_seconds"] >= 0


def test_subject_focus_uses_eye_landmarks_for_people():
    gray = np.full((256, 256), 128, dtype=np.uint8)
    gray[72:184, 72:184] = _checkerboard(112)
    detection = {
        "primary_subject": {"label": "person", "confidence": 0.8, "bbox": [0.25, 0.2, 0.75, 0.8]},
        "faces": [
            {
                "confidence": 0.95,
                "bbox": [0.3, 0.25, 0.7, 0.75],
                "landmarks": {"left_eye": [0.42, 0.42], "right_eye": [0.58, 0.42]},
            }
        ],
    }

    result = analyze_subject_focus(
        gray, detection=detection, focus_config=_FOCUS, sharpness_config=_SHARPNESS
    )

    assert result["source"] == "eye_roi"
    assert result["eye_focus_score"] is not None
    assert len(result["eye_laplacian_variances"]) == 2


def test_subject_focus_selects_face_inside_primary_person():
    gray = _checkerboard(256)
    target_face = {
        "confidence": 0.80,
        "bbox": [0.55, 0.25, 0.75, 0.55],
        "landmarks": {"left_eye": [0.61, 0.36], "right_eye": [0.69, 0.36]},
    }
    other_face = {
        "confidence": 0.99,
        "bbox": [0.05, 0.15, 0.35, 0.60],
        "landmarks": {"left_eye": [0.14, 0.30], "right_eye": [0.26, 0.30]},
    }
    detection = {
        "primary_subject": {
            "label": "person",
            "confidence": 0.9,
            "bbox": [0.5, 0.1, 0.85, 0.9],
        },
        "faces": [other_face, target_face],
    }

    result = analyze_subject_focus(
        gray, detection=detection, focus_config=_FOCUS, sharpness_config=_SHARPNESS
    )

    assert result["face_bbox"] == target_face["bbox"]


def test_subject_focus_falls_back_to_spectral_saliency_without_detection():
    gray = np.full((256, 256), 128, dtype=np.uint8)
    gray[120:180, 140:200] = _checkerboard(60)

    result = analyze_subject_focus(
        gray, detection=None, focus_config=_FOCUS, sharpness_config=_SHARPNESS
    )

    assert result["source"] == "saliency_fallback"
    assert result["confidence"] == 0.35
    assert all(0.0 <= value <= 1.0 for value in result["bbox"])


class _MustNotRunClient:
    async def score_image(self, jpeg_bytes):
        raise AssertionError("model stage must not run after catastrophic global blur")


def test_catastrophic_global_blur_rejects_before_model_stage():
    config = {
        "scorers": {
            "exposure": {"enabled": False},
            "sharpness": {
                "enabled": True,
                "weight": 1.0,
                "min_score": 0.0,
                "min_variance": 50,
                "max_variance": 1000,
            },
            "subject": {"enabled": True},
        },
        "focus_integrity": {
            "enabled": True,
            "mode": "subject_roi",
            "global_blur_reject_below": 0.25,
        },
        "screening": {"enabled": False},
        "scoring": {},
    }
    frame = RawFrame(jpeg_bytes=b"unused", gray=np.full((64, 64), 128, dtype=np.uint8))

    result = asyncio.run(compute_scores(frame, _MustNotRunClient(), config))

    assert result.status == "catastrophic_blur_rejected"
    assert result.decision == "reject"
    assert "global_catastrophic_blur" in result.decision_reasons
    assert result.meta["subject_focus"]["source"] == "global_blur_guard"
