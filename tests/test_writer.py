from unittest.mock import patch

from material_agent.adapters.metadata.exiftool_xmp import ExifToolXMPWriter
from material_agent.io.writer import XMPWriter


_SAMPLE_XMP = (
    "<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"
    "<x:xmpmeta xmlns:x='adobe:ns:meta/'>"
    "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
    "<rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/'>"
    "<dc:subject><rdf:Bag>"
    "<rdf:li>wedding</rdf:li>"
    "<rdf:li>pj:score=7.0</rdf:li>"
    "<rdf:li>pj:rank=1/3</rdf:li>"
    "</rdf:Bag></dc:subject>"
    "</rdf:Description></rdf:RDF></x:xmpmeta>"
    "<?xpacket end='w'?>"
)


def test_writer_score_to_stars():
    w = ExifToolXMPWriter()
    assert w.score_to_stars(0.0) == 0
    assert w.score_to_stars(5.0) == 3
    assert w.score_to_stars(10.0) == 5


def test_writer_builds_subject_tags():
    w = ExifToolXMPWriter()
    tags = w.build_subject_tags(score=7.2, rank=1, group_size=5, group_id="group_001", boosted=True)
    assert "pj:score=7.2" in tags
    assert "pj:rank=1/5" in tags
    assert "pj:group=group_001" in tags
    assert "pj:boosted" in tags


def test_writer_no_boosted_tag_when_false():
    w = ExifToolXMPWriter()
    tags = w.build_subject_tags(score=8.0, rank=1, group_size=3, group_id="g1", boosted=False)
    assert "pj:boosted" not in tags


def test_writer_new_xmp_written_directly(tmp_path):
    """New XMP is written as a minimal file — no exiftool subprocess called."""
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    with patch("subprocess.run") as mock_run:
        w.write(str(arw), rating=4, subject_tags=["pj:score=8.0"], instructions="exp:8.0", description="好照片")
    assert not mock_run.called, "subprocess must not be called when creating a new XMP"
    assert xmp.exists()


