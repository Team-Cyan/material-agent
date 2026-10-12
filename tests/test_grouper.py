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


def test_hash_cache_covers_within_time_group_and_reuses_results(caplog):
    import logging
    from unittest.mock import Mock, call

    caplog.set_level(logging.INFO, logger="material_agent")
    files = ["/a.arw", "/b.arw"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))

    class State:
        cache = {}
        writes = []

        def get_visual_hash_cache(self, paths):
            return self.cache

        def set_visual_hash_cache(self, entries):
            self.writes.append(entries.copy())
            self.cache.update(entries)

    state = State()
    progress = Mock()
    with (
        patch("material_agent.core.grouper.read_exif_datetimes", return_value=times),
        patch.object(
            Grouper, "_hash_file", return_value=imagehash.hex_to_hash("0" * 16)
        ) as hashing,
    ):
        assert Grouper(_cfg(True)).group(files, state, progress) == [files]
        assert hashing.call_count == 2
        assert hashing.call_args_list == [call(path) for path in files]
        assert state.cache == dict.fromkeys(files, "phash-exif-v1:" + "0" * 16)
        assert Grouper(_cfg(True)).group(files, state, progress) == [files]
        assert hashing.call_count == 2
    assert progress.mock_calls == (
        [call.on_phase_start("time/hash grouping", 2)] + [call.on_phase_advance()] * 2
    ) * 2
    assert state.writes == [dict.fromkeys(files, "phash-exif-v1:" + "0" * 16)]
    cold, warm = [record.grouping_diagnostics for record in caplog.records]
    assert cold["hash_computed_success"] == 2
    assert cold["cache_returned_accepted"] == cold["cache_reused"] == 0
    assert warm["hash_computed_success"] == 0
    assert warm["cache_returned_accepted"] == warm["cache_reused"] == 2


