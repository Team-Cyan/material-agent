import asyncio
import base64
import json
import os
import subprocess
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from ...utils.json_extract import extract_last_json_object


class MusiqFastScreeningAdapter:
    def __init__(self, config: dict):
        self.metric_name = config.get("metric", "musiq")
        self.device_name = config.get("device", "cpu")
        self.score_divisor = float(config.get("score_divisor", 10.0))
        self.python_bin = config.get("python_bin", "~/.material-agent/musiq-venv/bin/python")
        self._metric = None
        self._runtime = None

    def _load_runtime(self):
        if self._runtime is None:
            import pyiqa
            import torch

            self._runtime = (torch, pyiqa)
        return self._runtime

    def _get_metric(self):
        if self._metric is None:
            torch, pyiqa = self._load_runtime()
            device = torch.device(self.device_name)
            self._metric = pyiqa.create_metric(self.metric_name, device=device)
        return self._metric

    def _jpeg_bytes_to_tensor(self, jpeg_bytes: bytes, torch_mod):
        image = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        array = np.asarray(image, dtype=np.float32) / 255.0
        tensor = torch_mod.from_numpy(array).permute(2, 0, 1).unsqueeze(0)
        return tensor.to(torch_mod.device(self.device_name))

    def _score_sync(self, jpeg_bytes: bytes) -> float:
        torch_mod, _ = self._load_runtime()
        tensor = self._jpeg_bytes_to_tensor(jpeg_bytes, torch_mod)
        metric = self._get_metric()
        with torch_mod.inference_mode():
            raw_score = metric(tensor)
        score_value = raw_score.item() if hasattr(raw_score, "item") else raw_score
        normalized = float(score_value) / self.score_divisor
        return max(0.0, min(10.0, normalized))

    def _resolve_helper_python(self) -> Path | None:
        if not self.python_bin:
            return None
        path = Path(self.python_bin).expanduser()
        if path.exists():
            return path
        return None

    def _score_via_helper(self, jpeg_bytes: bytes, python_bin: Path) -> float:
        payload = {
            "metric": self.metric_name,
            "device": self.device_name,
            "score_divisor": self.score_divisor,
            "jpeg_base64": base64.b64encode(jpeg_bytes).decode("ascii"),
        }
        env = dict(os.environ)
        src_path = str(Path(__file__).resolve().parents[3])
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
        )
        completed = subprocess.run(
            [str(python_bin), "-m", "material_agent.adapters.screening.musiq_worker"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            check=True,
        )
        data = extract_last_json_object(completed.stdout)
        return float(data["overall"])

    async def score_image_fast(self, jpeg_bytes: bytes) -> float:
        try:
            return await asyncio.to_thread(self._score_sync, jpeg_bytes)
        except (ModuleNotFoundError, ImportError):
            helper_python = self._resolve_helper_python()
            if helper_python is None:
                raise
            return await asyncio.to_thread(self._score_via_helper, jpeg_bytes, helper_python)
