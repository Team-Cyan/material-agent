"""Projection snapshots and ledger tests: no media or XMP filesystem writes."""

import json
from pathlib import Path
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from material_agent.adapters.metadata import exiftool_xmp as xmp
from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository
from material_agent.app import rewrite_xmp_service as rewrite


def packet(rating):
    return ET.fromstring(
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<rdf:Description xmp:Rating="{rating}"><dc:subject><rdf:Bag>'
        "<rdf:li>family</rdf:li><rdf:li>material-agent:reject</rdf:li>"
        "</rdf:Bag></dc:subject></rdf:Description></rdf:RDF>"
    )


def plan(rating="5"):
    return xmp._projection_receipt(packet(rating), 2, ["pj:decision=keep"], "summary", "comment")


def test_import_and_planned_effective_values_remain_distinct():
    receipt = plan()
    rating = receipt["fields"]["rating"]
    assert rating == {
        "imported": "5",
        "requested": 2,
        "effective": "5",
        "planned": "5",
        "status": "skipped",
        "reason": "preserved_nonzero",
        "conflict": True,
        "imported_author": "unknown",
    }
    keywords = receipt["fields"]["keywords"]
    assert keywords["effective"] == ["family", "material-agent:reject"]
    assert keywords["planned"] == ["family", "material-agent:keep"]
    committed = xmp.finish_projection(receipt)
    assert committed["fields"]["keywords"]["effective"] == keywords["planned"]
    assert committed["fields"]["keywords"]["status"] == "written"
    assert receipt["status"] == "planned"  # original snapshot remains immutable


@pytest.mark.parametrize("operation", ["review", "rewrite"])
@pytest.mark.parametrize("fail", [False, True])
def test_atomic_paths_only_commit_receipt_after_replacement(monkeypatch, operation, fail):
    writer = xmp.ExifToolXMPWriter()
    monkeypatch.setattr(writer, "_sidecar_path", lambda _: Path("virtual.xmp"))
    monkeypatch.setattr(writer, "preview_projection", lambda *a, **k: plan())
    monkeypatch.setattr(writer, "_update_existing_xmp", Mock())
    monkeypatch.setattr(xmp, "_path_identity", lambda _: (1,))
    monkeypatch.setattr(rewrite, "_path_identity", lambda _: (1,))
    monkeypatch.setattr(xmp.shutil, "copy2", Mock())
    monkeypatch.setattr(Path, "unlink", Mock())
    replace = Mock(side_effect=OSError("simulated replacement failure") if fail else None)
    monkeypatch.setattr(Path, "replace", replace)
    kwargs = {
        "rating": 2,
        "subject_tags": ["pj:decision=keep"],
        "instructions": "",
        "description": "",
    }

    def run():
        if operation == "review":
            return writer.write("virtual.arw", **kwargs)
        return rewrite.RewriteXmpService(writer=writer)._rewrite_xmp_atomically(
            xmp_path=Path("virtual.xmp"), **kwargs
        )

    if fail:
        with pytest.raises(OSError) as error:
            run()
        receipt = error.value.xmp_receipt
        assert receipt["status"] == "failed"
        assert all(
            f["status"] == "failed" and f["effective"] is None for f in receipt["fields"].values()
        )
    else:
        receipt = run()
        assert receipt["status"] == "committed"
        assert receipt["rating"] == "preserved_nonzero"
        assert receipt["fields"]["keywords"]["status"] == "written"
    replace.assert_called_once()


