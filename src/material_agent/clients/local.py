from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image

from ..utils.constants import VISION_DIMS


class AsyncLocalClient:
    """Local, non-generative fallback used by the NAS-first material-agent path."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.output_language = self.config.get("output_language", "zh")

    async def score_image(self, jpeg_bytes: bytes) -> dict:
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        rgb = np.asarray(image, dtype=np.float32) / 255.0
        gray = rgb.mean(axis=2)

        brightness = float(gray.mean())
        contrast = float(gray.std())
        saturation = float((rgb.max(axis=2) - rgb.min(axis=2)).mean())
        high_clip = float((gray > 0.97).mean())
        low_clip = float((gray < 0.03).mean())
        gy, gx = np.gradient(gray)
        edge_energy = float(np.sqrt(gx * gx + gy * gy).mean())

        lighting = _clamp10(8.0 - abs(brightness - 0.48) * 12.0 - (high_clip + low_clip) * 15.0)
        color = _clamp10(4.5 + saturation * 8.0)
        clarity = _clamp10(3.5 + edge_energy * 45.0 + contrast * 8.0)
        composition = _clamp10(5.8 + min(contrast, 0.25) * 6.0)
        subject = _clamp10((clarity * 0.45) + (lighting * 0.35) + 1.0)
        depth = _clamp10(4.5 + contrast * 10.0)
        mood = _clamp10((lighting + color + depth) / 3.0)

        scores = {
            "subject": subject,
            "composition": composition,
            "lighting": lighting,
            "color": color,
            "clarity": clarity,
            "depth": depth,
            "mood": mood,
        }
        return {
            "scene": "other",
            "scene_raw": "local heuristic" if self.output_language == "en" else "本地启发式",
            **{dim: round(scores.get(dim, 5.0), 2) for dim in VISION_DIMS},
        }

    async def score_image_fast(self, jpeg_bytes: bytes) -> dict[str, float]:
        full = await self.score_image(jpeg_bytes)
        clarity = float(full.get("clarity", 5.0)) / 10.0
        lighting = float(full.get("lighting", 5.0)) / 10.0
        composition = float(full.get("composition", 5.0)) / 10.0
        usable = (clarity + lighting + composition) / 3.0
        return {
            "technical_ok": _clamp01((clarity + lighting) / 2.0),
            "subject_clear": _clamp01(clarity),
            "composition_ok": _clamp01(composition),
            "usable_for_selection": _clamp01(usable),
        }

    async def generate_group_commentary(self, group_data: str) -> str:
        raise RuntimeError("local backend does not generate model commentary")

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
        raise RuntimeError("local backend does not generate model commentary")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp10(value: float) -> float:
    return max(0.0, min(10.0, float(value)))
