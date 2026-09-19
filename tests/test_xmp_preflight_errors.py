"""Exercise real XML preflight failures without creating photos or sidecars."""

import io
from pathlib import Path
from unittest.mock import Mock

import pytest

from material_agent.adapters.metadata import exiftool_xmp as xmp


@pytest.mark.parametrize(
    "payload,limit",
    [
        (b"<broken", 1024),
        (b"<!DOCTYPE x [<!ENTITY expansion 'unsafe'>]><x/>", 1024),
        (b"<x>" + b"a" * 64 + b"</x>", 32),
    ],
)
def test_preflight_parse_errors_preserve_writer_contract(monkeypatch, payload, limit):
    path = Path("memory-only-sidecar.xmp")
    original_open = Path.open

    def read_memory(self, mode="r", *args, **kwargs):
        if self == path:
            assert mode == "rb"
            return io.BytesIO(payload)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_memory)
    monkeypatch.setattr(xmp, "_path_identity", lambda p: (1, 2, 3))
    monkeypatch.setattr(xmp, "_MAX_XMP_BYTES", limit)
    cleanup = Mock()
    monkeypatch.setattr(Path, "unlink", cleanup)
    run = Mock()
    copy = Mock()
    monkeypatch.setattr(xmp.subprocess, "run", run)
    monkeypatch.setattr(xmp.shutil, "copy2", copy)
    writer = xmp.ExifToolXMPWriter()
    monkeypatch.setattr(writer, "_sidecar_path", lambda p: path)
    with pytest.raises(RuntimeError, match="Unable to safely preserve Subject") as caught:
        writer.write(
            "memory-only-photo.ARW", rating=4, subject_tags=[], instructions="", description=""
        )
    assert isinstance(caught.value.__cause__, (ValueError, xmp.ET.ParseError))
    assert caught.value.xmp_receipt["status"] == "failed"
    run.assert_not_called()
    copy.assert_not_called()
    cleanup.assert_called_once()
