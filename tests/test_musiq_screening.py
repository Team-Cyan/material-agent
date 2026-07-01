import asyncio
import logging
import types
from types import SimpleNamespace

import numpy as np

from material_agent.adapters.screening.musiq import MusiqFastScreeningAdapter
from material_agent.domain.scoring_engine import RawFrame, compute_scores


def _base_config() -> dict:
    return {
        "output_language": "zh",
        "scorers": {
            "exposure": {
                "enabled": True,
                "weight": 0.5,
                "min_score": 0.0,
                "overexpose_threshold": 0.02,
                "overexpose_hard_limit": 2.0,
                "underexpose_threshold": 0.20,
                "underexpose_hard_limit": 2.0,
            },
            "sharpness": {
                "enabled": True,
                "weight": 0.5,
                "min_score": 0.0,
                "min_variance": 50,
                "max_variance": 1000,
            },
            "subject": {"enabled": True},
            "composition": {"enabled": True},
            "lighting": {"enabled": True},
            "color": {"enabled": True},
            "clarity": {"enabled": True},
            "depth": {"enabled": True},
            "mood": {"enabled": True},
        },
        "grouping": {
            "enabled": False,
            "visual_similarity": {"enabled": False},
            "group_guard": {"enabled": False, "min_score": 7.0},
        },
        "preview": {"max_size": 256, "jpeg_quality": 85},
        "scoring": {"pixel_weight": 0.3, "vision_weight": 0.7},
        "scene_weights": {
            "default": {
                "subject": 1 / 7,
                "composition": 1 / 7,
                "lighting": 1 / 7,
                "color": 1 / 7,
                "clarity": 1 / 7,
                "depth": 1 / 7,
                "mood": 1 / 7,
            }
        },
        "screening": {
            "enabled": True,
            "backend": "musiq",
            "tier1_threshold": 0.5,
            "tier2_threshold": 2.5,
            "musiq": {
                "metric": "musiq",
                "device": "cpu",
                "score_divisor": 10.0,
            },
        },
    }


class _VisionOnlyClient:
    def __init__(self):
        self.score_image_called = False

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        self.score_image_called = True
        return {
            "scene": "people",
            "scene_raw": "舞台上的人物",
            "subject": 8.0,
            "composition": 8.0,
            "lighting": 8.0,
            "color": 8.0,
            "clarity": 8.0,
            "depth": 8.0,
            "mood": 8.0,
        }

    async def generate_group_commentary(self, group_data: str) -> str:
        return ""

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        return ""


class _FixedFastScreening:
    def __init__(self, score: float | None = None, error: Exception | None = None):
        self.score = score
        self.error = error

    async def score_image_fast(self, jpeg_bytes: bytes) -> float:
        if self.error is not None:
            raise self.error
        return float(self.score)


def test_musiq_adapter_normalizes_scores_with_divisor(monkeypatch):
    adapter = MusiqFastScreeningAdapter({"metric": "musiq", "device": "cpu", "score_divisor": 10.0})

    fake_torch = types.SimpleNamespace(
        inference_mode=lambda: _NullContext(),
        device=lambda name: name,
    )

    class _FakeScore:
        def item(self):
            return 78.0

    class _FakeMetric:
        def __call__(self, _tensor):
            return _FakeScore()

    monkeypatch.setattr(adapter, "_load_runtime", lambda: (fake_torch, object()))
    monkeypatch.setattr(adapter, "_get_metric", lambda: _FakeMetric())
    monkeypatch.setattr(adapter, "_jpeg_bytes_to_tensor", lambda jpeg_bytes, torch_mod: object())

    score = asyncio.run(adapter.score_image_fast(b"jpeg"))

    assert score == 7.8


def test_musiq_adapter_falls_back_to_helper_python_when_runtime_is_missing(monkeypatch, tmp_path):
    helper_python = tmp_path / "musiq-helper" / "bin" / "python"
    helper_python.parent.mkdir(parents=True)
    helper_python.write_text("", encoding="utf-8")

    adapter = MusiqFastScreeningAdapter(
        {
            "metric": "musiq",
            "device": "cpu",
            "score_divisor": 10.0,
            "python_bin": str(helper_python),
        }
    )

    monkeypatch.setattr(adapter, "_load_runtime", lambda: (_ for _ in ()).throw(ModuleNotFoundError("pyiqa")))
    monkeypatch.setattr(adapter, "_score_via_helper", lambda jpeg_bytes, python_bin: 6.2)

    score = asyncio.run(adapter.score_image_fast(b"jpeg"))

    assert score == 6.2


def test_musiq_adapter_tolerates_helper_stdout_noise(monkeypatch, tmp_path):
    helper_python = tmp_path / "musiq-helper" / "bin" / "python"
    helper_python.parent.mkdir(parents=True)
    helper_python.write_text("", encoding="utf-8")

    adapter = MusiqFastScreeningAdapter(
        {
            "metric": "musiq",
            "device": "cpu",
            "score_divisor": 10.0,
            "python_bin": str(helper_python),
        }
    )

    monkeypatch.setattr(
        "material_agent.adapters.screening.musiq.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout='Loading pretrained model MUSIQ from /tmp/model.pth\n{"overall": 6.2}',
            stderr="",
        ),
    )

    score = adapter._score_via_helper(b"jpeg", helper_python)

    assert score == 6.2


def test_compute_scores_uses_independent_fast_screening_port():
    cfg = _base_config()
    client = _VisionOnlyClient()
    fast_screening = _FixedFastScreening(score=1.0)
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )

    bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=fast_screening))

    assert bundle.status == "fast_rejected"
    assert client.score_image_called is False


def test_compute_scores_skips_fast_screening_when_musiq_unavailable(caplog):
    cfg = _base_config()
    client = _VisionOnlyClient()
    fast_screening = _FixedFastScreening(error=ModuleNotFoundError("pyiqa"))
    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )

    with caplog.at_level(logging.INFO, logger="material_agent"):
        bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=fast_screening))

    assert bundle.status == "full"
    assert client.score_image_called is True
    assert "Fast screening skipped after parse failure" in "\n".join(r.message for r in caplog.records)


def test_compute_scores_uses_fast_screening_signal_object_as_prior_not_total():
    cfg = _base_config()
    client = _VisionOnlyClient()

    class _SignalFastScreening:
        async def score_image_fast(self, jpeg_bytes: bytes) -> dict:
            return {
                "technical_ok": 0.1,
                "subject_clear": 0.2,
                "composition_ok": 0.2,
                "usable_for_selection": 0.1,
            }

    frame = RawFrame(
        pixels=np.full((8, 8), 32000, dtype=np.uint16),
        jpeg_bytes=b"jpeg",
        gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
    )

    bundle = asyncio.run(compute_scores(frame, client, cfg, fast_screening=_SignalFastScreening()))

    assert bundle.screening_prior == 0.14
    assert bundle.total != bundle.screening_prior


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False
