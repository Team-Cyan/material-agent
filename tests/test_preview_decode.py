from types import SimpleNamespace

import cv2
import numpy as np
import rawpy

from material_agent.domain.scoring_engine import decode_raw


def _jpeg_thumb(width: int = 1600, height: int = 1000) -> bytes:
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    rgb[:, :, 0] = 64
    rgb[:, :, 1] = 128
    rgb[:, :, 2] = 192
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


class _FakeRawWithEmbeddedPreview:
    sizes = SimpleNamespace(width=6000, height=4000)

    def __init__(self):
        self.postprocess_called = False

    @property
    def raw_image_visible(self):
        raise AssertionError("decode_raw must not copy full RAW pixels for preview scoring")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_thumb(self):
        return SimpleNamespace(format=rawpy.ThumbFormat.JPEG, data=_jpeg_thumb())

    def postprocess(self, **kwargs):
        self.postprocess_called = True
        raise AssertionError("embedded preview should avoid RAW postprocess")


class _FakeRawWithoutPreview:
    sizes = SimpleNamespace(width=6000, height=4000)

    def __init__(self):
        self.postprocess_called = False

    @property
    def raw_image_visible(self):
        raise AssertionError("decode_raw must not copy full RAW pixels for preview scoring")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_thumb(self):
        raise rawpy.LibRawNoThumbnailError("no thumbnail")

    def postprocess(self, **kwargs):
        self.postprocess_called = True
        return np.full((2000, 3000, 3), 128, dtype=np.uint8)


def test_decode_raw_prefers_embedded_preview(monkeypatch, tmp_path):
    fake_raw = _FakeRawWithEmbeddedPreview()
    monkeypatch.setattr("material_agent.domain.scoring_engine.rawpy.imread", lambda path: fake_raw)
    raw_file = tmp_path / "image.ARW"
    raw_file.write_bytes(b"fake")

    frame = decode_raw(str(raw_file), {"max_size": 1024, "jpeg_quality": 85, "prefer_embedded": True})

    assert fake_raw.postprocess_called is False
    assert frame.pixels is None
    assert frame.preview_source == "embedded"
    assert frame.original_size == (6000, 4000)
    assert frame.preview_size == (1024, 640)
    assert frame.gray.shape == (640, 1024)
    assert frame.jpeg_bytes


def test_decode_raw_falls_back_to_half_size_postprocess(monkeypatch, tmp_path):
    fake_raw = _FakeRawWithoutPreview()
    monkeypatch.setattr("material_agent.domain.scoring_engine.rawpy.imread", lambda path: fake_raw)
    raw_file = tmp_path / "image.ARW"
    raw_file.write_bytes(b"fake")

    frame = decode_raw(str(raw_file), {"max_size": 1024, "jpeg_quality": 85, "prefer_embedded": True})

    assert fake_raw.postprocess_called is True
    assert frame.pixels is None
    assert frame.preview_source == "raw_postprocess"
    assert frame.preview_size == (1024, 682)
    assert frame.gray.shape == (682, 1024)
