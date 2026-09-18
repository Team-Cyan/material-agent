"""Render neutral, paired reference images in memory; never write image assets."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path

import cv2
from PIL import Image, ImageDraw
from material_agent.domain.scoring_engine import decode_raw


def render(panel, index):
    root = Path("docs/operations/benchmarks/2026-09-19-spatial-reference")
    rows = json.loads((root / "inputs.json").read_text())["pairs"]
    row = (rows if panel == "A" else list(reversed(rows)))[index]
    config = json.loads(
        Path("docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json").read_text()
    )
    images = []
    if row["kind"] == "raw":
        for item in row["images"]:
            path = Path(".local/hdrplus-holdout") / item["event"] / item["file"]
            with path.open("rb") as source:
                assert hashlib.file_digest(source, "sha256").hexdigest() == item["sha256"]
            image = decode_raw(str(path), config["preview"])
            images.append(Image.open(io.BytesIO(image.jpeg_bytes)).convert("RGB"))
    else:
        path = Path(".local/mpii-cooking") / (row["sequence"] + ".avi")
        with path.open("rb") as source:
            assert hashlib.file_digest(source, "sha256").hexdigest() == row["video_sha256"]
        cap = cv2.VideoCapture(str(path))
        try:
            for frame in row["frames"]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
                ok, bgr = cap.read()
                assert ok and abs(cap.get(cv2.CAP_PROP_POS_FRAMES) - frame - 1) < 0.1
                images.append(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        finally:
            cap.release()
    if panel == "B":
        images.reverse()
    canvas = Image.new("RGB", (1536, 600), "white")
    draw = ImageDraw.Draw(canvas)
    ids = []
    for i, im in enumerate(images):
        im.thumbnail((768, 570))
        canvas.paste(im, (i * 768, 30))
        key = f"{panel}{index + 1:02}{'L' if i == 0 else 'R'}"
        ids.append(key)
        draw.text((i * 768 + 10, 10), key, fill="black")
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=92)
    return {
        "ids": ids,
        "box_coordinates": "normalized within each 768x570 photo panel excluding the 30-pixel title; include unused padding in coordinates",
        "image": base64.b64encode(output.getvalue()).decode(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=["A", "B"])
    parser.add_argument("index", type=int)
    args = parser.parse_args()
    if not 0 <= args.index < 12:
        parser.error("index must be 0..11")
    print(json.dumps(render(args.panel, args.index)))


if __name__ == "__main__":
    main()
