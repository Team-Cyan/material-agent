import logging
import cv2
import numpy as np
import rawpy
from dataclasses import dataclass, field

from ..clients.protocol import BackendClient
from ..domain.layered_decision import summarize_signals
from ..ports.model_ports import FastScreeningPort
from ..scorers.aggregator import Aggregator
from ..scorers.base import ScorerResult
from ..scorers.exposure import ExposureScorer
from ..scorers.sharpness import SharpnessScorer
from ..utils.constants import (
    ALL_ABBR,
    ALL_DIMS,
    AESTHETIC_SOURCE_MAP,
    VISION_DIMS,
    dim_label,
    VISIBLE_BREAKDOWN_DIMS,
)

_log = logging.getLogger("material_agent")


@dataclass
class RawFrame:
    jpeg_bytes: bytes
    gray: object
    pixels: object | None = None
    preview_source: str = "unknown"
    original_size: tuple[int, int] | None = None
    preview_size: tuple[int, int] | None = None
    focus_assessment: str = "preview_proxy"


@dataclass
class ScoreBundle:
    scores: dict[str, float]
    total: float
    boosted: bool
    meta: dict
    scene: str
    scene_raw: str
    instructions: str
    status: str = "full"
    extra: dict = field(default_factory=dict)
    decision: str | None = None
    decision_reasons: list[str] = field(default_factory=list)
    screening_prior: float | None = None
    visible_breakdown: dict[str, float] = field(default_factory=dict)
    policy_version: str = "layered-v1"
    signals: list[dict] = field(default_factory=list)


def screening_prior_from_signals(signals: dict[str, float]) -> float:
    return round(
        signals["technical_ok"] * 0.35
        + signals["subject_clear"] * 0.30
        + signals["composition_ok"] * 0.15
        + signals["usable_for_selection"] * 0.20,
        4,
    )


