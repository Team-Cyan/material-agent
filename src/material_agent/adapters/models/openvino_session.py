"""Shared native OpenVINO compilation and ordered bounded execution."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import threading
import time
import uuid

from .inference_contract import REVISION, identity


@contextmanager
def compiled_cache(root, key, max_entries=16, max_bytes=2 * 1024**3):
    """Only manage our own namespace; serialize compilation/eviction across processes."""
    import fcntl

    namespace = Path(root) / REVISION
    if namespace.is_symlink():
        raise RuntimeError("compiled cache namespace must not be a symlink")
    namespace.mkdir(parents=True, exist_ok=True)
    with (namespace / ".lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entry = namespace / key
        if entry.is_symlink():
            raise RuntimeError("compiled cache entry must not be a symlink")
        entry.mkdir(exist_ok=True)
        try:
            yield entry
        finally:
            entry.touch()
            entries = [
                p
                for p in namespace.iterdir()
                if p.is_dir()
                and not p.is_symlink()
                and len(p.name) == 64
                and all(c in "0123456789abcdef" for c in p.name)
            ]
            sizes = {
                p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())
                for p in entries
            }
            for victim in sorted(entries, key=lambda p: p.stat().st_mtime):
                if len(sizes) <= max_entries and sum(sizes.values()) <= max_bytes:
                    break
                shutil.rmtree(victim)
                sizes.pop(victim)


class OpenVinoSession:
    def __init__(
        self,
        *,
        model_path,
        declaration,
        device,
        fallback_device,
        compiled_cache_dir,
        performance_hint="THROUGHPUT",
        batch_size=1,
        max_in_flight=8,
        infer_requests="auto",
        allow_batch_fallback=False,
        auto_batch=False,
        reshape=True,
    ):
        import numpy as np
        import openvino as ov

        self.np, self.ov = np, ov
        self.core = ov.Core()
        self.declaration = declaration
        if declaration.record()["assets"].get("state") != "available":
            raise RuntimeError("model assets unavailable or unsupported")
        if not 1 <= int(batch_size) <= 64 or not 1 <= int(max_in_flight) <= 64:
            raise RuntimeError("shared OpenVINO batch/request bounds must be 1..64")
        self.model_path = str(model_path)
        self.openvino_version = str(getattr(ov, "__version__", "unknown"))
        self.requested_device = device
        self.compiled_device = device
        self.compile_target = device
        self.fallback_device = fallback_device
        self.fallback_used = False
        self.fallback_reason = None
        self.performance_hint = performance_hint
        self.batch_size_requested = max(1, int(batch_size))
        self.batch_size = self.batch_size_requested
        self.input_batch_size = self.batch_size
        self.batch_strategy = "single" if self.batch_size == 1 else "reshape"
        self.batch_reshape_error = None
        self.batch_fallback_used = False
        self.batch_fallback_reason = None
        self.auto_batch = auto_batch
        self.reshape = reshape
        self.cache_root = compiled_cache_dir
        self._run_lock = threading.RLock()
        self.compile_event_id = uuid.uuid4().hex
        self.last_run_timing = {}
        started = time.perf_counter()
        try:
            self.compiled = self._compile(device, self.batch_size)
        except RuntimeError as error:
            if _should_compile_fallback(
                requested_device=device,
                fallback_device=fallback_device,
                available_devices=list(self.core.available_devices),
                error=error,
            ):
                self.fallback_used = True
                self.fallback_reason = "requested_device_unavailable"
                self.compiled_device = fallback_device
                try:
                    self.compiled = self._compile(fallback_device, self.batch_size)
                except RuntimeError:
                    if self.batch_size == 1 or not allow_batch_fallback:
                        raise
                    self._batch_fallback()
                    self.compiled = self._compile(fallback_device, 1)
            elif self.batch_size > 1 and allow_batch_fallback:
                self._batch_fallback()
                self.compiled = self._compile(device, 1)
            else:
                raise
        self.compile_seconds = time.perf_counter() - started
        self.execution_devices, self.execution_device_readback_error = _read_execution_devices(
            self.compiled
        )
        self.optimal_infer_requests, self.optimal_infer_requests_error = (
            _read_optimal_infer_requests(self.compiled)
        )
        self.infer_requests = _resolve_infer_requests(
            infer_requests, optimal=self.optimal_infer_requests, maximum=max_in_flight
        )
        self.max_in_flight = max_in_flight
        self.requested_infer_requests = infer_requests

    def _batch_fallback(self):
        self.batch_fallback_used = True
        self.batch_fallback_reason = "batch_compile_failed"
        self.batch_size = 1

    def _compile(self, device, batch):
        model = self.core.read_model(self.model_path)
        self.batch_strategy = "single" if batch == 1 else "reshape"
        self.input_batch_size = batch
        try:
            if self.reshape or batch > 1:
                port = model.input(0)
                shape = list(port.get_partial_shape())
                spec = self.declaration.record()["preprocessing"]
                declared = spec.get("shape")
                if declared:
                    if len(shape) != len(declared):
                        raise RuntimeError("model input rank does not match declaration")
                    shape = list(declared)
                shape[0] = batch
                model.reshape({port.get_any_name(): shape})
            return self._compile_cached(model, device, batch)
        except RuntimeError as error:
            if batch <= 1 or not self.auto_batch:
                raise
            self.batch_reshape_error = type(error).__name__ + ": batch reshape unavailable"
            self.batch_strategy = "auto_batch"
            self.input_batch_size = 1
            target = f"BATCH:{_auto_batch_target(device)}({batch})"
            return self._compile_cached(self.core.read_model(self.model_path), target, batch)

    def _compile_cached(self, model, target, batch):
        self.compile_target = target
        self.compiled_cache_identity = identity(
            {
                "model": self.declaration.key,
                "runtime_version": self.openvino_version,
                "target": target,
                "batch": batch,
                "strategy": self.batch_strategy,
                "performance_hint": self.performance_hint,
            }
        )
        with compiled_cache(self.cache_root, self.compiled_cache_identity) as directory:
            compiled = self.core.compile_model(
                model,
                target,
                {"CACHE_DIR": str(directory), "PERFORMANCE_HINT": self.performance_hint},
            )
            try:
                loaded = compiled.get_property("LOADED_FROM_CACHE")
                self.compiled_cache_status = (
                    ("hit" if loaded else "miss") if isinstance(loaded, bool) else "unknown"
                )
            except Exception:
                self.compiled_cache_status = "unknown"
        if not directory.exists():
            self.compiled_cache_status = "bypass_capacity"
        return compiled

    def run(self, images, preprocess, normalize):
        """Normalize one batch at a time, preserving submitted source order."""
        with self._run_lock:
            return self._run(images, preprocess, normalize)

    def _run(self, images, preprocess, normalize):
        timings = dict.fromkeys(
            ("preprocess_seconds", "inference_seconds", "postprocess_seconds"), 0.0
        )
        results = []
        batch_count = 0
        # At most 32 prepared images, except a declared batch itself may be larger.
        window = max(self.input_batch_size, (32 // self.input_batch_size) * self.input_batch_size)
        for offset in range(0, len(images), window):
            started = time.perf_counter()
            tensors = [preprocess(image) for image in images[offset : offset + window]]
            spec = self.declaration.record()["preprocessing"]
            for tensor in tensors:
                if str(tensor.dtype) != spec["dtype"] or tensor.ndim != 4 or tensor.shape[0] != 1:
                    raise RuntimeError("model input dtype/rank does not match declaration")
                if not self.np.isfinite(tensor).all():
                    raise RuntimeError("nonfinite model input")
            batches = []
            for start in range(0, len(tensors), self.input_batch_size):
                members = tensors[start : start + self.input_batch_size]
                valid = len(members)
                members += [members[-1]] * (self.input_batch_size - valid)
                batches.append((start, valid, self.np.concatenate(members, axis=0)))
            timings["preprocess_seconds"] += time.perf_counter() - started
            outputs = {}
            queue = self.ov.AsyncInferQueue(self.compiled, self.infer_requests)

            def complete(request, userdata):
                outputs[userdata] = [
                    self.np.array(t.data, copy=True) for t in request.output_tensors
                ]

            queue.set_callback(complete)
            started = time.perf_counter()
            try:
                for start, valid, tensor in batches:
                    queue.start_async(
                        {self.compiled.input(0).get_any_name(): tensor}, userdata=start
                    )
            finally:
                queue.wait_all()
            timings["inference_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            for start, valid, _ in batches:
                arrays = outputs.get(start)
                if not arrays or any(not self.np.isfinite(a).all() for a in arrays):
                    raise RuntimeError("missing or nonfinite model output")
                rows = normalize(arrays)
                if len(rows) != self.input_batch_size:
                    raise RuntimeError("model output batch count mismatch")
                results.extend(rows[:valid])
            timings["postprocess_seconds"] += time.perf_counter() - started
            batch_count += len(batches)
        self.execution_devices, self.execution_device_readback_error = _read_execution_devices(
            self.compiled
        )
        self.last_run_timing = {k: round(v, 6) for k, v in timings.items()}
        self.last_run_timing.update(
            compile_seconds=round(self.compile_seconds, 6),
            batch_count=batch_count,
            image_count=len(images),
        )
        return results

    def execution_record(self):
        return {
            "schema": REVISION,
            "status": "fallback" if self.fallback_used else "success",
            "lifecycle": "shared_openvino",
            "model": self.declaration.record(),
            "model_identity": self.declaration.key,
            "runtime_version": self.openvino_version,
            "requested_device": self.requested_device,
            "compiled_device": self.compile_target,
            "execution_devices": list(self.execution_devices),
            "execution_device_readback": "unknown"
            if self.execution_device_readback_error
            else "actual",
            "fallback": {
                "kind": "application_compile"
                if self.fallback_used
                else (
                    "runtime_selection"
                    if self.requested_device.upper().startswith("AUTO")
                    else "none"
                ),
                "reason": self.fallback_reason,
            },
            "compiled_cache": {
                "identity": self.compiled_cache_identity,
                "status": self.compiled_cache_status,
            },
            "compile_event_id": self.compile_event_id,
            "batch": {
                "requested": self.batch_size_requested,
                "actual": self.batch_size,
                "strategy": self.batch_strategy,
                "partial": "repeat_last_discard_padding",
                "fallback": self.batch_fallback_used,
            },
            "requests": {
                "requested": self.requested_infer_requests,
                "actual": self.infer_requests,
                "maximum": self.max_in_flight,
            },
            "missing_evidence": ["execution_devices"]
            if self.execution_device_readback_error
            else [],
        }


def _should_compile_fallback(
    *,
    requested_device: str,
    fallback_device: str,
    available_devices: list[str],
    error: RuntimeError,
) -> bool:
    fallback = fallback_device.strip()
    if not fallback or fallback.upper() == requested_device.strip().upper():
        return False
    if _request_has_unavailable_device(requested_device, available_devices):
        return True
    message = str(error).lower()
    unavailable_markers = (
        "not registered in the openvino runtime",
        "no available devices",
        "no supported devices",
        "device is not available",
        "no opencl device",
    )
    return any(marker in message for marker in unavailable_markers)


def _request_has_unavailable_device(requested: str, available: list[str]) -> bool:
    request = requested.strip().upper()
    if not request or request in {"AUTO", "MULTI", "HETERO"}:
        return False
    candidates = (
        [candidate.strip() for candidate in request.split(":", 1)[1].split(",")]
        if ":" in request
        else [request]
    )
    visible = [str(device).strip().upper() for device in available]
    return any(
        candidate
        and not any(device == candidate or device.startswith(f"{candidate}.") for device in visible)
        for candidate in candidates
    )


def _read_execution_devices(compiled) -> tuple[list[str], str | None]:
    try:
        devices = [str(value) for value in compiled.get_property("EXECUTION_DEVICES")]
        if not devices:
            return ["unknown"], "EXECUTION_DEVICES returned no devices"
        return devices, None
    except Exception as error:
        return ["unknown"], f"{type(error).__name__}: {error}"


def _read_optimal_infer_requests(compiled) -> tuple[int | None, str | None]:
    try:
        value = int(compiled.get_property("OPTIMAL_NUMBER_OF_INFER_REQUESTS"))
    except (RuntimeError, TypeError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"
    if value < 1:
        return None, "OPTIMAL_NUMBER_OF_INFER_REQUESTS returned a value below 1"
    return value, None


def _resolve_infer_requests(
    requested: str | int,
    *,
    optimal: int | None,
    maximum: int,
) -> int:
    cap = max(1, int(maximum))
    if isinstance(requested, int) and not isinstance(requested, bool):
        return min(cap, max(1, requested))
    if str(requested).strip().lower() != "auto":
        raise RuntimeError("OpenVINO infer_requests must be 'auto' or a positive integer")
    return min(cap, optimal or 1)


def _auto_batch_target(device: str) -> str:
    requested = device.strip()
    upper = requested.upper()
    if upper.startswith(("AUTO:", "MULTI:")):
        candidates = requested.split(":", 1)[1].split(",")
        target = candidates[0].strip()
        if target:
            return target
    if ":" in requested:
        raise RuntimeError(
            f"OpenVINO automatic batching does not support composite device {device!r}"
        )
    return requested
