from pathlib import Path


def scan_arw_files(input_dir: str, extensions: list[str] = None) -> list[str]:
    exts = extensions or ["ARW"]
    files: list[Path] = []
    for ext in exts:
        e = ext.lstrip(".").upper()
        pattern = "*." + "".join(f"[{c}{c.lower()}]" for c in e)
        files.extend(Path(input_dir).rglob(pattern))
    return sorted(str(p) for p in files)

