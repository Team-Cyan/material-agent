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


@pytest.mark.parametrize(
    "threshold,seconds,hashes,expected",
    [
        (8, [0, 2, 4, 6], [0, 0, 64, 64], [[0, 1], [2, 3]]),
        (0, [0, 2, 4, 6], [0, 0, 64, 64], [[0, 1, 2, 3]]),
        (8, [0, 10, 21], [0, 0, 0], [[0, 1], [2]]),
        (8, [0, 2, 4], [0, 8, 17], [[0, 1], [2]]),
        (8, [0, 2, 4], [0, None, 0], [[0], [1], [2]]),
        (8, [0, 8, 16], [0, 8, 16], [[0, 1, 2]]),
    ],
)
def test_time_and_hash_contract(threshold, seconds, hashes, expected):
    from datetime import timedelta

    files = [f"/{i}.arw" for i in range(len(seconds))]
    times = {
        f: datetime(2024, 1, 1) + timedelta(seconds=t) for f, t in zip(files, seconds, strict=True)
    }
    values = {
        f: None if n is None else imagehash.hex_to_hash(f"{(1 << n) - 1:016x}")
        for f, n in zip(files, hashes, strict=True)
    }
    config = _cfg(True)
    config.update(time_gap_seconds=10, hash_threshold=threshold)
    config["embedding_similarity"]["enabled"] = True
    with (
        patch("material_agent.core.grouper.read_exif_datetimes", return_value=times),
        patch.object(Grouper, "_hash_file", side_effect=values.get) as hashing,
    ):
        groups = Grouper(
            config, embedding_loader=lambda _: pytest.fail("embedding must not run")
        ).group(files)
    assert groups == [[files[i] for i in group] for group in expected]
    if threshold == 0:
        hashing.assert_not_called()


def test_hash_cache_covers_within_time_group_and_reuses_results():
    files = ["/a.arw", "/b.arw"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))

    class State:
        cache = {}

        def get_visual_hash_cache(self, paths):
            return self.cache

        def set_visual_hash_cache(self, entries):
            self.cache.update(entries)

    state = State()
    with (
        patch("material_agent.core.grouper.read_exif_datetimes", return_value=times),
        patch.object(
            Grouper, "_hash_file", return_value=imagehash.hex_to_hash("0" * 16)
        ) as hashing,
    ):
        assert Grouper(_cfg(True)).group(files, state) == [files]
        assert hashing.call_count == 2
        assert Grouper(_cfg(True)).group(files, state) == [files]
        assert hashing.call_count == 2


def test_zero_threshold_never_accesses_hash_cache():
    from unittest.mock import Mock

    files = ["a", "b"]
    state = Mock()
    config = _cfg(True)
    config["hash_threshold"] = 0
    with patch(
        "material_agent.core.grouper.read_exif_datetimes",
        return_value=dict.fromkeys(files, datetime(2024, 1, 1)),
    ):
        assert Grouper(config).group(files, state) == [files]
    state.get_visual_hash_cache.assert_not_called()
    state.set_visual_hash_cache.assert_not_called()


def test_standard_image_hash_reads_existing_fixture_without_raw_decode():
    from pathlib import Path
    source = Path(__file__).parent / 'fixtures/local_benchmark/ui-screenshot.png'
    with patch('material_agent.domain.grouper.rawpy.imread', side_effect=AssertionError('not RAW')):
        result = Grouper._hash_file(str(source))
    assert result is not None
    assert result.hash.size == 64
