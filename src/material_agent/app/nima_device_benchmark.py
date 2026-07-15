from __future__ import annotations

import asyncio
import json
import shutil
import statistics
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..adapters.models.openvino_nima_aesthetic import OpenVinoNimaAestheticAdapter
from ..domain.scoring_engine import decode_raw
from ..io.scanner import scan_arw_files


def run_nima_device_benchmark(
    input_dir: str | Path,
    model_path: str | Path,
    output_dir: str | Path,
    *,
    devices: list[str],
    batch_sizes: list[int],
    max_files: int = 128,
    warm_repetitions: int = 5,
) -> dict[str, Any]:
    if not devices:
        raise ValueError("at least one device is required")
    if not batch_sizes or any(size not in {1, 4, 8, 16} for size in batch_sizes):
        raise ValueError("batch sizes must be selected from 1, 4, 8, 16")
    if not 1 <= max_files <= 4096:
        raise ValueError("max_files must be between 1 and 4096")
    if not 1 <= warm_repetitions <= 100:
        raise ValueError("warm_repetitions must be between 1 and 100")
    source = Path(input_dir).expanduser().resolve()
    model = Path(model_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"input directory does not exist: {source}")
    if not model.is_file():
        raise ValueError(f"NIMA model does not exist: {model}")
    files = scan_arw_files(str(source), ["ARW", "CR3", "NEF", "RAF", "DNG", "ORF", "RW2"])[
        :max_files
    ]
    if not files:
        raise ValueError(f"no supported RAW files found: {source}")
    output.mkdir(parents=True, exist_ok=True)

    decode_started = time.perf_counter()
    images = [
        decode_raw(
            path,
            {
                "prefer_embedded": True,
                "fallback_decode": "half_size",
                "max_size": 1024,
                "focus_max_size": 2048,
                "jpeg_quality": 85,
            },
        ).jpeg_bytes
        for path in files
    ]
    decode_seconds = time.perf_counter() - decode_started

    profiles = []
    for device in devices:
        for batch_size in batch_sizes:
            profiles.append(
                _run_profile(
                    images,
                    model,
                    output / "cache" / _safe_name(device) / str(batch_size),
                    device=device,
                    batch_size=batch_size,
                    warm_repetitions=warm_repetitions,
                )
            )
    valid = [profile for profile in profiles if not profile.get("error")]
    selected = min(valid, key=lambda row: row["warm_p50_seconds"]) if valid else None
    report = {
        "schema_version": "material-agent.nima-device-benchmark.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "input": {
            "directory": str(source),
            "files": len(images),
            "raw_decode_seconds": round(decode_seconds, 6),
        },
        "model_path": str(model),
        "warm_repetitions": warm_repetitions,
        "profiles": profiles,
        "selected": (
            {
                "device": selected["device"],
                "batch_size": selected["batch_size"],
                "warm_p50_seconds": selected["warm_p50_seconds"],
                "images_per_second": selected["warm_images_per_second"],
                "execution_devices": selected["execution_devices"],
            }
            if selected
            else None
        ),
    }
    (output / "nima-device-benchmark.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "nima-device-benchmark.md").write_text(
        _render_markdown(report), encoding="utf-8"
    )
    return report


def _run_profile(
    images: list[bytes],
    model_path: Path,
    cache_dir: Path,
    *,
    device: str,
    batch_size: int,
    warm_repetitions: int,
) -> dict[str, Any]:
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    adapter = OpenVinoNimaAestheticAdapter(
        {
            "model_path": str(model_path),
            "device": device,
            "fallback_device": "",
            "compiled_cache_dir": str(cache_dir),
            "performance_hint": "THROUGHPUT",
            "batch_size": batch_size,
            "max_in_flight": 8,
            "infer_requests": "auto",
        }
    )
    try:
        cold, cold_utilization = _timed_score(adapter, images)
        warm = []
        warm_utilization = []
        last_results = None
        for _ in range(warm_repetitions):
            duration, utilization, last_results = _timed_score(adapter, images, return_results=True)
            warm.append(duration)
            warm_utilization.append(utilization)
        result = last_results[0]
        return {
            "device": device,
            "batch_size": batch_size,
            "files": len(images),
            "cold_seconds": round(cold, 6),
            "cold_utilization": cold_utilization,
            "warm_seconds": [round(value, 6) for value in warm],
            "warm_p50_seconds": round(statistics.median(warm), 6),
            "warm_images_per_second": round(len(images) / statistics.median(warm), 4),
            "warm_utilization": _merge_utilization(warm_utilization),
            "requested_device": result.get("requested_device"),
            "compiled_device": result.get("compiled_device"),
            "execution_devices": result.get("execution_devices", []),
            "fallback_used": result.get("fallback_used"),
            "infer_requests": result.get("infer_requests"),
            "optimal_infer_requests": result.get("optimal_infer_requests"),
            "model_digest": result.get("model_digest"),
            "openvino_version": result.get("openvino_version"),
            "inference_seconds_last": (result.get("timing") or {}).get("inference_seconds"),
        }
    except Exception as error:
        return {
            "device": device,
            "batch_size": batch_size,
            "files": len(images),
            "error": f"{type(error).__name__}: {error}",
        }


