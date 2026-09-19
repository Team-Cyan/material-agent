"""Render frozen supplement pairs in memory without writing derived media."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw


def render(panel, index):
    root = Path("docs/operations/benchmarks/2026-09-19-spatial-supplement")
    rows = json.loads((root / "acquisition.json").read_text())["sequences"]
    row = (rows if panel == "A" else list(reversed(rows)))[index]
    frames = row["frames"] if panel == "A" else list(reversed(row["frames"]))
    canvas = Image.new("RGB", (1536, 600), "white")
    draw = ImageDraw.Draw(canvas)
    ids = []
    for i, frame in enumerate(frames):
        data = Path(frame["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == frame["sha256"]
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im = im.resize((768, round(im.height * 768 / im.width)))
        im.thumbnail((768, 570))
        canvas.paste(im, (i * 768, 30))
        key = f"{panel}{index + 1:02}{'L' if i == 0 else 'R'}"
        ids.append(key)
        draw.text((i * 768 + 10, 10), key, fill="black")
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=95)
    return {
        "ids": ids,
        "box_coordinates": "normalized within 768x570 panel excluding title, including padding",
        "image": base64.b64encode(output.getvalue()).decode(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=["A", "B"])
    parser.add_argument("index", type=int, choices=range(4))
    args = parser.parse_args()
    print(json.dumps(render(args.panel, args.index)))
