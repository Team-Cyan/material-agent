"""Create original geometric fixtures under .local for offline viewer QA, never human gold."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from human_reference import digest, file_hash, local_output, membership, render, validate


def create(directory):
    directory = local_output(directory / "manifest.json").parent
    if (directory / "manifest.json").exists():
        raise ValueError("demo already exists; choose a fresh local directory")
    manifest = {
        "schema": "material-agent.human-reference.v1",
        "freeze": {"at": "2026-09-26T10:00:00Z", "membership_sha256": "0" * 64},
        "annotators": [
            {"id": "demo_operator", "kind": "human"},
            {"id": "second_operator", "kind": "human"},
        ],
        "events": [],
        "assets": [],
        "pairs": [],
    }
    for index, split in enumerate(["development", "holdout"]):
        event = f"E{index + 1:02}"
        manifest["events"].append(
            {
                "id": event,
                "scene_family": f"F{index + 1:02}",
                "related_sources": [f"generated_{index}"],
                "split": split,
                "origin": "synthetic",
            }
        )
        for variant in range(3):
            key = f"{event}_I{variant + 1:02}"
            path = directory / f"{key}.png"
            if path.exists():
                raise ValueError(f"refusing to overwrite {path.name}")
            image = Image.new("RGB", (600, 400), (225 - index * 20, 225 - variant * 10, 225))
            draw = ImageDraw.Draw(image)
            draw.rectangle((60, 80, 260, 300), fill=(25, 80 + index * 60, 160))
            draw.ellipse((340, 100, 490, 250), fill=(200, 65, 45))
            if variant == 2:
                draw.rectangle((360, 270, 480, 340), fill=(30, 150, 75))
            image.save(path)
            sha = file_hash(path)
            manifest["assets"].append(
                {
                    "id": key,
                    "event": event,
                    "source": {
                        "path": path.name,
                        "sha256": sha,
                        "permission": "Original geometric test fixture",
                        "capture_time": "2026-09-25T12:00:00+00:00",
                        "capture_time_provenance": "Synthetic timestamp; not camera metadata",
                    },
                    "preview": {
                        "path": path.name,
                        "sha256": sha,
                        "recipe": "Original RGB PNG; oriented; no resize",
                        "width": 600,
                        "height": 400,
                        "coordinates": "normalized_xyxy_oriented_image",
                    },
                }
            )
        for variant in range(2):
            manifest["pairs"].append(
                {
                    "id": f"{event}_P{variant + 1:02}",
                    "A": f"{event}_I01",
                    "B": f"{event}_I{variant + 2:02}",
                    "annotations": [],
                }
            )
    manifest["freeze"]["membership_sha256"] = digest(membership(manifest))
    validate(manifest, directory, True)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    render(manifest, directory, "development", "demo_operator", directory / "viewer.html")
    return directory / "viewer.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(create(args.out))
