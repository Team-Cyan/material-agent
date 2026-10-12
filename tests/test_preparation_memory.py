from concurrent.futures import Future
import io
import sys
from types import SimpleNamespace
import weakref

import numpy as np
import pytest

from material_agent.app import preparation_memory as memory
from material_agent.domain.scoring_engine import RawFrame


def test_payload_counts_shared_views_and_jpeg_without_double_counting():
    root = np.zeros((10, 12, 3), dtype=np.uint8)
    jpeg = b"shared-jpeg"
    first = RawFrame(jpeg, root[:, :, 0], pixels=root, focus_gray=root[:, :, 0])
    second = RawFrame(jpeg, root[2:5, :, 1], pixels=root[1:], focus_gray=None)
    one, two = {"frame": first}, {"frame": second}
    result = memory._payload_memory([one, one, two])
    assert result == {
        "prepared_live_count": 2,
        "frame_live_count": 2,
        "unknown_component_count": 0,
        "array_field_nbytes": 120 + 360 + 120 + 36 + 324,
        "array_storage_bytes": root.nbytes,
        "jpeg_storage_bytes": len(jpeg),
        "known_payload_bytes": root.nbytes + len(jpeg),
        "prepared_payload_bytes": root.nbytes + len(jpeg),
    }


def test_jpeg_owner_also_used_as_numpy_buffer_counts_once():
    jpeg = b"0123456789"
    pixels = np.frombuffer(jpeg, dtype=np.uint8)
    frame = RawFrame(jpeg, pixels[2:5], pixels=pixels, focus_gray=pixels)
    result = memory._payload_memory([{"frame": frame}, {"frame": frame}])
    assert result["frame_live_count"] == 1
    assert result["array_storage_bytes"] == len(jpeg)
    assert result["jpeg_storage_bytes"] == len(jpeg)
    assert result["prepared_payload_bytes"] == len(jpeg)


def test_bytearray_and_memoryview_array_owners_are_deduplicated():
    owner = bytearray(40)
    frame = RawFrame(
        b"jpeg",
        np.frombuffer(owner, dtype=np.uint8),
        pixels=np.frombuffer(memoryview(owner)[4:24], dtype=np.uint8),
    )
    result = memory._payload_memory([{"frame": frame}])
    assert result["array_storage_bytes"] == len(owner)
    assert result["prepared_payload_bytes"] == len(owner) + 4


def test_unknown_shapes_object_arrays_and_foreign_storage_stay_incomplete():
    class PropertyTrap:
        @property
        def nbytes(self):
            pytest.fail("arbitrary property traversed")

    arrays = np.zeros((2, 2), dtype=np.uint8)
    foreign_view = np.lib.stride_tricks.as_strided(arrays, shape=(1,), strides=(1,))
    frame = RawFrame(
        b"jpeg", PropertyTrap(), pixels=foreign_view, focus_gray=np.array([object()], dtype=object)
    )
    result = memory._payload_memory([{"frame": frame}, {"cached": True}, "legacy"])
    assert result["prepared_live_count"] == 3
    assert result["unknown_component_count"] == 4
    assert result["prepared_payload_bytes"] is None
    assert result["known_payload_bytes"] == 4
    assert result["array_field_nbytes"] == foreign_view.nbytes + frame.focus_gray.nbytes


def test_cached_empty_and_unknown_frame_payloads():
    assert memory._payload_memory([])["prepared_payload_bytes"] == 0
    assert (
        memory._payload_memory([{"cached": True, "meta": {"large": b"unused"}}])[
            "prepared_payload_bytes"
        ]
        == 0
    )
    assert memory._payload_memory([{"frame": object()}])["prepared_payload_bytes"] is None


def test_observe_does_not_wait_or_raise_stored_future_interruptions(monkeypatch):
    class UnreadyFuture(Future):
        def result(self, *args, **kwargs):
            pytest.fail("telemetry waited on an unready future")

        def exception(self, *args, **kwargs):
            pytest.fail("telemetry inspected an unready future")

    frame = RawFrame(b"jpeg", np.zeros((2, 2), dtype=np.uint8))
    item = {"frame": frame}
    ready, failed, cancelled = Future(), Future(), Future()
    ready.set_result(item)
    failed.set_exception(KeyboardInterrupt("stored worker interruption"))
    cancelled.cancel()
    monkeypatch.setattr(
        memory,
        "_process_memory",
        lambda: {
            "current_rss_bytes": None,
            "process_highwater_rss_bytes": None,
        },
    )
    observer = memory.PreparationMemoryDiagnostics()
    observer.observe(
        "after_prepare",
        current=item,
        prime_batch=[item],
        pending={
            "ready": ready,
            "failed": failed,
            "cancelled": cancelled,
            "running": UnreadyFuture(),
        },
    )
    stage = observer.stages["after_prepare"]
    assert stage["sampled_max"]["prepared_live_count"] == 1
    assert stage["sampled_max"]["pending_ready_count"] == 1
    assert stage["sampled_max"]["pending_failed_count"] == 2
    assert stage["sampled_max"]["pending_unready_count"] == 1
    assert stage["unknown_samples"]["current_rss_bytes"] == 1


