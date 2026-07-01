from ..domain import grouper as _impl

imagehash = _impl.imagehash
io = _impl.io
json = _impl.json
rawpy = _impl.rawpy
subprocess = _impl.subprocess
Image = _impl.Image
read_exif_datetimes = _impl.read_exif_datetimes
_read_exif_single = _impl._read_exif_single


class Grouper(_impl.Grouper):
    def group(self, files: list[str], state=None, progress=None) -> list[list[str]]:
        if not files:
            return []
        times = read_exif_datetimes(files, state=state, progress=progress)
        groups = self._time_split(files, times)
        if self.config["visual_similarity"]["enabled"]:
            groups = self._visual_merge(groups, times, state=state, progress=progress)
        return groups


__all__ = [
    "Grouper",
    "Image",
    "_read_exif_single",
    "imagehash",
    "io",
    "json",
    "rawpy",
    "read_exif_datetimes",
    "subprocess",
]
