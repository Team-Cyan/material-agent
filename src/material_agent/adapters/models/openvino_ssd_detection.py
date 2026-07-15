from __future__ import annotations

import asyncio
import hashlib
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .openvino_embedding import (
    _cache_identity,
    _portable_path,
    _read_execution_devices,
    _should_compile_fallback,
)


_COCO_LABELS = {
    1: "person",
    2: "bicycle",
    3: "car",
    4: "motorcycle",
    5: "airplane",
    6: "bus",
    7: "train",
    8: "truck",
    9: "boat",
    10: "traffic_light",
    11: "fire_hydrant",
    13: "stop_sign",
    14: "parking_meter",
    15: "bench",
    16: "bird",
    17: "cat",
    18: "dog",
    19: "horse",
    20: "sheep",
    21: "cow",
    22: "elephant",
    23: "bear",
    24: "zebra",
    25: "giraffe",
    27: "backpack",
    28: "umbrella",
    31: "handbag",
    32: "tie",
    33: "suitcase",
    34: "frisbee",
    35: "skis",
    36: "snowboard",
    37: "sports_ball",
    38: "kite",
    39: "baseball_bat",
    40: "baseball_glove",
    41: "skateboard",
    42: "surfboard",
    43: "tennis_racket",
    44: "bottle",
    46: "wine_glass",
    47: "cup",
    48: "fork",
    49: "knife",
    50: "spoon",
    51: "bowl",
    52: "banana",
    53: "apple",
    54: "sandwich",
    55: "orange",
    56: "broccoli",
    57: "carrot",
    58: "hot_dog",
    59: "pizza",
    60: "donut",
    61: "cake",
    62: "chair",
    63: "couch",
    64: "potted_plant",
    65: "bed",
    67: "dining_table",
    70: "toilet",
    72: "tv",
    73: "laptop",
    74: "mouse",
    75: "remote",
    76: "keyboard",
    77: "cell_phone",
    78: "microwave",
    79: "oven",
    80: "toaster",
    81: "sink",
    82: "refrigerator",
    84: "book",
    85: "clock",
    86: "vase",
    87: "scissors",
    88: "teddy_bear",
    89: "hair_drier",
    90: "toothbrush",
}
_ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
_SPORTS = {
    "frisbee",
    "skis",
    "snowboard",
    "sports_ball",
    "kite",
    "baseball_bat",
    "baseball_glove",
    "skateboard",
    "surfboard",
    "tennis_racket",
}
_DETAIL = {
    "bottle",
    "wine_glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot_dog",
    "pizza",
    "donut",
    "cake",
}


