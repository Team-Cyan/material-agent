import logging
import subprocess
import xml.etree.ElementTree as ET
import xml.sax.saxutils as _saxutils
from datetime import datetime
from pathlib import Path
from uuid import uuid4

_log = logging.getLogger("material_agent")

_XMP_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "lr": "http://ns.adobe.com/lightroom/1.0/",
}
_CREATOR_TOOL = "Team-Cyan material-agent"
_MACHINE_TAG_PREFIX = "pj:"


class ExifToolXMPWriter:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.machine_tag_target = self.config.get("machine_tag_target", "identifier")
        if self.machine_tag_target != "identifier":
            raise ValueError("ExifToolXMPWriter only supports machine_tag_target='identifier'")

    def _xmp_timestamp(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def score_to_stars(self, score: float) -> int:
        return max(0, min(5, int(score / 2 + 0.5)))

    def build_subject_tags(
        self,
        score: float,
        rank: int,
        group_size: int,
        group_id: str,
        boosted: bool,
        decision: str | None = None,
    ) -> list[str]:
        tags = [f"pj:score={score:.1f}", f"pj:rank={rank}/{group_size}", f"pj:group={group_id}"]
        if decision:
            tags.append(f"pj:decision={decision}")
        if boosted:
            tags.append("pj:boosted")
        return tags

    def _read_non_pj_subject_tags(self, xmp_path: str | Path) -> list[str]:
        try:
            tree = ET.parse(str(xmp_path))
            root = tree.getroot()
            tags = []
            for li in root.findall(".//dc:subject/rdf:Bag/rdf:li", _XMP_NS):
                if li.text and not li.text.startswith(_MACHINE_TAG_PREFIX):
                    tags.append(li.text)
            return tags
        except Exception as error:
            _log.warning(
                "Failed to read Subject tags from %s: %s — user keywords may not be preserved",
                xmp_path,
                error,
            )
            return []

    def _read_non_pj_identifier_tags(self, xmp_path: str | Path) -> list[str]:
        return self._read_non_pj_bag_tags(
            xmp_path,
            ".//xmp:Identifier/rdf:Bag/rdf:li",
            "Identifier",
        )

    def _read_non_pj_hierarchical_subject_tags(self, xmp_path: str | Path) -> list[str]:
        return self._read_non_pj_bag_tags(
            xmp_path,
            ".//lr:hierarchicalSubject/rdf:Bag/rdf:li",
            "HierarchicalSubject",
        )

    def _read_non_pj_bag_tags(self, xmp_path: str | Path, pattern: str, label: str) -> list[str]:
        try:
            tree = ET.parse(str(xmp_path))
            root = tree.getroot()
            tags = []
            for li in root.findall(pattern, _XMP_NS):
                if li.text and not li.text.startswith(_MACHINE_TAG_PREFIX):
                    tags.append(li.text)
            return tags
        except Exception as error:
            _log.warning(
                "Failed to read %s tags from %s: %s — user metadata may not be preserved",
                label,
                xmp_path,
                error,
            )
            return []

    def _sidecar_path(self, arw_path: str | Path) -> Path:
        source = Path(arw_path)
        lowercase = source.with_suffix(".xmp")
        uppercase = source.with_suffix(".XMP")
        try:
            existing_names = {child.name: child for child in source.parent.iterdir()}
        except FileNotFoundError:
            existing_names = {}
        if lowercase.name in existing_names:
            return existing_names[lowercase.name]
        if uppercase.name in existing_names:
            return existing_names[uppercase.name]
        return lowercase

    def clear_ai_tags(self, arw_path: str) -> None:
        xmp_path = self._sidecar_path(arw_path)
        if not xmp_path.exists():
            return
        preserved = self._read_non_pj_subject_tags(xmp_path)
        preserved_identifiers = self._read_non_pj_identifier_tags(xmp_path)
        preserved_hierarchical = self._read_non_pj_hierarchical_subject_tags(xmp_path)
        cmd = [
            "exiftool",
            "-XMP-xmp:Rating=",
            "-XMP-photoshop:Instructions=",
            "-XMP-dc:Description-x-default=",
            "-XMP-dc:Subject=",
            "-XMP-xmp:Identifier=",
            "-XMP-lr:HierarchicalSubject=",
        ]
        cmd += [f"-XMP-dc:Subject={tag}" for tag in preserved]
        cmd += [f"-XMP-xmp:Identifier={tag}" for tag in preserved_identifiers]
        cmd += [f"-XMP-lr:HierarchicalSubject={tag}" for tag in preserved_hierarchical]
        cmd += ["-overwrite_original", str(xmp_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"exiftool failed: {result.stderr}")

    def write(
        self,
        arw_path: str,
        rating: int,
        subject_tags: list[str],
        instructions: str,
        description: str,
    ):
        xmp_path = self._sidecar_path(arw_path)
        xmp_exists = xmp_path.exists()
        preserved = self._read_non_pj_subject_tags(xmp_path) if xmp_exists else []
        preserved_identifiers = self._read_non_pj_identifier_tags(xmp_path) if xmp_exists else []
        preserved_hierarchical = (
            self._read_non_pj_hierarchical_subject_tags(xmp_path) if xmp_exists else []
        )
        subject_tags = _dedupe(subject_tags)
        subject_args = ["-XMP-dc:Subject="] + [f"-XMP-dc:Subject={tag}" for tag in preserved]
        identifier_tags = _dedupe(preserved_identifiers + subject_tags)
        identifier_args = ["-XMP-xmp:Identifier="] + [
            f"-XMP-xmp:Identifier={tag}" for tag in identifier_tags
        ]
        hierarchical_args = ["-XMP-lr:HierarchicalSubject="] + [
            f"-XMP-lr:HierarchicalSubject={tag}" for tag in preserved_hierarchical
        ]
        metadata_date = self._xmp_timestamp()

        cmd = [
            "exiftool",
            f"-XMP-xmp:Rating={rating}",
            f"-XMP-photoshop:Instructions={instructions}",
            f"-XMP-dc:Description-x-default={description}",
            f"-XMP-xmp:CreatorTool={_CREATOR_TOOL}",
            f"-XMP-xmp:MetadataDate={metadata_date}",
            f"-XMP-xmp:ModifyDate={metadata_date}",
        ] + subject_args + identifier_args + hierarchical_args

        if xmp_exists:
            cmd += ["-overwrite_original", str(xmp_path)]
        else:
            self._write_minimal_xmp(
                xmp_path,
                rating,
                preserved,
                identifier_tags,
                preserved_hierarchical,
                instructions,
                description,
            )
            return

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"exiftool failed: {result.stderr}")

    def _write_minimal_xmp(
        self,
        xmp_path: str | Path,
        rating: int,
        subject_tags: list[str],
        identifier_tags: list[str],
        hierarchical_subject_tags: list[str],
        instructions: str,
        description: str,
    ):
        xmp_path = Path(xmp_path)
        temp_path = xmp_path.with_name(f"{xmp_path.name}.tmp-{uuid4().hex}")
        try:
            self._write_minimal_xmp_content(
                temp_path,
                rating,
                subject_tags,
                identifier_tags,
                hierarchical_subject_tags,
                instructions,
                description,
            )
            temp_path.replace(xmp_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _write_minimal_xmp_content(
        self,
        xmp_path: Path,
        rating: int,
        subject_tags: list[str],
        identifier_tags: list[str],
        hierarchical_subject_tags: list[str],
        instructions: str,
        description: str,
    ):
        esc = _saxutils.escape
        metadata_date = self._xmp_timestamp()
        document_id = f"xmp.did:{uuid4()}"
        instance_id = f"xmp.iid:{uuid4()}"
        subject_xml = _rdf_bag_xml("dc:subject", subject_tags)
        identifier_xml = _rdf_bag_xml("xmp:Identifier", identifier_tags)
        hierarchical_xml = _rdf_bag_xml("lr:hierarchicalSubject", hierarchical_subject_tags)
        xmp = (
            "<?xpacket begin=\"\ufeff\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n"
            f"<x:xmpmeta xmlns:x=\"adobe:ns:meta/\" x:xmptk=\"{_CREATOR_TOOL}\">\n"
            "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n"
            " <rdf:Description rdf:about=\"\"\n"
            "  xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\"\n"
            "  xmlns:xmpMM=\"http://ns.adobe.com/xap/1.0/mm/\"\n"
            "  xmlns:dc=\"http://purl.org/dc/elements/1.1/\"\n"
            "  xmlns:lr=\"http://ns.adobe.com/lightroom/1.0/\"\n"
            "  xmlns:photoshop=\"http://ns.adobe.com/photoshop/1.0/\">\n"
            f"  <xmp:Rating>{rating}</xmp:Rating>\n"
            f"  <xmp:CreatorTool>{_CREATOR_TOOL}</xmp:CreatorTool>\n"
            f"  <xmp:MetadataDate>{metadata_date}</xmp:MetadataDate>\n"
            f"  <xmp:ModifyDate>{metadata_date}</xmp:ModifyDate>\n"
            f"  <xmpMM:DocumentID>{document_id}</xmpMM:DocumentID>\n"
            f"  <xmpMM:InstanceID>{instance_id}</xmpMM:InstanceID>\n"
            f"{subject_xml}"
            f"{identifier_xml}"
            f"{hierarchical_xml}"
            f"  <photoshop:Instructions>{esc(instructions)}</photoshop:Instructions>\n"
            "  <dc:description>\n"
            "   <rdf:Alt>\n"
            f"   <rdf:li xml:lang=\"x-default\">{esc(description)}</rdf:li>\n"
            "   </rdf:Alt>\n"
            "  </dc:description>\n"
            " </rdf:Description>\n"
            "</rdf:RDF>\n"
            "</x:xmpmeta>\n"
            "<?xpacket end='w'?>"
        )
        xmp_path.write_text(xmp, encoding="utf-8")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _rdf_bag_xml(tag_name: str, values: list[str]) -> str:
    if not values:
        return ""
    esc = _saxutils.escape
    li_items = "\n".join(f"    <rdf:li>{esc(value)}</rdf:li>" for value in values)
    return (
        f"  <{tag_name}>\n"
        "   <rdf:Bag>\n"
        f"{li_items}\n"
        "   </rdf:Bag>\n"
        f"  </{tag_name}>\n"
    )
