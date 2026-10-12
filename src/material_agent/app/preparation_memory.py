"""Best-effort sampled preparation diagnostics; never retain prepared payloads."""

import json
import logging
import os
import sys


_log = logging.getLogger("material_agent")


def _process_memory() -> dict:
    result = {
        "current_rss_bytes": None,
        "process_highwater_rss_bytes": None,
    }
    if sys.platform == "linux":
        try:
            with open("/proc/self/statm", encoding="ascii") as statm:
                result["current_rss_bytes"] = int(statm.read().split()[1]) * os.sysconf(
                    "SC_PAGE_SIZE"
                )
        except Exception:
            pass
    if sys.platform in {"linux", "darwin"}:
        try:
            import resource

            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            result["process_highwater_rss_bytes"] = int(
                value * (1024 if sys.platform == "linux" else 1)
            )
        except Exception:
            pass
    return result


def _array_storage(array, np) -> tuple[int, int] | None:
    """Resolve only explicit ndarray base links, bounded to 64, without copying."""
    if type(array) is not np.ndarray or array.dtype.hasobject:
        return None
    owner = array
    for _ in range(64):
        if type(owner) is not np.ndarray:
            break
        if owner.dtype.hasobject:
            return None
        if owner.base is None:
            if owner.flags.owndata and (owner.flags.c_contiguous or owner.flags.f_contiguous):
                return id(owner), int(owner.nbytes)
            return None
        owner = owner.base
    else:
        return None
    if type(owner) is memoryview:
        owner = owner.obj
    if type(owner) in {bytes, bytearray}:
        return id(owner), len(owner)
    return None


def _payload_memory(prepared_items: list[object]) -> dict:
    prepared_ids: set[int] = set()
    frames: dict[int, object] = {}
    unknown = 0
    for item in prepared_items:
        if id(item) in prepared_ids:
            continue
        prepared_ids.add(id(item))
        if type(item) is not dict:
            unknown += 1
        elif item.get("frame") is not None:
            frame = item["frame"]
            frames[id(frame)] = frame
        elif item.get("cached") is not True:
            unknown += 1

    array_owners: dict[int, int] = {}
    jpeg_owners: dict[int, int] = {}
    array_field_nbytes = 0
    frame_count = 0
    if frames:
        # The concrete runtime owns these imports. Observation must never load
        # the image/model stack for an unfamiliar preparation collaborator.
        module = sys.modules.get("material_agent.domain.scoring_engine")
        frame_type = vars(module).get("RawFrame") if module is not None else None
        np = sys.modules.get("numpy")

        for frame in frames.values():
            if type(frame) is not frame_type or np is None:
                unknown += 1
                continue
            frame_count += 1
            jpeg = frame.jpeg_bytes
            if type(jpeg) is bytes:
                jpeg_owners[id(jpeg)] = len(jpeg)
            else:
                unknown += 1
            for array in (frame.gray, frame.pixels, frame.focus_gray):
                if array is None:
                    continue
                if type(array) is np.ndarray:
                    array_field_nbytes += int(array.nbytes)
                storage = _array_storage(array, np)
                if storage is None:
                    unknown += 1
                else:
                    owner_id, size = storage
                    array_owners[owner_id] = size
    owners = array_owners | jpeg_owners
    known_bytes = sum(owners.values())
    return {
        "prepared_live_count": len(prepared_ids),
        "frame_live_count": frame_count,
        "unknown_component_count": unknown,
        "array_field_nbytes": array_field_nbytes,
        "array_storage_bytes": sum(array_owners.values()),
        "jpeg_storage_bytes": sum(jpeg_owners.values()),
        "known_payload_bytes": known_bytes,
        "prepared_payload_bytes": known_bytes if not unknown else None,
    }


class PreparationMemoryDiagnostics:
    """Aggregate scalar samples only; all observation/log failures are optional."""

    def __init__(self):
        self.stages: dict[str, dict] = {}
        self.observation_errors = 0

    def __enter__(self):
        return self

    def observe(self, stage: str, *, current, prime_batch: list, pending: dict) -> None:
        try:
            items = list(prime_batch)
            if current is not None:
                items.append(current)
            ready = failed = unready = 0
            for future in pending.values():
                if not future.done():
                    unready += 1
                elif future.cancelled() or future.exception(timeout=0) is not None:
                    failed += 1
                else:
                    ready += 1
                    items.append(future.result(timeout=0))
            sample = _payload_memory(items)
            sample.update(_process_memory())
            sample.update(
                pending_ready_count=ready,
                pending_failed_count=failed,
                pending_unready_count=unready,
            )
            aggregate = self.stages.setdefault(
                stage, {"sample_count": 0, "sampled_max": {}, "unknown_samples": {}}
            )
            aggregate["sample_count"] += 1
            for key, value in sample.items():
                if value is None:
                    unknowns = aggregate["unknown_samples"]
                    unknowns[key] = unknowns.get(key, 0) + 1
                else:
                    maxima = aggregate["sampled_max"]
                    maxima[key] = max(maxima.get(key, value), value)
        except Exception:
            self.observation_errors += 1

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            report = {
                "schema": "material-agent.preparation-memory.v1",
                "scope": "job_owned_prepared_refs_at_stage_samples",
                "payload_unit": "bytes",
                "rss_unit": "bytes",
                "platform": sys.platform,
                "current_rss_source": "proc_statm" if sys.platform == "linux" else "unknown",
                "highwater_rss_source": (
                    "resource_ru_maxrss" if sys.platform in {"linux", "darwin"} else "unknown"
                ),
                "highwater_rss_scope": "process_lifetime",
                "status": (
                    "complete"
                    if exc_type is None
                    else "failed"
                    if issubclass(exc_type, Exception)
                    else "interrupted"
                ),
                "observation_errors": self.observation_errors,
                "stages": self.stages,
            }
            _log.info("Preparation memory diagnostics: %s", json.dumps(report, sort_keys=True))
        except Exception:
            pass
        return False
