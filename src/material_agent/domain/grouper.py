import io
import json
import subprocess
from datetime import datetime

import imagehash
import rawpy
from PIL import Image


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
    try:
        if progress:
            progress.on_phase_start("reading EXIF", len(missing))
        proc = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-s3", "-j"] + missing,
            capture_output=True,
            text=True,
            timeout=300,
        )
        rows = json.loads(proc.stdout)
        row_by_path = {row.get("SourceFile", ""): row for row in rows}
        for file_path in missing:
            row = row_by_path.get(file_path, {})
            val = row.get("DateTimeOriginal", "") or ""
            new_raw[file_path] = val if val else None
            try:
                result[file_path] = datetime.strptime(val, "%Y:%m:%d %H:%M:%S") if val else None
            except ValueError:
                result[file_path] = None
        if progress:
            progress.on_phase_advance(len(missing))
    except Exception:
        if progress:
            progress.on_phase_start("reading EXIF", len(missing))
        for file_path in missing:
            val = _read_exif_single(file_path)
            new_raw[file_path] = val.strftime("%Y:%m:%d %H:%M:%S") if val else None
            result[file_path] = val
            if progress:
                progress.on_phase_advance()

    if state and new_raw:
        state.set_exif_cache(new_raw)

    return result


def _read_exif_single(file_path: str) -> datetime | None:
    try:
        result = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-s3", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        val = result.stdout.strip()
        return datetime.strptime(val, "%Y:%m:%d %H:%M:%S") if val else None
    except Exception:
        return None


class Grouper:
    def __init__(self, config: dict):
        self.config = config

    def group(self, files: list[str], state=None, progress=None) -> list[list[str]]:
        if not files:
            return []
        times = read_exif_datetimes(files, state=state, progress=progress)
        groups = self._time_split(files, times)
        if self.config["visual_similarity"]["enabled"]:
            groups = self._visual_merge(groups, times, state=state, progress=progress)
        return groups

    def _time_split(self, files: list[str], times: dict) -> list[list[str]]:
        gap = self.config["time_gap_seconds"]
        sorted_files = sorted(files, key=lambda f: (times.get(f) is None, times.get(f)))
        groups: list[list[str]] = [[sorted_files[0]]]
        for i in range(1, len(sorted_files)):
            t_prev = times[sorted_files[i - 1]]
            t_curr = times[sorted_files[i]]
            if t_prev is None or t_curr is None or (t_curr - t_prev).total_seconds() > gap:
                groups.append([sorted_files[i]])
            else:
                groups[-1].append(sorted_files[i])
        return groups

    def _visual_merge(self, groups: list[list[str]], times: dict, state=None, progress=None) -> list[list[str]]:
        cfg = self.config["visual_similarity"]
        threshold = cfg["hash_threshold"]
        max_gap_s = cfg["max_merge_gap_minutes"] * 60
        merged: list[list[str]] = []
        i = 0
        hash_cache = self._load_visual_hash_cache(groups, state=state)
        new_hash_entries: dict[str, str] = {}

        def _get_hash(file_path: str):
            if file_path in hash_cache:
                return hash_cache[file_path]
            image_hash = self._hash_file(file_path)
            hash_cache[file_path] = image_hash
            if image_hash is not None:
                new_hash_entries[file_path] = str(image_hash)
            return image_hash

        def _try_merge(idx: int) -> bool:
            if idx + 1 >= len(groups):
                return False
            tail, head = groups[idx][-1], groups[idx + 1][0]
            t1, t2 = times.get(tail), times.get(head)
            if not (t1 and t2 and (t2 - t1).total_seconds() <= max_gap_s):
                return False
            h1, h2 = _get_hash(tail), _get_hash(head)
            if h1 is None or h2 is None or (h1 - h2) > threshold:
                return False
            groups[idx + 1] = groups[idx] + groups[idx + 1]
            return True

        if progress:
            progress.on_phase_start("visual merge", len(groups))
            while i < len(groups):
                if _try_merge(i):
                    i += 1
                    progress.on_phase_advance()
                    continue
                merged.append(groups[i])
                progress.on_phase_advance()
                i += 1
        else:
            while i < len(groups):
                if _try_merge(i):
                    i += 1
                    continue
                merged.append(groups[i])
                i += 1
        if state and new_hash_entries and hasattr(state, "set_visual_hash_cache"):
            state.set_visual_hash_cache(new_hash_entries)
        return merged

    @staticmethod
    def _hash_file(file_path: str):
        try:
            with rawpy.imread(file_path) as raw:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                else:
                    img = Image.fromarray(thumb.data)
            img.thumbnail((256, 256))
            return imagehash.phash(img)
        except Exception:
            return None

    @staticmethod
    def _load_visual_hash_cache(groups: list[list[str]], state=None) -> dict[str, imagehash.ImageHash]:
        if state is None or len(groups) < 2 or not hasattr(state, "get_visual_hash_cache"):
            return {}

        boundary_files: list[str] = []
        for idx in range(len(groups) - 1):
            boundary_files.append(groups[idx][-1])
            boundary_files.append(groups[idx + 1][0])

        cached = state.get_visual_hash_cache(list(dict.fromkeys(boundary_files)))
        loaded: dict[str, imagehash.ImageHash] = {}
        for file_path, raw_hash in cached.items():
            try:
                loaded[file_path] = imagehash.hex_to_hash(raw_hash)
            except Exception:
                continue
        return loaded