def test_writer_new_xmp_contains_subject_tags(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    w.write(str(arw), rating=4, subject_tags=["pj:score=8.0", "pj:scene=人物"],
            instructions="exp:8.0", description="好照片")
    content = xmp.read_text(encoding="utf-8")
    assert "pj:score=8.0" in content
    assert "pj:scene=人物" in content


def test_writer_new_xmp_has_no_exif_namespace(tmp_path):
    """New XMP must not contain exif:/tiff: namespace data (causes Lightroom crashes)."""
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    w.write(str(arw), rating=3, subject_tags=["pj:score=7.0"], instructions="exp:7.0", description="x")
    content = xmp.read_text(encoding="utf-8")
    assert "xmlns:exif=" not in content
    assert "xmlns:tiff=" not in content


def test_writer_new_xmp_escapes_xml_special_chars(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    w.write(str(arw), rating=3, subject_tags=[], instructions="a&b <c>", description="x>y")
    content = xmp.read_text(encoding="utf-8")
    assert "a&amp;b" in content
    assert "&lt;c&gt;" in content
    assert "x&gt;y" in content


def test_writer_new_xmp_uses_lang_alt_description(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    w.write(str(arw), rating=3, subject_tags=[], instructions="x", description="好照片")

    content = xmp.read_text(encoding="utf-8")
    assert "<dc:description>" in content
    assert "<rdf:Alt>" in content
    assert "xml:lang='x-default'>好照片</rdf:li>" in content


def test_writer_new_xmp_includes_lifecycle_metadata(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    w.write(str(arw), rating=3, subject_tags=[], instructions="x", description="x")

    content = xmp.read_text(encoding="utf-8")
    assert "xmlns:xmpMM='http://ns.adobe.com/xap/1.0/mm/'" in content
    assert "<xmp:CreatorTool>Team-Cyan material-agent</xmp:CreatorTool>" in content
    assert "<xmp:MetadataDate>" in content
    assert "<xmp:ModifyDate>" in content
    assert "<xmpMM:DocumentID>xmp.did:" in content
    assert "<xmpMM:InstanceID>xmp.iid:" in content


def test_writer_new_xmp_write_is_atomic(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()

    w.write(str(arw), rating=3, subject_tags=[], instructions="x", description="x")

    assert xmp.exists()
    assert not list(tmp_path.glob("test.xmp.tmp-*"))


def test_writer_new_xmp_instructions_has_no_timestamp(tmp_path):
    """Instructions field must not contain a datetime timestamp."""
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    w = ExifToolXMPWriter()
    w.write(str(arw), rating=3, subject_tags=[], instructions="exp:7.0 sharp:8.0", description="x")
    content = xmp.read_text(encoding="utf-8")
    # Find the Instructions value
    start = content.index("<photoshop:Instructions>") + len("<photoshop:Instructions>")
    end = content.index("</photoshop:Instructions>")
    instr = content[start:end]
    assert "|" not in instr
    assert "T" not in instr  # ISO datetime contains 'T'


def test_writer_updates_existing_xmp_without_output_flag(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    xmp.write_text("existing")
    w = ExifToolXMPWriter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        w.write(str(arw), rating=4, subject_tags=["pj:score=8.0"],
                instructions="exp:8.0", description="好照片")
    cmd = mock_run.call_args[0][0]
    assert str(xmp) == cmd[-1]
    assert "-o" not in cmd


def test_writer_updates_existing_xmp_description_as_x_default(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    xmp.write_text(_SAMPLE_XMP, encoding="utf-8")
    w = ExifToolXMPWriter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        w.write(str(arw), rating=4, subject_tags=["pj:score=8.0"],
                instructions="exp:8.0", description="好照片")

    cmd = mock_run.call_args[0][0]
    assert "-XMP-photoshop:Instructions=exp:8.0" in cmd
    assert "-XMP-dc:Description-x-default=好照片" in cmd
    assert "-xmp:Description=好照片" not in cmd
    assert "-xmp:Instructions=exp:8.0" not in cmd


def test_writer_updates_existing_xmp_core_lifecycle_metadata(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    xmp.write_text(_SAMPLE_XMP, encoding="utf-8")
    w = ExifToolXMPWriter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        w.write(str(arw), rating=4, subject_tags=[], instructions="x", description="x")

    cmd = mock_run.call_args[0][0]
    assert "-XMP-xmp:CreatorTool=Team-Cyan material-agent" in cmd
    assert any(arg.startswith("-XMP-xmp:MetadataDate=") for arg in cmd)
    assert any(arg.startswith("-XMP-xmp:ModifyDate=") for arg in cmd)


def test_writer_overwrite_original_only_for_existing_xmp(tmp_path):
    """-overwrite_original must only appear when updating an existing XMP, not when creating."""
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    w = ExifToolXMPWriter()

    # New file: no subprocess at all
    with patch("subprocess.run") as mock_run:
        w.write(str(arw), rating=3, subject_tags=[], instructions="x", description="x")
    assert not mock_run.called

    # Existing file: -overwrite_original present, no -o
    xmp = tmp_path / "test.xmp"
    xmp.write_text("existing")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        w.write(str(arw), rating=3, subject_tags=[], instructions="x", description="x")
    cmd_existing = mock_run.call_args[0][0]
    assert "-overwrite_original" in cmd_existing
    assert "-o" not in cmd_existing


def test_writer_preserves_user_keywords_on_rewrite(tmp_path):
    """When rewriting an existing XMP, non-pj: keywords must be preserved."""
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    xmp.write_text(_SAMPLE_XMP, encoding="utf-8")

    w = ExifToolXMPWriter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        w.write(str(arw), rating=4, subject_tags=["pj:score=8.0"],
                instructions="exp:8.0", description="好照片")

    # Only one subprocess call (the write); reading is done via ET.parse
    assert mock_run.call_count == 1
    write_cmd = mock_run.call_args[0][0]
    assert "-xmp:Subject=wedding" in write_cmd
    assert "-xmp:Subject=pj:score=8.0" in write_cmd
    assert "-xmp:Subject=pj:score=7.0" not in write_cmd
    assert "-xmp:Subject=pj:rank=1/3" not in write_cmd


def test_writer_read_subject_tags_parses_xmp_directly(tmp_path):
    """_read_non_pj_subject_tags uses ET.parse, no subprocess."""
    xmp = tmp_path / "test.xmp"
    xmp.write_text(_SAMPLE_XMP, encoding="utf-8")
    w = ExifToolXMPWriter()
    tags = w._read_non_pj_subject_tags(str(xmp))
    assert tags == ["wedding"]


def test_writer_read_subject_tags_logs_warning_on_bad_xmp(tmp_path, caplog):
    """Bad XMP triggers a warning log and returns [] rather than crashing."""
    import logging
    xmp = tmp_path / "bad.xmp"
    xmp.write_text("not xml at all", encoding="utf-8")
    w = ExifToolXMPWriter()
    with caplog.at_level(logging.WARNING, logger="material_agent"):
        result = w._read_non_pj_subject_tags(str(xmp))
    assert result == []
    assert any("user keywords may not be preserved" in r.message for r in caplog.records)


def test_writer_clear_ai_tags_preserves_non_pj_keywords(tmp_path):
    arw = tmp_path / "test.ARW"
    arw.write_bytes(b"fake")
    xmp = tmp_path / "test.xmp"
    xmp.write_text(_SAMPLE_XMP, encoding="utf-8")
    w = ExifToolXMPWriter()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        w.clear_ai_tags(str(arw))

    cmd = mock_run.call_args[0][0]
    assert "-XMP-xmp:Rating=" in cmd
    assert "-XMP-photoshop:Instructions=" in cmd
    assert "-XMP-dc:Description-x-default=" in cmd
    assert "-xmp:Subject=" in cmd
    assert "-xmp:Subject=wedding" in cmd
    assert "-xmp:Subject=pj:score=7.0" not in cmd
    assert "-overwrite_original" in cmd


def test_io_writer_keeps_compatibility_alias():
    assert XMPWriter is ExifToolXMPWriter