def _timed_score(adapter, images, *, return_results: bool = False):
    sampler = _UtilizationSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        results = asyncio.run(adapter.score_images(images))
    finally:
        duration = time.perf_counter() - started
        utilization = sampler.stop()
    if return_results:
        return duration, utilization, results
    return duration, utilization


class _UtilizationSampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._samples: list[dict[str, float | None]] = []
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        cpu = [row["process_cpu_percent"] for row in self._samples]
        gpu = [row["gpu_busy_percent"] for row in self._samples if row["gpu_busy_percent"] is not None]
        rss = [row["rss_mib"] for row in self._samples]
        return {
            "samples": len(self._samples),
            "process_cpu_percent_mean": round(statistics.mean(cpu), 3) if cpu else None,
            "process_cpu_percent_peak": round(max(cpu), 3) if cpu else None,
            "gpu_busy_percent_mean": round(statistics.mean(gpu), 3) if gpu else None,
            "gpu_busy_percent_peak": round(max(gpu), 3) if gpu else None,
            "gpu_busy_source": str(_gpu_busy_path()) if _gpu_busy_path() else None,
            "rss_mib_peak": round(max(rss), 3) if rss else None,
        }

    def _run(self) -> None:
        previous_wall = time.monotonic()
        previous_cpu = time.process_time()
        while not self._stop.wait(0.05):
            wall = time.monotonic()
            cpu = time.process_time()
            elapsed = wall - previous_wall
            process_percent = ((cpu - previous_cpu) / elapsed * 100.0) if elapsed else 0.0
            self._samples.append(
                {
                    "process_cpu_percent": process_percent,
                    "gpu_busy_percent": _read_gpu_busy(),
                    "rss_mib": _rss_mib(),
                }
            )
            previous_wall = wall
            previous_cpu = cpu


def _gpu_busy_path() -> Path | None:
    candidates = sorted(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"))
    return candidates[0] if candidates else None


def _read_gpu_busy() -> float | None:
    path = _gpu_busy_path()
    if path is None:
        return None
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _rss_mib() -> float:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def _merge_utilization(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "process_cpu_percent_mean",
        "process_cpu_percent_peak",
        "gpu_busy_percent_mean",
        "gpu_busy_percent_peak",
        "rss_mib_peak",
    )
    merged = {}
    for key in keys:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        merged[key] = round(statistics.mean(values), 3) if values else None
    merged["samples"] = sum(int(row.get("samples", 0)) for row in rows)
    merged["gpu_busy_source"] = next(
        (row.get("gpu_busy_source") for row in rows if row.get("gpu_busy_source")), None
    )
    return merged


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NIMA OpenVINO Device Benchmark",
        "",
        f"RAW files: {report['input']['files']}",
        "",
        "| Device | Batch | Cold s | Warm p50 s | Images/s | Execution | CPU mean % | GPU mean % |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in report["profiles"]:
        if row.get("error"):
            lines.append(f"| {row['device']} | {row['batch_size']} | error | | | {row['error']} | | |")
            continue
        util = row.get("warm_utilization", {})
        lines.append(
            "| {device} | {batch} | {cold:.3f} | {warm:.3f} | {speed:.3f} | {execution} | {cpu} | {gpu} |".format(
                device=row["device"],
                batch=row["batch_size"],
                cold=row.get("cold_seconds", 0.0),
                warm=row["warm_p50_seconds"],
                speed=row["warm_images_per_second"],
                execution=",".join(row["execution_devices"]),
                cpu=util.get("process_cpu_percent_mean"),
                gpu=util.get("gpu_busy_percent_mean"),
            )
        )
    lines.extend(["", "Selected: `" + json.dumps(report.get("selected")) + "`", ""])
    return "\n".join(lines)
