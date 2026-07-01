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
}
_CREATOR_TOOL = "Team-Cyan material-agent"


class ExifToolXMPWriter:
    def _xmp_timestamp(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def score_to_stars(self, score: float) -> int:
        return int(score / 2 + 0.5)

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
                if li.text and not li.text.startswith("pj:"):
                    tags.append(li.text)
            return tags
        except Exception as error:
            _log.warning(
                "Failed to read Subject tags from %s: %s — user keywords may not be preserved",
                xmp_path,
                error,
            )
            return []

    def clear_ai_tags(self, arw_path: str) -> None:
        xmp_path = Path(arw_path).with_suffix(".xmp")
        if not xmp_path.exists():
            return
        preserved = self._read_non_pj_subject_tags(xmp_path)
        cmd = [
            "exiftool",
            "-XMP-xmp:Rating=",
            "-XMP-photoshop:Instructions=",
            "-XMP-dc:Description-x-default=",
            "-xmp:Subject=",
        ] + [f"-xmp:Subject={tag}" for tag in preserved] + ["-overwrite_original", str(xmp_path)]
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
        xmp_path = Path(arw_path).with_suffix(".xmp")
        xmp_exists = xmp_path.exists()
        preserved = self._read_non_pj_subject_tags(xmp_path) if xmp_exists else []
        all_tags = preserved + subject_tags
        subject_args = [f"-xmp:Subject={tag}" for tag in all_tags]
        metadata_date = self._xmp_timestamp()

        cmd = [
            "exiftool",
            f"-XMP-xmp:Rating={rating}",
            f"-XMP-photoshop:Instructions={instructions}",
            f"-XMP-dc:Description-x-default={description}",
            f"-XMP-xmp:CreatorTool={_CREATOR_TOOL}",
            f"-XMP-xmp:MetadataDate={metadata_date}",
            f"-XMP-xmp:ModifyDate={metadata_date}",
        ] + subject_args

        if xmp_exists:
            cmd += ["-overwrite_original", str(xmp_path)]
        else:
            self._write_minimal_xmp(xmp_path, rating, all_tags, instructions, description)
            return

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"exiftool failed: {result.stderr}")

    def _write_minimal_xmp(
        self,
        xmp_path: str | Path,
        rating: int,
        subject_tags: list[str],
        instructions: str,
        description: str,
    ):
        xmp_path = Path(xmp_path)
        temp_path = xmp_path.with_name(f"{xmp_path.name}.tmp-{uuid4().hex}")
        try:
            self._write_minimal_xmp_content(temp_path, rating, subject_tags, instructions, description)
            temp_path.replace(xmp_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _write_minimal_xmp_content(
        self,
        xmp_path: Path,
        rating: int,
        subject_tags: list[str],
        instructions: str,
        description: str,
    ):
        esc = _saxutils.escape
        metadata_date = self._xmp_timestamp()
        document_id = f"xmp.did:{uuid4()}"
        instance_id = f"xmp.iid:{uuid4()}"
        li_items = "\n    ".join(f"    <rdf:li>{esc(t)}</rdf:li>" for t in subject_tags)
        xmp = (
            "<?xpacket begin='\\xef\\xbb\\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>\n"
            f"<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='{_CREATOR_TOOL}'>\n"
            "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>\n"
            " <rdf:Description rdf:about=''\n"
            "  xmlns:xmp='http://ns.adobe.com/xap/1.0/'\n"
            "  xmlns:xmpMM='http://ns.adobe.com/xap/1.0/mm/'\n"
            "  xmlns:dc='http://purl.org/dc/elements/1.1/'\n"
            "  xmlns:photoshop='http://ns.adobe.com/photoshop/1.0/'\n"
            f"  xmp:Rating='{rating}'>\n"
            f"  <xmp:CreatorTool>{_CREATOR_TOOL}</xmp:CreatorTool>\n"
            f"  <xmp:MetadataDate>{metadata_date}</xmp:MetadataDate>\n"
            f"  <xmp:ModifyDate>{metadata_date}</xmp:ModifyDate>\n"
            f"  <xmpMM:DocumentID>{document_id}</xmpMM:DocumentID>\n"
            f"  <xmpMM:InstanceID>{instance_id}</xmpMM:InstanceID>\n"
            "  <dc:subject>\n"
            "   <rdf:Bag>\n"
            f"{li_items}\n"
            "   </rdf:Bag>\n"
            "  </dc:subject>\n"
            f"  <photoshop:Instructions>{esc(instructions)}</photoshop:Instructions>\n"
            "  <dc:description>\n"
            "   <rdf:Alt>\n"
            f"   <rdf:li xml:lang='x-default'>{esc(description)}</rdf:li>\n"
            "   </rdf:Alt>\n"
            "  </dc:description>\n"
            " </rdf:Description>\n"
            "</rdf:RDF>\n"
            "</x:xmpmeta>\n"
            "<?xpacket end='w'?>"
        )
        xmp_path.write_text(xmp, encoding="utf-8")