class OpenVinoSsdObjectDetectorAdapter:
    """Small COCO SSD detector plus optional YuNet face/eye localization."""

    def __init__(self, config: dict[str, Any] | None = None, *, runtime=None):
        self.config = config or {}
        self.model_path = str(Path(str(self.config.get("model_path", ""))).expanduser())
        self.face_model_path = str(Path(str(self.config.get("face_model_path", ""))).expanduser())
        self.device = str(self.config.get("device", "CPU"))
        self.fallback_device = str(self.config.get("fallback_device", "CPU"))
        self.compiled_cache_dir = str(
            Path(
                str(self.config.get("compiled_cache_dir", "~/.material-agent/openvino-cache"))
            ).expanduser()
        )
        self.input_size = max(224, int(self.config.get("input_size", 320)))
        self.score_threshold = float(self.config.get("score_threshold", 0.30))
        self.max_results = max(1, int(self.config.get("max_results", 10)))
        self.face_score_threshold = float(self.config.get("face_score_threshold", 0.60))
        self._runtime = runtime
        self._face_detector = None
        self._runtime_lock = threading.Lock()
        self._face_lock = threading.Lock()
        self.model_digest = _file_digest(Path(self.model_path))
        self.face_model_digest = _file_digest(Path(self.face_model_path))

    async def detect_objects(self, jpeg_bytes: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._detect_sync, jpeg_bytes)

    def _detect_sync(self, jpeg_bytes: bytes) -> dict[str, Any]:
        decode_started = time.perf_counter()
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        rgb = np.asarray(image)
        decode_seconds = time.perf_counter() - decode_started
        runtime = self._runtime
        if runtime is None:
            with self._runtime_lock:
                runtime = self._runtime
                if runtime is None:
                    if not self.model_path:
                        raise RuntimeError(
                            "OpenVINO SSD detection requires local.detection.model_path"
                        )
                    runtime = _OpenVinoSsdRuntime(
                        model_path=self.model_path,
                        device=self.device,
                        fallback_device=self.fallback_device,
                        compiled_cache_dir=self.compiled_cache_dir,
                        input_size=self.input_size,
                    )
                    self._runtime = runtime
        detections, timing = runtime.detect(rgb)
        objects = []
        for detection in detections:
            if detection["confidence"] < self.score_threshold:
                continue
            class_id = int(detection["class_id"])
            objects.append(
                {
                    **detection,
                    "label": _COCO_LABELS.get(class_id, f"coco_{class_id}"),
                }
            )
            if len(objects) >= self.max_results:
                break
        faces, face_timing = self._detect_faces(rgb)
        primary_index = _select_primary_subject(objects)
        scene = _scene_from_detection(objects, primary_index, faces)
        requested_device = str(getattr(runtime, "requested_device", self.device))
        compiled_device = str(getattr(runtime, "compiled_device", requested_device))
        fallback_used = bool(getattr(runtime, "fallback_used", False))
        return {
            "inference_run_id": uuid.uuid4().hex,
            "model_name": str(self.config.get("model_name", "ssd-mobilenet-v1-12")),
            "model_version": str(self.config.get("model_version", "onnxmodelzoo-opset12")),
            "runtime": "openvino",
            "device": self.device,
            "requested_device": requested_device,
            "compiled_device": compiled_device,
            "fallback_device": self.fallback_device,
            "fallback_used": fallback_used,
            "fallback_reason": getattr(runtime, "fallback_reason", None),
            "execution_devices": list(getattr(runtime, "execution_devices", [])),
            "model_digest": self.model_digest,
            "face_model_name": "opencv-yunet-int8" if self.face_model_path else None,
            "face_model_digest": self.face_model_digest if self.face_model_path else None,
            "compiled_cache_dir": _portable_path(self.compiled_cache_dir),
            "cache_identity": _cache_identity(
                self.model_digest,
                requested_device,
                getattr(runtime, "openvino_version", "unknown"),
                fallback_device=self.fallback_device,
                compiled_device=compiled_device,
            ),
            "input_size": self.input_size,
            "score_threshold": self.score_threshold,
            "objects": objects,
            "faces": faces,
            "primary_subject_index": primary_index,
            "primary_subject": objects[primary_index] if primary_index is not None else None,
            "scene": scene,
            "timing": {
                "image_decode_seconds": round(decode_seconds, 6),
                **timing,
                **face_timing,
            },
        }

    def _detect_faces(self, rgb: np.ndarray) -> tuple[list[dict], dict]:
        if not self.face_model_path or not Path(self.face_model_path).is_file():
            return [], {}
        started = time.perf_counter()
        height, width = rgb.shape[:2]
        scale = min(640 / max(height, width), 1.0)
        resized = cv2.resize(
            cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        resized_height, resized_width = resized.shape[:2]
        with self._face_lock:
            if self._face_detector is None:
                self._face_detector = cv2.FaceDetectorYN.create(
                    self.face_model_path,
                    "",
                    (resized_width, resized_height),
                    self.face_score_threshold,
                    0.3,
                    100,
                )
            else:
                self._face_detector.setInputSize((resized_width, resized_height))
            _, rows = self._face_detector.detect(resized)
        faces = []
        for row in rows if rows is not None else []:
            x, y, box_width, box_height = [float(value) for value in row[:4]]
            landmarks = {
                name: [
                    round(float(row[index]) / resized_width, 6),
                    round(float(row[index + 1]) / resized_height, 6),
                ]
                for name, index in (
                    ("right_eye", 4),
                    ("left_eye", 6),
                    ("nose", 8),
                    ("right_mouth", 10),
                    ("left_mouth", 12),
                )
            }
            faces.append(
                {
                    "confidence": round(float(row[14]), 6),
                    "bbox": _clamp_bbox(
                        [
                            x / resized_width,
                            y / resized_height,
                            (x + box_width) / resized_width,
                            (y + box_height) / resized_height,
                        ]
                    ),
                    "landmarks": landmarks,
                }
            )
        return faces, {"face_detection_seconds": round(time.perf_counter() - started, 6)}


class _OpenVinoSsdRuntime:
    def __init__(
        self,
        *,
        model_path: str,
        device: str,
        fallback_device: str,
        compiled_cache_dir: str,
        input_size: int,
    ):
        try:
            import openvino as ov
        except ImportError as error:
            raise RuntimeError(
                "OpenVINO SSD detection requires intel-openvino dependencies"
            ) from error
        model_file = Path(model_path)
        if not model_file.is_file():
            raise RuntimeError(f"OpenVINO SSD model does not exist: {model_file}")
        cache_dir = Path(compiled_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.ov = ov
        self.core = ov.Core()
        self.openvino_version = str(getattr(ov, "__version__", "unknown"))
        self.requested_device = device
        self.compiled_device = device
        self.fallback_device = fallback_device
        self.fallback_used = False
        self.fallback_reason = None
        model = self.core.read_model(str(model_file))
        model.reshape({model.input(0).get_any_name(): [1, input_size, input_size, 3]})
        config = {"CACHE_DIR": str(cache_dir), "PERFORMANCE_HINT": "LATENCY"}
        compile_started = time.perf_counter()
        try:
            self.compiled = self.core.compile_model(model, device, config)
        except RuntimeError as error:
            if not _should_compile_fallback(
                requested_device=device,
                fallback_device=fallback_device,
                available_devices=[str(value) for value in self.core.available_devices],
                error=error,
            ):
                raise
            self.fallback_used = True
            self.fallback_reason = f"{type(error).__name__}: {error}"
            self.compiled_device = fallback_device
            self.compiled = self.core.compile_model(model, fallback_device, config)
        self.compile_seconds = time.perf_counter() - compile_started
        self.execution_devices, self.execution_device_readback_error = _read_execution_devices(
            self.compiled
        )

    def detect(self, rgb: np.ndarray) -> tuple[list[dict], dict]:
        preprocess_started = time.perf_counter()
        input_size = int(self.compiled.input(0).shape[1])
        resized = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_AREA)
        tensor = np.expand_dims(resized.astype(np.uint8, copy=False), axis=0)
        preprocess_seconds = time.perf_counter() - preprocess_started
        inference_started = time.perf_counter()
        output = self.compiled([tensor])
        inference_seconds = time.perf_counter() - inference_started
        arrays = {port.get_any_name(): np.asarray(output[port]) for port in self.compiled.outputs}
        count = int(arrays["num_detections"].reshape(-1)[0])
        boxes = arrays["detection_boxes"].reshape(-1, 4)
        classes = arrays["detection_classes"].reshape(-1)
        scores = arrays["detection_scores"].reshape(-1)
        detections = [
            {
                "class_id": int(classes[index]),
                "confidence": round(float(scores[index]), 6),
                "bbox": _clamp_bbox(
                    [boxes[index][1], boxes[index][0], boxes[index][3], boxes[index][2]]
                ),
            }
            for index in range(min(count, len(scores)))
        ]
        return detections, {
            "compile_seconds": round(self.compile_seconds, 6),
            "preprocess_seconds": round(preprocess_seconds, 6),
            "inference_seconds": round(inference_seconds, 6),
        }


def _select_primary_subject(objects: list[dict]) -> int | None:
    if not objects:
        return None
    ranked = []
    for index, item in enumerate(objects):
        x1, y1, x2, y2 = item["bbox"]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
        center_score = max(
            0.0, 1.0 - ((center_x - 0.5) ** 2 + (center_y - 0.5) ** 2) ** 0.5 / 0.707
        )
        subject_bonus = 0.08 if item["label"] == "person" or item["label"] in _ANIMALS else 0.0
        score = (
            float(item["confidence"]) * 0.45
            + min(1.0, area / 0.35) * 0.35
            + center_score * 0.20
            + subject_bonus
        )
        ranked.append((score, index))
    return max(ranked)[1]


def _scene_from_detection(objects: list[dict], primary_index: int | None, faces: list[dict]) -> str:
    if faces:
        return "people"
    if primary_index is None:
        return "other"
    label = objects[primary_index]["label"]
    if label == "person":
        return "people"
    if label in _ANIMALS:
        return "animals"
    if label in _SPORTS:
        return "sports"
    if label in _DETAIL:
        return "detail"
    return "other"


def _clamp_bbox(values) -> list[float]:
    x1, y1, x2, y2 = [max(0.0, min(1.0, float(value))) for value in values]
    return [
        round(min(x1, x2), 6),
        round(min(y1, y2), 6),
        round(max(x1, x2), 6),
        round(max(y1, y2), 6),
    ]


def _file_digest(path: Path) -> str:
    if not path.is_file():
        return hashlib.sha256(str(path).encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
