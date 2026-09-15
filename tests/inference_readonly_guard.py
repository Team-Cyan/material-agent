"""Session-only pytest guard: never create/modify media or XMP, even test fixtures."""

import os
from pathlib import Path
import sys
import pytest

SUFFIXES = {
    ".xmp",
    ".arw",
    ".cr3",
    ".nef",
    ".raf",
    ".dng",
    ".orf",
    ".rw2",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".heic",
}


def sensitive(path):
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False
    name = Path(os.fsdecode(path)).name.lower()
    return any(name.endswith(suffix) or suffix + ".tmp" in name for suffix in SUFFIXES)


def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if sensitive(path) and ((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            pytest.skip("session boundary: media/XMP filesystem write blocked before execution")
    if event in {"os.remove", "os.rename", "os.rmdir"} and any(sensitive(p) for p in args[:2]):
        pytest.skip("session boundary: media/XMP mutation blocked before execution")
    if event == "subprocess.Popen":
        command = str(args[1])
        if "exiftool" in command and any(
            flag in command for flag in ["overwrite", "-Rating=", "-XMP", "-keywords="]
        ):
            pytest.skip("session boundary: external metadata writer blocked before execution")


def pytest_configure(config):
    sys.addaudithook(audit)