def test_observer_retains_only_scalars_and_reports_unknown_samples(monkeypatch):
    monkeypatch.setattr(
        memory,
        "_process_memory",
        lambda: {
            "current_rss_bytes": None,
            "process_highwater_rss_bytes": 42,
        },
    )
    frame = RawFrame(b"jpeg", np.zeros((2, 2), dtype=np.uint8))
    reference = weakref.ref(frame)
    observer = memory.PreparationMemoryDiagnostics()
    observer.observe("score", current={"frame": frame}, prime_batch=[], pending={})
    del frame
    assert reference() is None
    observer.observe("score", current="unsupported", prime_batch=[], pending={})
    assert observer.stages["score"]["sample_count"] == 2
    assert observer.stages["score"]["unknown_samples"] == {
        "current_rss_bytes": 2,
        "prepared_payload_bytes": 1,
    }


@pytest.mark.parametrize("platform, multiplier", [("linux", 1024), ("darwin", 1)])
def test_process_memory_units_and_platform_scope(monkeypatch, platform, multiplier):
    monkeypatch.setattr(memory, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setitem(
        sys.modules,
        "resource",
        SimpleNamespace(
            RUSAGE_SELF=0,
            getrusage=lambda _: SimpleNamespace(ru_maxrss=13),
        ),
    )
    monkeypatch.setattr(memory, "open", lambda *a, **kw: io.StringIO("10 7 1"), raising=False)
    monkeypatch.setattr(memory.os, "sysconf", lambda _: 4096)
    assert memory._process_memory() == {
        "current_rss_bytes": 7 * 4096 if platform == "linux" else None,
        "process_highwater_rss_bytes": 13 * multiplier,
    }


def test_process_memory_unavailable_and_sampler_failure_are_unknown(monkeypatch):
    monkeypatch.setattr(memory, "sys", SimpleNamespace(platform="win32"))
    assert set(memory._process_memory().values()) == {None}
    monkeypatch.setattr(memory, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(memory, "open", lambda *a, **kw: io.StringIO("invalid"), raising=False)
    monkeypatch.setitem(sys.modules, "resource", None)
    assert set(memory._process_memory().values()) == {None}


def test_observation_and_logging_failures_are_nonthrowing(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("sampler unavailable")

    monkeypatch.setattr(memory, "_process_memory", fail)
    monkeypatch.setattr(memory._log, "info", fail)
    observer = memory.PreparationMemoryDiagnostics()
    with observer:
        observer.observe("score", current={"cached": True}, prime_batch=[], pending={})
    assert observer.observation_errors == 1


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_telemetry_does_not_swallow_operator_interruptions(monkeypatch, interruption):
    def interrupt():
        raise interruption("operator")

    monkeypatch.setattr(memory, "_process_memory", interrupt)
    with pytest.raises(interruption):
        with memory.PreparationMemoryDiagnostics() as observer:
            observer.observe("score", current=None, prime_batch=[], pending={})


def test_unfamiliar_preparation_does_not_import_or_traverse_arbitrary_values(monkeypatch):
    import builtins

    def forbidden(*args, **kwargs):
        pytest.fail("telemetry loaded a module for an unfamiliar preparation")

    class PropertyTrap:
        def __bool__(self):
            pytest.fail("telemetry evaluated an arbitrary cached value")

        @property
        def jpeg_bytes(self):
            pytest.fail("telemetry inspected an unknown frame")

    monkeypatch.setattr(memory, "sys", SimpleNamespace(platform="win32", modules={}))
    monkeypatch.setattr(builtins, "__import__", forbidden)
    observer = memory.PreparationMemoryDiagnostics()
    observer.observe(
        "prepare",
        current={"frame": PropertyTrap()},
        prime_batch=[
            {"cached": PropertyTrap()},
        ],
        pending={},
    )
    assert observer.observation_errors == 0
    assert observer.stages["prepare"]["sampled_max"]["unknown_component_count"] == 2
    assert "prepared_payload_bytes" not in observer.stages["prepare"]["sampled_max"]
    assert observer.stages["prepare"]["unknown_samples"]["prepared_payload_bytes"] == 1
