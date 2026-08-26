from datetime import datetime
from unittest.mock import patch

import imagehash
import pytest

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
        "embedding_similarity": {"enabled": False, "threshold": 0.85},
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
    with patch(
        "material_agent.core.grouper.read_exif_datetimes", return_value={"/no_exif.arw": None}
    ):
        groups = Grouper(_cfg()).group(files)
    assert groups == [["/no_exif.arw"]]


def test_time_grouping_sorts_by_exif_before_splitting():
    """Files passed in reverse chronological order should still be grouped correctly."""
    # c then b then a — reversed from shoot order
    files = ["/c.arw", "/b.arw", "/a.arw"]
    times = {
        "/a.arw": datetime(2024, 1, 1, 10, 0, 0),
        "/b.arw": datetime(2024, 1, 1, 10, 0, 20),  # 20s gap → same group as a
        "/c.arw": datetime(2024, 1, 1, 10, 1, 0),  # 40s gap → new group
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
    mock_output = json.dumps(
        [
            {"SourceFile": "/b.arw", "DateTimeOriginal": "2024:01:01 10:00:20"},
            {"SourceFile": "/a.arw", "DateTimeOriginal": "2024:01:01 10:00:00"},
        ]
    )
    mock_proc = MagicMock()
    mock_proc.stdout = mock_output
    mock_proc.stderr = ""
    mock_proc.returncode = 0

    with patch("material_agent.core.grouper.subprocess.run", return_value=mock_proc):
        result = read_exif_datetimes(["/a.arw", "/b.arw"])

    assert result["/a.arw"] == datetime(2024, 1, 1, 10, 0, 0)
    assert result["/b.arw"] == datetime(2024, 1, 1, 10, 0, 20)


def test_exiftool_reads_large_inputs_in_bounded_batches():
    import json
    from unittest.mock import MagicMock

    from material_agent.core.grouper import read_exif_datetimes

    files = [f"/library/{index:04d}.arw" for index in range(600)]
    batch_sizes: list[int] = []

    def _run(command, **_kwargs):
        batch = command[4:]
        batch_sizes.append(len(batch))
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = json.dumps(
            [
                {
                    "SourceFile": file_path,
                    "DateTimeOriginal": "2024:01:01 10:00:00",
                }
                for file_path in batch
            ]
        )
        return proc

    with patch("material_agent.core.grouper.subprocess.run", side_effect=_run):
        result = read_exif_datetimes(files)

    assert batch_sizes == [256, 256, 88]
    assert len(result) == len(files)


def test_transient_exiftool_failure_is_not_cached_as_missing():
    from material_agent.core.grouper import read_exif_datetimes

    class _State:
        def __init__(self):
            self.writes = []

        def get_exif_cache(self, _files):
            return {}

        def set_exif_cache(self, entries):
            self.writes.append(entries)

    state = _State()
    with (
        patch(
            "material_agent.domain.grouper._read_exif_batch",
            side_effect=RuntimeError("temporary failure"),
        ),
        patch(
            "material_agent.domain.grouper._read_exif_single_result",
            return_value=(False, None, None),
        ),
    ):
        result = read_exif_datetimes(["/library/a.arw"], state=state)

    assert result == {"/library/a.arw": None}
    assert state.writes == []


def test_missing_exiftool_json_row_is_not_cached_as_missing():
    import json
    from unittest.mock import MagicMock

    from material_agent.core.grouper import read_exif_datetimes

    class _State:
        def __init__(self):
            self.writes = []

        def get_exif_cache(self, _files):
            return {}

        def set_exif_cache(self, entries):
            self.writes.append(entries)

    proc = MagicMock(returncode=0, stderr="", stdout=json.dumps([]))
    state = _State()
    with (
        patch("material_agent.core.grouper.subprocess.run", return_value=proc),
        patch(
            "material_agent.domain.grouper._read_exif_single_result",
            return_value=(False, None, None),
        ) as single_read,
    ):
        result = read_exif_datetimes(["/library/a.arw"], state=state)

    assert result == {"/library/a.arw": None}
    assert state.writes == []
    single_read.assert_called_once_with("/library/a.arw")


def test_progress_failure_does_not_trigger_per_file_exif_fallback():
    from material_agent.core.grouper import read_exif_datetimes

    class _Progress:
        def on_phase_start(self, _label, _total):
            pass

        def on_phase_advance(self, _amount=1):
            raise RuntimeError("progress failed")

    with (
        patch(
            "material_agent.domain.grouper._read_exif_batch",
            return_value=(
                {"/library/a.arw": None},
                {"/library/a.arw": None},
            ),
        ),
        patch("material_agent.domain.grouper._read_exif_single_result") as single_read,
        pytest.raises(RuntimeError, match="progress failed"),
    ):
        read_exif_datetimes(["/library/a.arw"], progress=_Progress())

    single_read.assert_not_called()


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
            return {
                file_path: self.cache[file_path]
                for file_path in file_paths
                if file_path in self.cache
            }

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
        with patch.object(
            Grouper, "_hash_file", side_effect=AssertionError("hash should be cached")
        ):
            groups = Grouper(_cfg(visual_enabled=True)).group(files, state=state)

    assert groups == [["/a.arw", "/b.arw", "/c.arw", "/d.arw"]]
    assert hash_calls == []


def test_embedding_similarity_merges_hash_miss_and_reuses_cache():
    files = ["/a.arw", "/b.arw"]
    times = {
        "/a.arw": datetime(2024, 1, 1, 10, 0, 0),
        "/b.arw": datetime(2024, 1, 1, 10, 1, 0),
    }
    config = _cfg(visual_enabled=True)
    config["embedding_similarity"] = {"enabled": True, "threshold": 0.9}

    class _State:
        def __init__(self):
            self.embeddings = {}

        def get_visual_hash_cache(self, file_paths):
            return {}

        def set_visual_hash_cache(self, entries):
            pass

        def get_embedding_cache(self, file_paths, model_key):
            return {
                file_path: self.embeddings[file_path]
                for file_path in file_paths
                if file_path in self.embeddings
            }

        def set_embedding_cache(self, entries, model_key):
            self.embeddings.update(entries)

    state = _State()
    calls = []

    def embedding_loader(file_path):
        calls.append(file_path)
        return [1.0, 0.0] if file_path == "/a.arw" else [0.95, 0.05]

    with patch("material_agent.core.grouper.read_exif_datetimes", return_value=times):
        with patch.object(
            Grouper,
            "_hash_file",
            side_effect=[imagehash.hex_to_hash("0" * 16), imagehash.hex_to_hash("f" * 16)],
        ):
            groups = Grouper(
                config,
                embedding_loader=embedding_loader,
                embedding_model_key="fixture-v1",
            ).group(files, state=state)

    assert groups == [["/a.arw", "/b.arw"]]
    assert calls == ["/a.arw", "/b.arw"]
    assert set(state.embeddings) == set(files)

    calls.clear()
    with patch("material_agent.core.grouper.read_exif_datetimes", return_value=times):
        with patch.object(
            Grouper,
            "_hash_file",
            side_effect=[imagehash.hex_to_hash("0" * 16), imagehash.hex_to_hash("f" * 16)],
        ):
            groups = Grouper(
                config,
                embedding_loader=lambda path: calls.append(path),
                embedding_model_key="fixture-v1",
            ).group(files, state=state)

    assert groups == [["/a.arw", "/b.arw"]]
    assert calls == []