def test_zero_threshold_never_accesses_hash_cache():
    from unittest.mock import Mock

    files = ["a", "b"]
    state = Mock()
    config = _cfg(True)
    config["hash_threshold"] = 0
    with (
        patch(
            "material_agent.core.grouper.read_exif_datetimes",
            return_value=dict.fromkeys(files, datetime(2024, 1, 1)),
        ),
        patch.object(Grouper, "_hash_file", side_effect=AssertionError("no decode")),
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


@pytest.mark.parametrize("error_name", ["LibRawNoThumbnailError", "LibRawUnsupportedThumbnailError"])
def test_raw_hash_falls_back_to_half_size_decode_and_caches(monkeypatch, error_name, caplog):
    import logging
    from unittest.mock import MagicMock, Mock, call
    import numpy as np
    from material_agent.domain import grouper

    caplog.set_level(logging.INFO, logger="material_agent")
    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.extract_thumb.side_effect = getattr(grouper.rawpy, error_name)()
    rgb = np.random.default_rng(0).integers(0, 256, (32, 48, 3), dtype=np.uint8)
    raw.postprocess.return_value = rgb
    monkeypatch.setattr(grouper.Image, "open", Mock(side_effect=OSError("RAW")))
    monkeypatch.setattr(grouper.rawpy, "imread", Mock(return_value=raw))
    files = ["a.dng", "b.dng"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    state = Mock()
    cache = {}
    state.get_visual_hash_cache.side_effect = lambda _: cache.copy()
    state.set_visual_hash_cache.side_effect = cache.update
    progress = Mock()
    instance = grouper.Grouper({"time_gap_seconds": 30, "hash_threshold": 10})
    assert instance._group_with_times(files, times, state=state, progress=progress) == [files]
    assert len(cache) == 2
    assert raw.postprocess.call_count == 2
    raw.postprocess.assert_called_with(use_camera_wb=True, output_bps=8, half_size=True)
    assert instance._group_with_times(files, times, state=state, progress=progress) == [files]
    assert raw.postprocess.call_count == 2
    assert raw.extract_thumb.call_count == 2
    assert grouper.Image.open.call_count == grouper.rawpy.imread.call_count == 2
    state.set_visual_hash_cache.assert_called_once_with(cache)
    assert state.get_visual_hash_cache.call_args_list == [call(files), call(files)]
    assert progress.mock_calls == (
        [call.on_phase_start("time/hash grouping", 2)] + [call.on_phase_advance()] * 2
    ) * 2
    cold, warm = [record.grouping_diagnostics for record in caplog.records]
    assert cold["hash_computed_success"] == 2
    assert cold["hash_computed_missing"] == 0  # Earlier thumbnail failure is not terminal.
    assert warm["hash_computed_success"] == warm["hash_computed_missing"] == 0
    assert warm["cache_reused"] == 2


def test_raw_hash_decode_failure_remains_missing(monkeypatch):
    from unittest.mock import MagicMock, Mock
    from material_agent.domain import grouper

    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.extract_thumb.side_effect = grouper.rawpy.LibRawNoThumbnailError()
    raw.postprocess.side_effect = RuntimeError("unreadable raw")
    monkeypatch.setattr(grouper.Image, "open", Mock(side_effect=OSError("RAW")))
    monkeypatch.setattr(grouper.rawpy, "imread", Mock(return_value=raw))
    assert grouper.Grouper._hash_file("broken.dng") is None
    raw.postprocess.assert_called_once()


def test_raw_embedded_thumbnail_hash_does_not_postprocess(monkeypatch):
    from unittest.mock import MagicMock, Mock
    from types import SimpleNamespace
    import numpy as np
    from PIL import Image
    from material_agent.domain import grouper

    rgb = np.random.default_rng(42).integers(0, 256, (32, 48, 3), dtype=np.uint8)
    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.extract_thumb.return_value = SimpleNamespace(format=grouper.rawpy.ThumbFormat.BITMAP, data=rgb)
    monkeypatch.setattr(grouper.Image, "open", Mock(side_effect=OSError("RAW")))
    monkeypatch.setattr(grouper.rawpy, "imread", Mock(return_value=raw))
    assert grouper.Grouper._hash_file("embedded.dng") == imagehash.phash(Image.fromarray(rgb))
    raw.postprocess.assert_not_called()


def _oriented_jpeg(tmp_path, orientation):
    """Return stored JPEG pixels and an independently applied display transform."""
    import numpy as np
    from PIL import Image

    # Asymmetry in both axes makes all eight display transforms observable.
    rgb = np.random.default_rng(23).integers(0, 256, (73, 119, 3), dtype=np.uint8)
    rgb[:30, :40] = (240, 20, 40)
    rgb[40:, 60:] = (20, 220, 50)
    rgb[10:65, 85:100] = (30, 40, 230)
    path = tmp_path / f"orientation-{orientation}.jpg"
    exif = Image.Exif()
    exif[274] = orientation
    Image.fromarray(rgb).save(path, quality=97, exif=exif)
    with Image.open(path) as source:
        stored = source.convert("RGB")
    transforms = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_270,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_90,
    }
    displayed = stored.transpose(transforms[orientation]) if orientation != 1 else stored.copy()
    return path, stored, displayed


@pytest.mark.parametrize("orientation", range(1, 9))
@pytest.mark.parametrize("embedded", [False, True], ids=["standard", "embedded-jpeg"])
def test_jpeg_hash_uses_display_orientation_once(tmp_path, monkeypatch, orientation, embedded):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, Mock

    import numpy as np
    from material_agent.domain import grouper

    path, stored, displayed = _oriented_jpeg(tmp_path, orientation)
    expected = displayed.copy()
    expected.thumbnail((256, 256))
    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.extract_thumb.return_value = SimpleNamespace(
        format=grouper.rawpy.ThumbFormat.JPEG, data=path.read_bytes()
    )
    image_open = grouper.Image.open

    def open_image(source):
        if source == "embedded.dng":
            raise OSError("RAW")
        return image_open(source)

    monkeypatch.setattr(grouper.Image, "open", open_image)
    imread = Mock(return_value=raw, side_effect=None if embedded else AssertionError("not RAW"))
    monkeypatch.setattr(grouper.rawpy, "imread", imread)
    phash = grouper.imagehash.phash
    captured = []

    def hash_displayed(image):
        captured.append(np.asarray(image).copy())
        return phash(image)

    monkeypatch.setattr(grouper.imagehash, "phash", hash_displayed)
    assert Grouper._hash_file("embedded.dng" if embedded else str(path)) == phash(expected)
    assert len(captured) == 1
    np.testing.assert_array_equal(captured[0], np.asarray(expected))
    if orientation == 1:
        assert phash(expected) == phash(stored)
    else:
        assert phash(expected) - phash(stored) > 10
    raw.postprocess.assert_not_called()
    if embedded:
        raw.extract_thumb.assert_called_once()
    else:
        imread.assert_not_called()


@pytest.mark.parametrize("orientation", range(1, 9))
def test_display_equivalent_jpeg_and_png_group_at_existing_threshold(tmp_path, orientation, caplog):
    import logging
    from unittest.mock import Mock, call

    caplog.set_level(logging.INFO, logger="material_agent")
    path, _, displayed = _oriented_jpeg(tmp_path, orientation)
    canonical = tmp_path / "canonical.png"
    displayed.save(canonical)
    files = [str(path), str(canonical)]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    progress = Mock()
    with patch.object(Grouper, "_hash_file", wraps=Grouper._hash_file) as hashing:
        assert Grouper(_cfg(True))._group_with_times(files, times, progress=progress) == [files]
    assert hashing.call_args_list == [call(path) for path in files]
    assert progress.mock_calls == [call.on_phase_start("time/hash grouping", 2)] + [
        call.on_phase_advance()
    ] * 2
    assert caplog.records[-1].grouping_diagnostics["hash_computed_success"] == 2


@pytest.mark.parametrize(
    "cached",
    [
        "0" * 16,
        "phash-exif-v0:" + "0" * 16,
        "phash-exif-v1:" + "0" * 15,
        "phash-exif-v1:" + "0" * 17,
        "phash-exif-v1:" + "g" * 16,
        "phash-exif-v1:" + "0" * 16 + "\n",
        None,
        123,
    ],
)
def test_stale_or_malformed_hash_cache_recomputes(cached, caplog):
    import logging
    from unittest.mock import Mock, call

    caplog.set_level(logging.INFO, logger="material_agent")

    files = ["a", "b"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    state = Mock()
    state.get_visual_hash_cache.return_value = dict.fromkeys(files, cached)
    with patch.object(
        Grouper, "_hash_file", return_value=imagehash.hex_to_hash("0" * 16)
    ) as hashing:
        assert Grouper(_cfg(True))._group_with_times(files, times, state) == [files]
    assert hashing.call_count == 2
    assert hashing.call_args_list == [call(path) for path in files]
    state.set_visual_hash_cache.assert_called_once_with(
        dict.fromkeys(files, "phash-exif-v1:" + "0" * 16)
    )
    diagnostic = caplog.records[-1].grouping_diagnostics
    assert diagnostic["cache_returned_rejected"] == 2
    assert diagnostic["cache_returned_accepted"] == diagnostic["cache_reused"] == 0
    assert diagnostic["hash_computed_success"] == 2


def test_failed_hash_retries_without_persisting_missing():
    from unittest.mock import Mock

    files = ["a", "b"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    state = Mock()
    state.get_visual_hash_cache.return_value = {}
    with patch.object(Grouper, "_hash_file", return_value=None) as hashing:
        instance = Grouper(_cfg(True))
        assert instance._group_with_times(files, times, state) == [["a"], ["b"]]
        assert instance._group_with_times(files, times, state) == [["a"], ["b"]]
    assert hashing.call_count == 4
    state.set_visual_hash_cache.assert_not_called()


@pytest.mark.parametrize("embedded", [False, True], ids=["postprocess", "bitmap"])
def test_raw_array_pixels_are_not_transposed(monkeypatch, embedded):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, Mock

    import numpy as np
    from PIL import Image
    from material_agent.domain import grouper

    rgb = np.random.default_rng(7).integers(0, 256, (51, 89, 3), dtype=np.uint8)
    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.sizes.flip = 6
    if embedded:
        raw.extract_thumb.return_value = SimpleNamespace(
            format=grouper.rawpy.ThumbFormat.BITMAP, data=rgb
        )
    else:
        raw.extract_thumb.side_effect = grouper.rawpy.LibRawNoThumbnailError()
        raw.postprocess.return_value = rgb
    monkeypatch.setattr(grouper.Image, "open", Mock(side_effect=OSError("RAW")))
    monkeypatch.setattr(grouper.rawpy, "imread", Mock(return_value=raw))
    monkeypatch.setattr(
        grouper.ImageOps, "exif_transpose", Mock(side_effect=AssertionError("already oriented"))
    )
    assert Grouper._hash_file("array.dng") == imagehash.phash(Image.fromarray(rgb))
    grouper.ImageOps.exif_transpose.assert_not_called()
    if embedded:
        raw.postprocess.assert_not_called()
    else:
        raw.postprocess.assert_called_once_with(
            use_camera_wb=True, output_bps=8, half_size=True
        )


def test_orientation_cache_revision_crosses_real_sqlite_boundary(tmp_path):
    from PIL import Image
    from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository

    path, stored, displayed = _oriented_jpeg(tmp_path, 6)
    canonical = tmp_path / "canonical.png"
    displayed.save(canonical)
    files = [str(path), str(canonical)]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    database = tmp_path / "state.db"
    legacy = {files[0]: str(imagehash.phash(stored)), files[1]: str(imagehash.phash(displayed))}
    assert imagehash.hex_to_hash(legacy[files[0]]) - imagehash.hex_to_hash(legacy[files[1]]) > 10
    with SQLiteProcessedRepository(database) as state:
        state.set_visual_hash_cache(legacy)
        state.conn.execute(
            "INSERT INTO processed (file_path, status, total_score) VALUES (?, ?, ?)",
            (files[0], "done", 4.25),
        )
        state.conn.commit()
        before = tuple(state.conn.execute("SELECT * FROM processed").fetchone())
        assert Grouper(_cfg(True))._group_with_times(files, times, state) == [files]
        cached = state.get_visual_hash_cache(files)
        assert set(cached) == set(files)
        assert all(value.startswith("phash-exif-v1:") for value in cached.values())
        assert tuple(state.conn.execute("SELECT * FROM processed").fetchone()) == before
    with SQLiteProcessedRepository(database) as reopened:
        with patch.object(Grouper, "_hash_file", side_effect=AssertionError("cache must persist")):
            assert Grouper(_cfg(True))._group_with_times(files, times, reopened) == [files]
        assert reopened.get_visual_hash_cache(files) == cached
        assert tuple(reopened.conn.execute("SELECT * FROM processed").fetchone()) == before
    with Image.open(path) as unchanged:
        assert unchanged.getexif()[274] == 6


@pytest.mark.parametrize("capture_log", [False, True], ids=["logging-off", "logging-on"])
@pytest.mark.parametrize(
    "threshold,seconds,bits,expected,hashes_by_step,splits",
    [
        (0, [0, 10, 20], [0, 64, 0], [[0, 1, 2]], [[], [], []], {}),
        (8, [0, 10, 20], [0, 8, 16], [[0, 1, 2]], [[], [0, 1], [2]], {}),
        (8, [0, 10, 21], [0, 0, 0], [[0, 1], [2]], [[], [0, 1], []],
         {"split_time_gap": 1}),
        (8, [0, 2, 4], [0, None, 0], [[0], [1], [2]], [[], [0, 1], [2]],
         {"split_missing_hash": 2}),
        (8, [0, 2, 4], [0, 8, 17], [[0, 1], [2]], [[], [0, 1], [2]],
         {"split_hash_distance": 1}),
        (8, [0, None, None], [0, 0, 0], [[0], [2], [1]], [[], [], []],
         {"split_missing_time": 2}),
        (8, [None], [0], [[0]], [[]], {}),
        (8, [None, None], [0, 0], [[1], [0]], [[], []], {"split_missing_time": 1}),
    ],
)
def test_completion_diagnostics_preserve_order_and_side_effect_sequence(
    caplog, capture_log, threshold, seconds, bits, expected, hashes_by_step, splits
):
    import logging
    from datetime import timedelta

    caplog.set_level(logging.INFO if capture_log else logging.WARNING, logger="material_agent")
    ordered = [f"{i}.arw" for i in range(len(seconds))]
    times = {
        path: None if second is None else datetime(2024, 1, 1) + timedelta(seconds=second)
        for path, second in zip(ordered, seconds, strict=True)
    }
    values = {
        path: None if bit is None else imagehash.hex_to_hash(f"{(1 << bit) - 1:016x}")
        for path, bit in zip(ordered, bits, strict=True)
    }
    events = []

    class State:
        def get_visual_hash_cache(self, paths):
            events.append(("cache_read", paths.copy()))
            return {}

        def set_visual_hash_cache(self, entries):
            events.append(("cache_write", entries.copy()))

    class Progress:
        def on_phase_start(self, phase, count):
            events.append(("start", phase, count))

        def on_phase_advance(self):
            events.append(("advance",))

    def hash_file(path):
        events.append(("hash", path))
        return values[path]

    with patch.object(Grouper, "_hash_file", side_effect=hash_file):
        groups = Grouper({"time_gap_seconds": 10, "hash_threshold": threshold})._group_with_times(
            list(reversed(ordered)), times, State(), Progress()
        )
    # Stable input order is retained among missing timestamps.
    assert groups == [[ordered[i] for i in group] for group in expected]
    expected_events = [("cache_read", [path for group in groups for path in group])] if threshold else []
    expected_events.append(("start", "time/hash grouping", len(ordered)))
    for step in hashes_by_step:
        expected_events.extend(("hash", ordered[i]) for i in step)
        expected_events.append(("advance",))
    computed = [ordered[i] for step in hashes_by_step for i in step]
    writes = {path: "phash-exif-v1:" + str(values[path]) for path in computed if values[path] is not None}
    if writes:
        expected_events.append(("cache_write", writes))
    assert events == expected_events
    records = [record for record in caplog.records if hasattr(record, "grouping_diagnostics")]
    assert len(records) == int(capture_log)
    if capture_log:
        diagnostic = records[0].grouping_diagnostics
        assert diagnostic["hash_computed_success"] == len(writes)
        assert diagnostic["hash_computed_missing"] == len(computed) - len(writes)
        assert diagnostic["cache_returned_accepted"] == diagnostic["cache_returned_rejected"] == 0
        assert diagnostic["cache_reused"] == 0
        assert diagnostic["pairs_merged"] == len(ordered) - len(groups)
        for reason in ("missing_time", "time_gap", "missing_hash", "hash_distance"):
            assert diagnostic[f"split_{reason}"] == splits.get(f"split_{reason}", 0)
        assert sum(diagnostic[f"split_{reason}"] for reason in (
            "missing_time", "time_gap", "missing_hash", "hash_distance"
        )) == len(groups) - 1
        assert diagnostic["groups"] == len(groups)
        assert diagnostic["files"] == len(ordered)
        lengths = {}
        for group in groups:
            lengths[len(group)] = lengths.get(len(group), 0) + 1
        assert diagnostic["group_length_counts"] == lengths
        known_spans = [
            (times[group[-1]] - times[group[0]]).total_seconds()
            for group in groups if times[group[0]] is not None and times[group[-1]] is not None
        ]
        assert diagnostic["group_span_known"] == len(known_spans)
        assert diagnostic["group_span_unknown"] == len(groups) - len(known_spans)
        assert diagnostic["group_span_seconds_min"] == (min(known_spans) if known_spans else None)
        assert diagnostic["group_span_seconds_max"] == (max(known_spans) if known_spans else None)
        assert diagnostic["group_span_seconds_total"] == sum(known_spans)


def test_empty_group_completion_has_no_cache_hash_exif_or_progress_work(caplog):
    import logging
    from unittest.mock import Mock
    from material_agent.domain.grouper import Grouper as DomainGrouper

    caplog.set_level(logging.INFO, logger="material_agent")

    state, progress = Mock(), Mock()
    with (
        patch("material_agent.domain.grouper.read_exif_datetimes") as exif,
        patch.object(DomainGrouper, "_hash_file") as hashing,
    ):
        assert DomainGrouper({}).group([], state, progress) == []
    assert not state.mock_calls and not progress.mock_calls
    exif.assert_not_called()
    hashing.assert_not_called()
    diagnostic = caplog.records[-1].grouping_diagnostics
    assert diagnostic["groups"] == diagnostic["files"] == 0
    assert diagnostic["group_length_counts"] == {}
    assert diagnostic["group_span_seconds_min"] is None
    assert diagnostic["group_span_seconds_max"] is None


def test_cache_completion_counts_returned_values_and_actual_reuse(caplog):
    import logging
    from unittest.mock import Mock, call

    caplog.set_level(logging.INFO, logger="material_agent")
    files = ["a", "b", "c", "d"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    valid = "phash-exif-v1:" + "0" * 16
    state, progress = Mock(), Mock()
    # A missing adapter entry is not an observed rejection; old/malformed returned values are.
    state.get_visual_hash_cache.return_value = {"a": "0" * 16, "b": valid, "c": None}
    with patch.object(Grouper, "_hash_file", return_value=imagehash.hex_to_hash("0" * 16)) as hashing:
        assert Grouper(_cfg(True))._group_with_times(files, times, state, progress) == [files]
    assert hashing.call_args_list == [call("a"), call("c"), call("d")]
    state.get_visual_hash_cache.assert_called_once_with(files)
    state.set_visual_hash_cache.assert_called_once_with({path: valid for path in ("a", "c", "d")})
    assert progress.mock_calls == [call.on_phase_start("time/hash grouping", 4)] + [
        call.on_phase_advance()
    ] * 4
    diagnostic = caplog.records[-1].grouping_diagnostics
    assert diagnostic["cache_returned_accepted"] == 1
    assert diagnostic["cache_returned_rejected"] == 2
    assert diagnostic["cache_reused"] == 2  # b is the right then left neighbor.
    assert diagnostic["hash_computed_success"] == 3
    assert diagnostic["hash_computed_missing"] == 0
    assert diagnostic["pairs_merged"] == 3


def test_accepted_cache_entry_not_used_after_time_split(caplog):
    import logging
    from datetime import timedelta
    from unittest.mock import Mock

    caplog.set_level(logging.INFO, logger="material_agent")
    files = ["a", "b"]
    times = {"a": datetime(2024, 1, 1), "b": datetime(2024, 1, 1) + timedelta(seconds=31)}
    state = Mock()
    state.get_visual_hash_cache.return_value = dict.fromkeys(files, "phash-exif-v1:" + "0" * 16)
    with patch.object(Grouper, "_hash_file", side_effect=AssertionError("no hash on time split")):
        assert Grouper(_cfg(True))._group_with_times(files, times, state) == [["a"], ["b"]]
    state.set_visual_hash_cache.assert_not_called()
    diagnostic = caplog.records[-1].grouping_diagnostics
    assert diagnostic["cache_returned_accepted"] == 2
    assert diagnostic["cache_reused"] == 0
    assert diagnostic["split_time_gap"] == 1
    assert diagnostic["hash_computed_success"] == diagnostic["hash_computed_missing"] == 0


@pytest.mark.parametrize("failure", ["progress", "cache_write"])
def test_grouping_failure_propagates_without_completion_log(caplog, failure):
    import logging
    from unittest.mock import Mock, call

    caplog.set_level(logging.INFO, logger="material_agent")
    files = ["a", "b"]
    times = dict.fromkeys(files, datetime(2024, 1, 1))
    state, progress = Mock(), Mock()
    state.get_visual_hash_cache.return_value = {}
    if failure == "progress":
        progress.on_phase_advance.side_effect = RuntimeError("progress failed")
    else:
        state.set_visual_hash_cache.side_effect = RuntimeError("cache_write failed")
    with (
        patch.object(Grouper, "_hash_file", return_value=imagehash.hex_to_hash("0" * 16)) as hashing,
        pytest.raises(RuntimeError, match=f"{failure} failed"),
    ):
        Grouper(_cfg(True))._group_with_times(files, times, state, progress)
    assert hashing.call_args_list == ([] if failure == "progress" else [call(path) for path in files])
    if failure == "progress":
        state.set_visual_hash_cache.assert_not_called()
    assert not [record for record in caplog.records if hasattr(record, "grouping_diagnostics")]
