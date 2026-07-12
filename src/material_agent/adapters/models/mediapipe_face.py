from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


class FaceRuntime(Protocol):
    def detect(self, image: Image.Image) -> list[list[tuple[float, float]]]: ...


class MediaPipeFaceAdapter:
    """Optional MediaPipe Face Landmarker adapter for portrait structure signals."""

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: FaceRuntime | None = None):
        self.config = config or {}
        self.model_asset_path = str(
            Path(
                self.config.get(
                    "model_asset_path", "~/.material-agent/models/face_landmarker.task"
                )
            ).expanduser()
        )
        self.num_faces = int(self.config.get("num_faces", 5))
        self.min_detection_confidence = float(
            self.config.get("min_detection_confidence", 0.5)
        )
        self._runtime = runtime

    async def detect_faces(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._detect_sync, jpeg_bytes)

    def _detect_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is None:
            runtime = _MediaPipeRuntime(
                model_asset_path=self.model_asset_path,
                num_faces=self.num_faces,
                min_detection_confidence=self.min_detection_confidence,
            )
            self._runtime = runtime
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        faces = runtime.detect(image)
        area_ratios = [_landmark_area_ratio(face) for face in faces if face]
        return {
            "face_present": bool(faces),
            "face_count": len(faces),
            "max_face_area_ratio": round(max(area_ratios, default=0.0), 6),
            "landmark_counts": [len(face) for face in faces],
            "model_name": "mediapipe-face-landmarker",
            "model_version": Path(self.model_asset_path).name,
            "runtime": "mediapipe",
            "device": "cpu",
        }


class _MediaPipeRuntime:
    def __init__(
        self,
        *,
        model_asset_path: str,
        num_faces: int,
        min_detection_confidence: float,
    ):
        path = Path(model_asset_path)
        if not path.is_file():
            raise RuntimeError(f"MediaPipe face model asset does not exist: {path}")
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise RuntimeError(
                "MediaPipe face signals require the face-models optional dependencies"
            ) from error
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=num_faces,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_detection_confidence,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self.mp = mp

    def detect(self, image: Image.Image) -> list[list[tuple[float, float]]]:
        import numpy as np

        mp_image = self.mp.Image(
            image_format=self.mp.ImageFormat.SRGB,
            data=np.asarray(image, dtype=np.uint8),
        )
        result = self.landmarker.detect(mp_image)
        return [
            [(float(landmark.x), float(landmark.y)) for landmark in face]
            for face in result.face_landmarks
        ]


def _landmark_area_ratio(landmarks: list[tuple[float, float]]) -> float:
    xs = [point[0] for point in landmarks]
    ys = [point[1] for point in landmarks]
    width = max(0.0, min(1.0, max(xs)) - max(0.0, min(xs)))
    height = max(0.0, min(1.0, max(ys)) - max(0.0, min(ys)))
    return width * height
