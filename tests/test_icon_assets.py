from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def test_icon_assets_and_dockerman_reference_are_canonical() -> None:
    assets = Path("docs/assets")
    template = ET.parse("deploy/unraid/material-agent.xml").getroot()
    values = {child.tag: child.text or "" for child in template}

    assert {path.name for path in assets.glob("*icon*")} == {"icon.svg", "icon.png"}
    assert not Path("assets").exists()
    assert values["Icon"].endswith("docs/assets/icon.png")
