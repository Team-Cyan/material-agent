import io
import json
import logging
import subprocess
from datetime import datetime

import imagehash
import rawpy
from PIL import Image

_EXIFTOOL_BATCH_SIZE = 256
_log = logging.getLogger("material_agent")


def read_exif_datetimes(files: list[str], state=None, progress=None) -> dict[str, datetime | None]:
    if not files:
        return {}

    cached = state.get_exif_cache(files) if state else {}
    cached_files = set(cached.keys())
    missing = [f for f in files if f not in cached_files]
    result: dict[str, datetime | None] = {}

    for file_path, val in cached.items():
        try:
            result[file_path] = datetime.strptime(val, "%Y:%m:%d %H:%M:%S") if val else None
        except ValueError:
            result[file_path] = None

    if not missing:
        return result

    new_raw: dict[str, str | None] = {}
    if progress:
        progress.on_phase_start("reading EXIF", len(missing))
    for start in range(0, len(missing), _EXIFTOOL_BATCH_SIZE):
        batch = missing[start : start + _EXIFTOOL_BATCH_SIZE]
        try:
            batch_raw, batch_result = _read_exif_batch(batch)
        except Exception as error:
            _log.warning(
                "Bulk EXIF read failed for %d files; falling back per file: %s",
                len(batch),
                error,
            )
            for file_path in batch:
                read_ok, raw_val, val = _read_exif_single_result(file_path)
                if read_ok:
                    new_raw[file_path] = raw_val
                result[file_path] = val
                if progress:
                    progress.on_phase_advance()
        else:
            missing_rows = [file_path for file_path in batch if file_path not in batch_raw]
            if missing_rows:
                _log.warning(
                    "Bulk EXIF output omitted %d files; retrying those files individually",
                    len(missing_rows),
                )
                for file_path in missing_rows:
                    read_ok, raw_val, val = _read_exif_single_result(file_path)
                    if read_ok:
                        batch_raw[file_path] = raw_val
                    batch_result[file_path] = val
            new_raw.update(batch_raw)
            result.update(batch_result)
            if progress:
                progress.on_phase_advance(len(batch))

    if state and new_raw:
        state.set_exif_cache(new_raw)

    return result


def _read_exif_batch(files: list[str]) -> tuple[dict[str, str | None], dict[str, datetime | None]]:
    proc = subprocess.run(
        ["exiftool", "-DateTimeOriginal", "-s3", "-j", *files],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"exiftool exited with status {proc.returncode}")
    rows = json.loads(proc.stdout)
    if not isinstance(rows, list):
        raise ValueError("exiftool JSON output must be a list")

    row_by_path = {row.get("SourceFile", ""): row for row in rows if isinstance(row, dict)}
    raw: dict[str, str | None] = {}
    parsed: dict[str, datetime | None] = {}
    for file_path in files:
        row = row_by_path.get(file_path)
        if row is None:
            parsed[file_path] = None
            continue
        val = row.get("DateTimeOriginal", "") or ""
        raw[file_path] = val if val else None
        try:
            parsed[file_path] = datetime.strptime(val, "%Y:%m:%d %H:%M:%S") if val else None
        except ValueError:
            parsed[file_path] = None
    return raw, parsed


def _read_exif_single(file_path: str) -> datetime | None:
    return _read_exif_single_result(file_path)[2]


def _read_exif_single_result(file_path: str) -> tuple[bool, str | None, datetime | None]:
    try:
        result = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-s3", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, None, None
        val = result.stdout.strip()
        try:
            parsed = datetime.strptime(val, "%Y:%m:%d %H:%M:%S") if val else None
        except ValueError:
            parsed = None
        return True, val or None, parsed
    except Exception:
        return False, None, None


class Grouper:
    def __init__(self, config: dict, *, embedding_loader=None, embedding_model_key: str = ""):
        self.config = config
        self.embedding_loader = embedding_loader
        self.embedding_model_key = embedding_model_key

    def group(self, files: list[str], state=None, progress=None) -> list[list[str]]:
        if not files:
            return []
        times = read_exif_datetimes(files, state=state, progress=progress)
        return self._group_with_times(files, times, state=state, progress=progress)

    def _group_with_times(self, files, times, state=None, progress=None):
        gap = self.config["time_gap_seconds"]
        legacy = self.config.get("visual_similarity", {})
        threshold = self.config.get(
            "hash_threshold",
            legacy.get("hash_threshold", 10) if legacy.get("enabled", False) else 0,
        )
        ordered = sorted(files, key=lambda f: (times.get(f) is None, times.get(f)))
        cache = {}
        if threshold > 0 and state is not None and hasattr(state, "get_visual_hash_cache"):
            for path, value in state.get_visual_hash_cache(ordered).items():
                try:
                    cached_hash = imagehash.hex_to_hash(value)
                    if cached_hash.hash.size == 64:
                        cache[path] = cached_hash
                except ValueError, TypeError:
                    pass
        new_entries = {}

        def get_hash(path):
            if path not in cache:
                cache[path] = self._hash_file(path)
                if cache[path] is not None:
                    new_entries[path] = str(cache[path])
            return cache[path]

        groups = []
        previous = None
        if progress:
            progress.on_phase_start("time/hash grouping", len(ordered))
        for path in ordered:
            before, current = times.get(previous), times.get(path)
            matches = (
                previous is not None
                and before is not None
                and current is not None
                and (current - before).total_seconds() <= gap
            )
            if matches and threshold > 0:
                left, right = get_hash(previous), get_hash(path)
                matches = left is not None and right is not None and left - right <= threshold
            if matches:
                groups[-1].append(path)
            else:
                groups.append([path])
            previous = path
            if progress:
                progress.on_phase_advance()
        if new_entries and state is not None and hasattr(state, "set_visual_hash_cache"):
            state.set_visual_hash_cache(new_entries)
        return groups

    @staticmethod
    def _hash_file(file_path: str):
        try:
            try:
                with Image.open(file_path) as source:
                    img = source.convert("RGB")
            except OSError, ValueError:
                with rawpy.imread(file_path) as raw:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        with Image.open(io.BytesIO(thumb.data)) as source:
                            img = source.convert("RGB")
                    else:
                        img = Image.fromarray(thumb.data)
            img.thumbnail((256, 256))
            return imagehash.phash(img)
        except Exception:
            return None