def decode_raw(file_path: str, preview_config: dict) -> RawFrame:
    with rawpy.imread(file_path) as raw:
        original_size = _raw_size(raw)
        if preview_config.get("prefer_embedded", True):
            preview_rgb = _embedded_preview_rgb(raw)
            preview_source = "embedded"
        else:
            preview_rgb = None
            preview_source = "raw_postprocess"
        if preview_rgb is None:
            preview_rgb = raw.postprocess(use_camera_wb=True, output_bps=8, half_size=True)
            preview_source = "raw_postprocess"

    max_size = int(preview_config["max_size"])
    h, w = preview_rgb.shape[:2]
    scale = min(max_size / max(h, w), 1.0)
    if scale < 1.0:
        preview_rgb = cv2.resize(
            preview_rgb,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    gray = cv2.cvtColor(preview_rgb, cv2.COLOR_RGB2GRAY)
    _, jpeg_enc = cv2.imencode(
        ".jpg", preview_rgb, [cv2.IMWRITE_JPEG_QUALITY, preview_config["jpeg_quality"]]
    )
    preview_h, preview_w = preview_rgb.shape[:2]
    return RawFrame(
        jpeg_bytes=jpeg_enc.tobytes(),
        gray=gray,
        pixels=None,
        preview_source=preview_source,
        original_size=original_size,
        preview_size=(preview_w, preview_h),
        focus_assessment="preview_proxy",
    )


def _embedded_preview_rgb(raw) -> np.ndarray | None:
    try:
        thumb = raw.extract_thumb()
    except rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError:
        return None
    if thumb.format is rawpy.ThumbFormat.JPEG:
        encoded = np.frombuffer(thumb.data, dtype=np.uint8)
        preview_bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if preview_bgr is None:
            return None
        return cv2.cvtColor(preview_bgr, cv2.COLOR_BGR2RGB)
    if thumb.format is rawpy.ThumbFormat.BITMAP:
        preview = np.asarray(thumb.data)
        if preview.ndim == 2:
            return cv2.cvtColor(preview, cv2.COLOR_GRAY2RGB)
        if preview.shape[2] >= 3:
            return preview[:, :, :3].astype(np.uint8, copy=False)
    return None


def _raw_size(raw) -> tuple[int, int] | None:
    sizes = getattr(raw, "sizes", None)
    if sizes is None:
        return None
    width = (
        getattr(sizes, "width", None)
        or getattr(sizes, "iwidth", None)
        or getattr(sizes, "raw_width", None)
    )
    height = (
        getattr(sizes, "height", None)
        or getattr(sizes, "iheight", None)
        or getattr(sizes, "raw_height", None)
    )
    if width is None or height is None:
        return None
    return int(width), int(height)


def build_score_instructions(scores: dict[str, float]) -> str:
    return " ".join(
        f"{abbr}:{scores[dim]:.1f}" for dim, abbr in zip(ALL_DIMS, ALL_ABBR) if dim in scores
    )


def build_xmp_instructions(scores: dict[str, float], output_language: str = "zh") -> str:
    return " ".join(
        f"{dim_label(dim, output_language)}:{scores[dim]:.1f}" for dim in ALL_DIMS if dim in scores
    )


def build_visible_breakdown_instructions(
    scores: dict[str, float], output_language: str = "zh"
) -> str:
    ordered_dims = [dim for dim in VISIBLE_BREAKDOWN_DIMS if dim in scores]
    if not ordered_dims:
        ordered_dims = list(scores)
    return " ".join(f"{dim_label(dim, output_language)}:{scores[dim]:.1f}" for dim in ordered_dims)


def _build_rejected_bundle(
    *,
    status: str,
    total: float,
    scores: dict[str, float],
    meta: dict,
    config: dict,
    reason: str,
    scene: str = "other",
    scene_raw: str = "",
    extra: dict | None = None,
) -> ScoreBundle:
    signals = _build_layered_signals(scores=scores, meta=meta, scene=scene, config=config)
    summary = summarize_signals(signals, scene=scene, config=config) if signals else None
    decision_reasons = [reason]
    if summary is not None:
        for existing_reason in summary.decision_reasons:
            if existing_reason not in decision_reasons:
                decision_reasons.append(existing_reason)
    return ScoreBundle(
        scores=scores,
        total=round(total, 2),
        boosted=False,
        meta=meta,
        scene=scene,
        scene_raw=scene_raw,
        instructions=build_score_instructions(scores),
        status=status,
        extra=extra or {},
        decision="reject",
        decision_reasons=decision_reasons,
        screening_prior=summary.screening_prior if summary is not None else None,
        visible_breakdown=summary.visible_breakdown if summary is not None else {},
        policy_version=summary.policy_version if summary is not None else "layered-v1",
        signals=signals,
    )


async def compute_scores(
    frame: RawFrame,
    client: BackendClient,
    config: dict,
    *,
    fast_screening: FastScreeningPort | None = None,
) -> ScoreBundle:
    results: list[ScorerResult] = []
    meta: dict = _build_frame_meta(frame, config)
    exposure_scorer = None

    exp_cfg = config["scorers"]["exposure"]
    if exp_cfg["enabled"]:
        exposure_scorer = ExposureScorer(exp_cfg)
        r = exposure_scorer.score_image(frame.gray)
        results.append(r)
        meta.update(r.metadata)

    sharp_cfg = config["scorers"]["sharpness"]
    if sharp_cfg["enabled"]:
        r = SharpnessScorer(sharp_cfg).score_image(frame.gray)
        results.append(r)
        meta.update(r.metadata)

    pixel_results = [r for r in results if r.name not in VISION_DIMS]
    pixel_total = Aggregator.aggregate(pixel_results)
    screening_cfg = config.get("screening", {})
    screening_enabled = screening_cfg.get("enabled", False)
    scores = {r.name: r.score for r in results}

    tier1_threshold = screening_cfg.get("tier1_threshold", 0.5)
    tier2_threshold = screening_cfg.get("tier2_threshold", 0.25)

    if screening_enabled and pixel_total < tier1_threshold:
        _log.info(
            "Pixel screening rejected image pixel_total=%.2f threshold=%.2f",
            pixel_total,
            tier1_threshold,
        )
        return _build_rejected_bundle(
            status="pixel_rejected",
            total=pixel_total,
            scores=scores,
            meta=meta,
            config=config,
            reason="screening_tier1_reject",
        )

    if any(config["scorers"].get(dim, {}).get("enabled") for dim in VISION_DIMS):
        if screening_enabled and fast_screening is not None:
            try:
                fast_result = await fast_screening.score_image_fast(frame.jpeg_bytes)
                effective_tier2_threshold = float(tier2_threshold)
                if isinstance(fast_result, dict):
                    meta["fast_screening_signals"] = fast_result
                    fast_score = screening_prior_from_signals(fast_result)
                    if effective_tier2_threshold > 1.0:
                        effective_tier2_threshold = round(effective_tier2_threshold / 10.0, 4)
                else:
                    fast_score = float(fast_result)
                meta["fast_score"] = fast_score
                _log.info(
                    "Fast screening score=%.2f threshold=%.2f",
                    fast_score,
                    effective_tier2_threshold,
                )
                if fast_score < effective_tier2_threshold:
                    _log.info(
                        "Fast screening rejected image fast_score=%.2f threshold=%.2f",
                        fast_score,
                        effective_tier2_threshold,
                    )
                    scoring_cfg = config.get("scoring", {})
                    total = _combine_scores(
                        pixel_total=pixel_total,
                        vision_total=fast_score,
                        pixel_results=pixel_results,
                        pixel_weight=scoring_cfg.get("pixel_weight", 0.3),
                        vision_weight=scoring_cfg.get("vision_weight", 0.7),
                    )
                    return _build_rejected_bundle(
                        status="fast_rejected",
                        total=total,
                        scores=scores,
                        meta=meta,
                        config=config,
                        reason="screening_tier2_reject",
                        extra={
                            "fast_score": fast_score,
                            "fast_screening_signals": meta.get("fast_screening_signals"),
                        },
                    )
            except Exception as error:
                meta["fast_error"] = str(error)
                _log.warning("Fast screening skipped after parse failure: %s", error)

        raw_scores = await client.score_image(frame.jpeg_bytes)
        _merge_backend_meta(meta, raw_scores)
        scene = raw_scores.get("scene", "other")
        scene_raw = raw_scores.get("scene_raw", "")
        if exposure_scorer is not None:
            exposure_result = exposure_scorer.score_image(frame.gray, scene=scene)
            results = [r for r in results if r.name != "exposure"]
            results.append(exposure_result)
            meta.update(exposure_result.metadata)
        for dim in VISION_DIMS:
            if not config["scorers"].get(dim, {}).get("enabled", False):
                continue
            try:
                score = max(0.0, min(10.0, float(raw_scores.get(dim, 0))))
            except TypeError, ValueError:
                score = 0.0
            results.append(
                ScorerResult(
                    name=dim,
                    score=score,
                    enabled=True,
                    weight=config["scorers"].get(dim, {}).get("weight", 0.0),
                    min_score=config["scorers"].get(dim, {}).get("min_score", 0.0),
                )
            )
    else:
        scene = "other"
        scene_raw = ""

    scores = {r.name: r.score for r in results}
    pixel_results = [r for r in results if r.name not in VISION_DIMS]
    vision_scores = {r.name: r.score for r in results if r.name in VISION_DIMS}
    scoring_cfg = config.get("scoring", {})
    total = Aggregator.aggregate_with_scene(
        pixel_results,
        vision_scores,
        scene,
        config.get("scene_weights", {}),
        pixel_weight=scoring_cfg.get("pixel_weight", 0.3),
        vision_weight=scoring_cfg.get("vision_weight", 0.7),
    )
    signals = _build_layered_signals(
        scores=scores,
        meta=meta,
        scene=scene,
        config=config,
    )
    summary = summarize_signals(signals, scene=scene, config=config)
    instructions = build_score_instructions(scores)
    local_total = summary.total_score
    return ScoreBundle(
        scores=scores,
        total=local_total,
        boosted=False,
        meta=meta,
        scene=scene,
        scene_raw=scene_raw,
        instructions=instructions,
        extra={
            "aggregated_total": total,
            "layered_total": local_total,
        },
        decision=summary.decision,
        decision_reasons=summary.decision_reasons,
        screening_prior=summary.screening_prior,
        visible_breakdown=summary.visible_breakdown,
        policy_version=summary.policy_version,
        signals=signals,
    )


def _combine_scores(
    *,
    pixel_total: float,
    vision_total: float,
    pixel_results: list[ScorerResult],
    pixel_weight: float,
    vision_weight: float,
) -> float:
    if not pixel_results:
        return round(vision_total, 2)
    w_sum = pixel_weight + vision_weight
    if w_sum <= 0:
        return round(pixel_total, 2)
    return round((pixel_total * pixel_weight + vision_total * vision_weight) / w_sum, 2)


def _build_layered_signals(
    *, scores: dict[str, float], meta: dict, scene: str, config: dict
) -> list[dict]:
    focus_integrity = _mean_known([scores.get("sharpness"), scores.get("clarity")])
    clarity_proxy = scores.get("clarity", focus_integrity)
    focus_confidence = _focus_confidence(meta)
    subject_focus = focus_integrity if focus_integrity is not None else scores.get("subject")
    focus_source = "preview_proxy" if meta.get("focus_assessment") == "preview_proxy" else "cpu"
    technical_quality = _mean_known(
        [
            scores.get("exposure"),
            focus_integrity,
            clarity_proxy,
            clarity_proxy,
        ]
    )
    screening_prior = meta.get("fast_score", technical_quality)
    signals = [
        {
            "stage": "technical",
            "signal_key": "exposure_control",
            "value": scores.get("exposure"),
            "confidence": 1.0,
            "source": "cpu",
        },
        {
            "stage": "technical",
            "signal_key": "focus_integrity",
            "value": focus_integrity,
            "confidence": focus_confidence,
            "source": focus_source,
        },
        {
            "stage": "technical",
            "signal_key": "motion_blur",
            "value": scores.get("clarity", focus_integrity),
            "confidence": 0.7,
            "source": "vision",
        },
        {
            "stage": "technical",
            "signal_key": "noise_cleanliness",
            "value": scores.get("clarity", focus_integrity),
            "confidence": 0.7,
            "source": "vision",
        },
        {
            "stage": "technical",
            "signal_key": "technical_quality",
            "value": technical_quality,
            "confidence": 1.0,
            "source": "aggregate",
        },
        {
            "stage": "aggregate",
            "signal_key": "subject_focus",
            "value": subject_focus,
            "confidence": focus_confidence if focus_integrity is not None else 0.35,
            "source": focus_source if focus_integrity is not None else "subject_proxy",
        },
        {
            "stage": "screening",
            "signal_key": "screening_prior",
            "value": screening_prior,
            "confidence": 1.0,
            "source": "musiq" if "fast_score" in meta else "aggregate",
            "model_name": "musiq" if "fast_score" in meta else None,
            "model_version": "1" if "fast_score" in meta else None,
        },
    ]
    if scene == "people" and config.get("portrait_face_eye", {}).get("enabled", False):
        portrait_signal = _estimate_portrait_face_eye_usability(scores)
        if portrait_signal is not None:
            signals.append(
                {
                    "stage": "technical",
                    "signal_key": "portrait_face_eye_usability",
                    "value": portrait_signal,
                    "confidence": min(0.4, focus_confidence),
                    "source": "preview_proxy",
                }
            )
    for public_dim, source_dim in AESTHETIC_SOURCE_MAP.items():
        signals.append(
            {
                "stage": "aesthetic",
                "signal_key": public_dim,
                "value": scores.get(source_dim),
                "confidence": 1.0,
                "source": "vision",
            }
        )
    aesthetic = meta.get("aesthetic")
    if isinstance(aesthetic, dict) and aesthetic.get("status") == "model":
        signals.append(
            {
                "stage": "aesthetic",
                "signal_key": "overall_aesthetic",
                "value": aesthetic.get("score"),
                "confidence": 1.0,
                "source": "learned_model",
                "model_name": aesthetic.get("model_name"),
                "model_version": aesthetic.get("model_version"),
            }
        )
    return [signal for signal in signals if signal.get("value") is not None]


def _build_frame_meta(frame: RawFrame, config: dict) -> dict:
    meta = {
        "preview_source": getattr(frame, "preview_source", "unknown"),
        "focus_assessment": getattr(frame, "focus_assessment", "preview_proxy"),
    }
    original_size = getattr(frame, "original_size", None)
    preview_size = getattr(frame, "preview_size", None)
    if original_size is not None:
        meta["original_size"] = list(original_size)
    if preview_size is not None:
        meta["preview_size"] = list(preview_size)
    downscale_ratio = _downscale_ratio(frame)
    if downscale_ratio is not None:
        meta["preview_downscale_ratio"] = downscale_ratio
        warning_ratio = float(
            config.get("focus_integrity", {}).get("downscale_warning_ratio", 3.0) or 3.0
        )
        if downscale_ratio >= warning_ratio:
            meta["focus_review_required"] = True
            meta["focus_review_reason"] = "high_resolution_roi_not_run"
    return meta


def _merge_backend_meta(meta: dict, raw_scores: dict) -> None:
    for key in (
        "_scoring_mode",
        "_runtime",
        "_runtime_components",
        "_configured_runtime",
        "_model_stack",
        "_semantic",
        "_quality",
        "_aesthetic",
        "_embedding",
        "_face",
        "_timing",
    ):
        value = raw_scores.get(key)
        if value is not None:
            meta[key.removeprefix("_")] = value


def _downscale_ratio(frame: RawFrame) -> float | None:
    original_size = getattr(frame, "original_size", None)
    preview_size = getattr(frame, "preview_size", None)
    if original_size is None or preview_size is None:
        return None
    original_edge = max(original_size)
    preview_edge = max(preview_size)
    if preview_edge <= 0:
        return None
    return round(float(original_edge) / float(preview_edge), 3)


def _focus_confidence(meta: dict) -> float:
    if meta.get("focus_assessment") != "preview_proxy":
        return 1.0
    ratio = meta.get("preview_downscale_ratio")
    if ratio is None:
        return 0.6
    if ratio >= 6:
        return 0.35
    if ratio >= 3:
        return 0.45
    return 0.65


def _estimate_portrait_face_eye_usability(scores: dict[str, float]) -> float | None:
    return _mean_known([scores.get("subject"), scores.get("clarity"), scores.get("sharpness")])


def _mean_known(values: list[float | None]) -> float | None:
    known = [float(value) for value in values if value is not None]
    if not known:
        return None
    return round(sum(known) / len(known), 2)
