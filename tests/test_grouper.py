from datetime import datetime
from unittest.mock import patch

import imagehash

from material_agent.core.grouper import Grouper


def _cfg(visual_enabled=False):
    return {
        "enabled": True,
        "time_gap_seconds": 30,
        "visual_similarity": {
            "enabled": visual_enabled,
            "hash_threshold": 10,
            "max_merge_gap_minutes": 10,
        },
        "group_guard": {"enabled": True, "min_score": 7.0},
    }


def test_time_grouping_splits_on_gap():
    files = ["/a.arw", "/b.arw", "/c.arw"]
    times = {
        "/a.arw": datetime(2024, 1, 1, 10, 0, 0),
        "/b.arw": datetime(2024, 1, 1, 10, 0, 20),  # 20s → same group
        "/c.arw": datetime(2024, 1, 1, 10, 1, 0),  # 40s → new group
    }
    with patch("material_agent.core.grouper.read_exif_datetimes", return_value=times):
        groups = Grouper(_cfg()).group(files)
    assert len(groups) == 2
    assert groups[0] == ["/a.arw", "/b.arw"]
    assert groups[1] == ["/c.arw"]


def test_no_exif_becomes_singleton():
    files = ["/no_exif.arw"]
    with patch("material_agent.core.grouper.read_exif_datetimes", return_value={"/no_exif.arw": None}):
        groups = Grouper(_cfg()).group(files)
    assert groups == [["/no_exif.arw"]]


def test_time_grouping_sorts_by_exif_before_splitting():
    """Files passed in reverse chronological order should still be grouped correctly."""
    # c then b then a — reversed from shoot order
    files = ["/c.arw", "/b.arw", "/a.arw"]
    times = {
        "/a.arw": datetime(2024, 1, 1, 10, 0, 0),
        "/b.arw": datetime(2024, 1, 1, 10, 0, 20),  # 20s gap → same group as a
        "/c.arw": datetime(2024, 1, 1, 10, 1, 0),   # 40s gap → new group
    }
    with patch("material_agent.core.grouper.read_exif_datetimes", return_value=times):
        groups = Grouper(_cfg()).group(files)
    assert len(groups) == 2
    # After chronological sort: a, b → group 1; c → group 2
    assert set(groups[0]) == {"/a.arw", "/b.arw"}
    assert groups[1] == ["/c.arw"]


def test_exiftool_sourcefile_matching():
    """read_exif_datetimes should match by SourceFile key, not array position."""
    import json
    from unittest.mock import MagicMock
    from material_agent.core.grouper import read_exif_datetimes

    # exiftool returns rows in a different order than the input files
    mock_output = json.dumps([
        {"SourceFile": "/b.arw", "DateTimeOriginal": "2024:01:01 10:00:20"},
        {"SourceFile": "/a.arw", "DateTimeOriginal": "2024:01:01 10:00:00"},
    ])
    mock_proc = MagicMock()
    mock_proc.stdout = mock_output

    with patch("material_agent.core.grouper.subprocess.run", return_value=mock_proc):
        result = read_exif_datetimes(["/a.arw", "/b.arw"])

    assert result["/a.arw"] == datetime(2024, 1, 1, 10, 0, 0)
    assert result["/b.arw"] == datetime(2024, 1, 1, 10, 0, 20)


def test_visual_merge_reuses_cached_hashes_between_runs():
    files = ["/a.arw", "/b.arw", "/c.arw", "/d.arw"]
    times = {
        "/a.arw": datetime(2024, 1, 1, 10, 0, 0),
        "/b.arw": datetime(2024, 1, 1, 10, 0, 10),
        "/c.arw": datetime(2024, 1, 1, 10, 0, 50),
        "/d.arw": datetime(2024, 1, 1, 10, 1, 0),
    }

    class _State:
        def __init__(self):
            self.cache = {}

        def get_visual_hash_cache(self, file_paths):
            return {file_path: self.cache[file_path] for file_path in file_paths if file_path in self.cache}

        def set_visual_hash_cache(self, entries):
            self.cache.update(entries)

    state = _State()
    hash_calls: list[str] = []

    def _fake_hash(file_path: str):
        hash_calls.append(file_path)
        if file_path in {"/b.arw", "/c.arw"}:
            return imagehash.hex_to_hash("0" * 16)
        return imagehash.hex_to_hash("f" * 16)

    with patch("material_agent.core.grouper.read_exif_datetimes", return_value=times):
        with patch.object(Grouper, "_hash_file", side_effect=_fake_hash):
            groups = Grouper(_cfg(visual_enabled=True)).group(files, state=state)

    assert groups == [["/a.arw", "/b.arw", "/c.arw", "/d.arw"]]
    assert hash_calls == ["/b.arw", "/c.arw"]
    assert state.cache == {
        "/b.arw": "0000000000000000",
        "/c.arw": "0000000000000000",
    }

    hash_calls.clear()
    with patch("material_agent.core.grouper.read_exif_datetimes", return_value=times):
        with patch.object(Grouper, "_hash_file", side_effect=AssertionError("hash should be cached")):
            groups = Grouper(_cfg(visual_enabled=True)).group(files, state=state)

    assert groups == [["/a.arw", "/b.arw", "/c.arw", "/d.arw"]]
    assert hash_calls == []
