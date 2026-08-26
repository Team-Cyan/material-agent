import logging
import shutil
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
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
}
_CREATOR_TOOL = "Team-Cyan material-agent"
_MACHINE_TAG_PREFIX = "pj:"
_MAX_XMP_BYTES = 16 * 1024 * 1024


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
        return self._read_non_pj_bag_tags(
            xmp_path,
            ".//dc:subject/rdf:Bag/rdf:li",
            "Subject",
        )

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
            root = _read_xmp_root(xmp_path)
            tags = []
            for li in root.findall(pattern, _XMP_NS):
                if li.text and not li.text.startswith(_MACHINE_TAG_PREFIX):
                    tags.append(li.text)
            return tags
        except (OSError, ET.ParseError, ValueError) as error:
            _log.warning(
                "Failed to read %s tags from %s: %s — refusing to overwrite user metadata",
                label,
                xmp_path,
                error,
            )
            raise RuntimeError(
                f"Unable to safely preserve {label} tags from existing XMP {xmp_path}"
            ) from error

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

    def _read_ai_scalar_fields(self, xmp_path: str | Path) -> dict[str, str | None]:
        try:
            root = _read_xmp_root(xmp_path)
        except (OSError, ET.ParseError, ValueError) as error:
            _log.warning(
                "Failed to read AI scalar fields from %s: %s — refusing scalar cleanup",
                xmp_path,
                error,
            )
            raise RuntimeError(
                f"Unable to safely inspect AI scalar fields in existing XMP {xmp_path}"
            ) from error

        description = None
        for item in root.findall(".//dc:description/rdf:Alt/rdf:li", _XMP_NS):
            language = item.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
            if language in {None, "x-default"}:
                description = item.text or ""
                if language == "x-default":
                    break

        return {
            "rating": _xmp_scalar_value(root, "xmp", "Rating"),
            "instructions": _xmp_scalar_value(root, "photoshop", "Instructions"),
            "description": description,
        }

    def clear_ai_tags(
        self,
        arw_path: str,
        *,
        expected_fields: dict | None = None,
        force_scalar_clear: bool = False,
    ) -> dict[str, bool]:
        xmp_path = self._sidecar_path(arw_path)
        if not xmp_path.exists():
            return {"rating": False, "instructions": False, "description": False}
        _reject_symbolic_link(xmp_path)
        source_identity = _path_identity(xmp_path)
        temp_path = xmp_path.with_name(f".{xmp_path.stem}.clear-{uuid4().hex}.xmp")
        try:
            shutil.copy2(xmp_path, temp_path)
            preserved = self._read_non_pj_subject_tags(temp_path)
            preserved_identifiers = self._read_non_pj_identifier_tags(temp_path)
            preserved_hierarchical = self._read_non_pj_hierarchical_subject_tags(temp_path)
            current_fields = self._read_ai_scalar_fields(temp_path)
            expected_fields = expected_fields or {}
            cleared = {
                key: bool(
                    force_scalar_clear
                    or (
                        key in expected_fields
                        and str(current_fields.get(key)) == str(expected_fields.get(key))
                    )
                )
                for key in ("rating", "instructions", "description")
            }
            cmd = ["exiftool"]
            if cleared["rating"]:
                cmd.append("-XMP-xmp:Rating=")
            if cleared["instructions"]:
                cmd.append("-XMP-photoshop:Instructions=")
            if cleared["description"]:
                cmd.append("-XMP-dc:Description-x-default=")
            cmd += [
                "-XMP-dc:Subject=",
                "-XMP-xmp:Identifier=",
                "-XMP-lr:HierarchicalSubject=",
            ]
            cmd += [f"-XMP-dc:Subject={tag}" for tag in preserved]
            cmd += [f"-XMP-xmp:Identifier={tag}" for tag in preserved_identifiers]
            cmd += [f"-XMP-lr:HierarchicalSubject={tag}" for tag in preserved_hierarchical]
            cmd += ["-overwrite_original", str(temp_path)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"exiftool failed: {result.stderr}")
            if _path_identity(xmp_path) != source_identity:
                raise RuntimeError(
                    f"XMP changed during AI cleanup; refusing to overwrite: {xmp_path}"
                )
            temp_path.replace(xmp_path)
            return cleared
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def write(
        self,
        arw_path: str,
        rating: int,
        subject_tags: list[str],
        instructions: str,
        description: str,
    ):
        _validate_material_rating(rating)
        xmp_path = self._sidecar_path(arw_path)
        _reject_symbolic_link(xmp_path)
        subject_tags = _dedupe(subject_tags)
        source_identity = _path_identity(xmp_path)
        temp_path = xmp_path.with_name(f".{xmp_path.stem}.write-{uuid4().hex}.xmp")
        try:
            if source_identity is not None:
                shutil.copy2(xmp_path, temp_path)
                self._update_existing_xmp(
                    temp_path,
                    rating=rating,
                    subject_tags=subject_tags,
                    instructions=instructions,
                    description=description,
                )
            else:
                self._write_minimal_xmp(
                    temp_path,
                    rating,
                    [],
                    subject_tags,
                    [],
                    instructions,
                    description,
                )
            if _path_identity(xmp_path) != source_identity:
                raise RuntimeError(f"XMP changed during write; refusing to overwrite: {xmp_path}")
            temp_path.replace(xmp_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _update_existing_xmp(
        self,
        xmp_path: str | Path,
        *,
        rating: int,
        subject_tags: list[str],
        instructions: str,
        description: str,
    ) -> None:
        """Update owned fields while retaining every unrelated XMP namespace."""

        _validate_material_rating(rating)
        xmp_path = Path(xmp_path)
        preserved = self._read_non_pj_subject_tags(xmp_path)
        preserved_identifiers = self._read_non_pj_identifier_tags(xmp_path)
        preserved_hierarchical = self._read_non_pj_hierarchical_subject_tags(xmp_path)
        identifier_tags = _dedupe(preserved_identifiers + _dedupe(subject_tags))
        metadata_date = self._xmp_timestamp()
        cmd = [
            "exiftool",
            f"-XMP-xmp:Rating={rating}",
            f"-XMP-photoshop:Instructions={instructions}",
            f"-XMP-dc:Description-x-default={description}",
            f"-XMP-xmp:CreatorTool={_CREATOR_TOOL}",
            f"-XMP-xmp:MetadataDate={metadata_date}",
            f"-XMP-xmp:ModifyDate={metadata_date}",
            "-XMP-dc:Subject=",
            *[f"-XMP-dc:Subject={tag}" for tag in preserved],
            "-XMP-xmp:Identifier=",
            *[f"-XMP-xmp:Identifier={tag}" for tag in identifier_tags],
            "-XMP-lr:HierarchicalSubject=",
            *[f"-XMP-lr:HierarchicalSubject={tag}" for tag in preserved_hierarchical],
            "-overwrite_original",
            str(xmp_path),
        ]
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
        _validate_material_rating(rating)
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
            '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            f'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="{_CREATOR_TOOL}">\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            ' <rdf:Description rdf:about=""\n'
            '  xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
            '  xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"\n'
            '  xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
            '  xmlns:lr="http://ns.adobe.com/lightroom/1.0/"\n'
            '  xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">\n'
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
            f'   <rdf:li xml:lang="x-default">{esc(description)}</rdf:li>\n'
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


def _read_xmp_root(xmp_path: str | Path) -> ET.Element:
    """Parse a bounded, declaration-free XMP document.

    XMP sidecars are local inputs but may originate in other applications or
    archives. Refusing DTD/entity declarations and limiting the byte count
    prevents entity-expansion and unbounded-input denial of service without
    adding another runtime dependency.
    """

    path = Path(xmp_path)
    with path.open("rb") as source:
        payload = source.read(_MAX_XMP_BYTES + 1)
    if len(payload) > _MAX_XMP_BYTES:
        raise ValueError(f"XMP exceeds the {_MAX_XMP_BYTES}-byte safety limit: {path}")
    normalized = payload.upper()
    if b"<!DOCTYPE" in normalized or b"<!ENTITY" in normalized:
        raise ValueError(f"XMP DTD/entity declarations are not allowed: {path}")
    # The byte bound and declaration rejection above address the ElementTree
    # hazards reported by generic XML security scanners.
    return ET.fromstring(payload)  # nosec B314


def _path_identity(path: Path) -> tuple[int, ...] | None:
    try:
        link_stat = path.lstat()
    except FileNotFoundError:
        return None
    try:
        target_stat = path.stat()
    except OSError:
        target_identity = (-1, -1, -1, -1)
    else:
        target_identity = (
            int(target_stat.st_dev),
            int(target_stat.st_ino),
            int(target_stat.st_size),
            int(target_stat.st_mtime_ns),
        )
    return (
        int(link_stat.st_dev),
        int(link_stat.st_ino),
        int(link_stat.st_size),
        int(link_stat.st_mtime_ns),
        *target_identity,
    )


def _reject_symbolic_link(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"Refusing to replace symbolic-link XMP sidecar: {path}")


def _validate_material_rating(rating: int) -> None:
    """Keep material-agent ratings inside its interoperable 0..5 star contract."""
    if type(rating) is not int or not 0 <= rating <= 5:
        raise ValueError(f"rating must be an integer from 0 to 5, got: {rating!r}")


def _xmp_scalar_value(root: ET.Element, prefix: str, local_name: str) -> str | None:
    namespace = _XMP_NS[prefix]
    qualified = f"{{{namespace}}}{local_name}"
    element = root.find(f".//{prefix}:{local_name}", _XMP_NS)
    if element is not None:
        return element.text or ""
    for description in root.findall(".//rdf:Description", _XMP_NS):
        if qualified in description.attrib:
            return description.attrib[qualified]
    return None


def _rdf_bag_xml(tag_name: str, values: list[str]) -> str:
    if not values:
        return ""
    esc = _saxutils.escape
    li_items = "\n".join(f"    <rdf:li>{esc(value)}</rdf:li>" for value in values)
    return f"  <{tag_name}>\n   <rdf:Bag>\n{li_items}\n   </rdf:Bag>\n  </{tag_name}>\n"