def test_ledger_keeps_attempts_and_updates_only_committed_ownership(tmp_path):
    repo = SQLiteProcessedRepository(tmp_path / "fixture.db")
    try:
        repo.conn.execute(
            "INSERT INTO processed(file_path,status,score_metadata_json,xmp_payload_json) "
            "VALUES ('a','done',?,?)",
            ('{"runtime":"fixture"}', '{"rating":3}'),
        )
        repo.conn.commit()
        success = xmp.finish_projection(plan())
        repo.record_xmp_projection(
            "a", success, operation="rewrite", owned_payload={"instructions": "new"}
        )
        failure = xmp.failed_projection(plan(), ValueError("fixture"))
        repo.record_xmp_projection("a", failure, operation="rewrite", owned_payload={"rating": 2})
        row = repo.conn.execute("SELECT * FROM processed WHERE file_path='a'").fetchone()
        assert json.loads(row["xmp_payload_json"]) == {"instructions": "new"}
        assert json.loads(row["score_metadata_json"])["runtime"] == "fixture"
        repo.mark_error("a", "fixture failure")
        receipts = [
            json.loads(row[0])
            for row in repo.conn.execute(
                "SELECT receipt_json FROM xmp_projection_ledger ORDER BY id"
            )
        ]
        assert [r["status"] for r in receipts] == ["committed", "failed"]
        assert receipts[0]["fields"]["rating"]["imported_author"] == "unknown"
    finally:
        repo.close()


def test_rewrite_partial_batch_persists_success_and_failure_without_media(tmp_path, monkeypatch):
    repo = SQLiteProcessedRepository(tmp_path)
    try:
        repo.conn.executemany(
            "INSERT INTO processed(file_path,status,total_score,star_rating,group_rank,group_size,decision) "
            "VALUES (?,'done',2,1,1,1,'keep')",
            [("a",), ("b",)],
        )
        repo.conn.commit()
        service = rewrite.RewriteXmpService(repository=repo)
        success = xmp.finish_projection(plan())
        monkeypatch.setattr(
            service, "_rewrite_xmp_atomically", Mock(side_effect=[success, OSError("fixture")])
        )
        assert service.run(str(tmp_path), dry_run=False) == {"ok": 1, "err": 1}
        receipts = [
            json.loads(row[0])
            for row in repo.conn.execute(
                "SELECT receipt_json FROM xmp_projection_ledger ORDER BY id"
            )
        ]
        assert [r["status"] for r in receipts] == ["committed", "failed"]
        owned = repo.conn.execute(
            "SELECT xmp_payload_json FROM processed WHERE file_path='a'"
        ).fetchone()[0]
        assert "rating" not in json.loads(owned)
    finally:
        repo.close()


def test_review_records_failure_receipt_and_dry_run_only_plans(monkeypatch):
    from material_agent.app import review_runtime
    from material_agent.utils.config_validator import normalize_config

    writer = xmp.ExifToolXMPWriter()
    monkeypatch.setattr(writer, "_sidecar_path", lambda _: Path("virtual.xmp"))
    monkeypatch.setattr(writer, "preview_projection", lambda *a, **k: plan())
    monkeypatch.setattr(review_runtime, "ExifToolXMPWriter", lambda _: writer)
    monkeypatch.setattr(review_runtime, "make_client", lambda _: object())
    monkeypatch.setattr(review_runtime, "make_fast_screening_port", lambda _: None)
    state = Mock()
    payload = {"score_total": 4.0, "scores": {}, "meta": {}, "decision": "keep"}
    executor = review_runtime.build_review_job_executor(
        repository=Mock(), config=normalize_config({}), state=state, progress=Mock(), dry_run=True
    )
    executor.review_job.write_file("virtual.arw", payload, rank=1, group_id="g", group_size=1)
    assert payload["xmp_projection"]["status"] == "planned"
    assert payload["xmp_projection"]["effective_rating"] == "5"
    state.record_xmp_projection.assert_not_called()
    state.mark_done.assert_not_called()
    failure = OSError("fixture")
    failure.xmp_receipt = xmp.failed_projection(plan(), failure)
    monkeypatch.setattr(writer, "write", Mock(side_effect=failure))
    executor = review_runtime.build_review_job_executor(
        repository=Mock(), config=normalize_config({}), state=state, progress=Mock(), dry_run=False
    )
    with pytest.raises(OSError):
        executor.review_job.write_file("virtual.arw", payload, rank=1, group_id="g", group_size=1)
    assert state.record_xmp_projection.call_args.args[1]["status"] == "failed"
    state.mark_done.assert_not_called()
