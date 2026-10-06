from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest

from material_agent.commands import persisted_score_audit as audit
from material_agent.commands.score_review import build_score_review, cmd_review_scores

A, B, NEW, OPEN, WRONG = (letter * 32 for letter in "abcde")


def _fact(decision="keep", *, selection="keep", role="quality_policy"):
    return {
        "quality_assessment": {"version": 1, "decision": decision, "reasons": []},
        "selection": {"version": 1, "decision": selection, "role": role, "reasons": []},
    }


@pytest.fixture
def corpus(tmp_path):
    source = tmp_path / "original-input"
    source.mkdir()
    other = tmp_path / "historical-missing-input"
    photo = source / "shared.ARW"
    photo.write_bytes(b"unchanged photo bytes; no decoding needed")
    paths = [
        str(photo),
        str(source / "null.ARW"),
        str(source / "inf.ARW"),
        str(source / "Case.ARW"),
        str(source / "duplicates.ARW"),
        str(source / "legacy.ARW"),
    ]
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY,kind TEXT,input_root TEXT,config_snapshot TEXT,
                                  status TEXT,created_at TEXT,finished_at TEXT);
            CREATE TABLE jobs(id TEXT PRIMARY KEY,session_id TEXT,type TEXT,stage TEXT,status TEXT,
                              summary_json TEXT,started_at TEXT,finished_at TEXT);
            CREATE TABLE job_files(id TEXT PRIMARY KEY,job_id TEXT,file_path TEXT,group_id TEXT,rank INTEGER,
                                   status TEXT,error_code TEXT,error_message TEXT,score_total REAL,scene TEXT,scene_raw TEXT);
            CREATE TABLE artifacts(id TEXT PRIMARY KEY,job_id TEXT,job_file_id TEXT,kind TEXT,
                                   uri TEXT,metadata_json TEXT,created_at TEXT);
        """)
        first_config = {
            "backend": "local",
            "preview": {"max_size": 1024, "jpeg_quality": 85},
            "api_key": "secret-a",
            "future_setting": {"preserve": [1, 2]},
            "local": {"quality": {"enabled": True}},
            "image": "current-image-is-not-history",
        }
        second_config = {
            **first_config,
            "api_key": "secret-b",
            "application_revision": "saved-revision",
            "preview": {"max_size": 2048, "jpeg_quality": 85},
        }
        for job, root, config, status, kind, timestamp in (
            (A, source, first_config, "finished_with_errors", "review_photos", "1"),
            (B, other, second_config, "finished", "review_photos", "2"),
            (NEW, source, {"preview": {"max_size": 99}}, "finished", "review_photos", "9"),
            (OPEN, source, {}, "running", "review_photos", "8"),
            (WRONG, source, {}, "finished", "scan", "7"),
        ):
            connection.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                ("s-" + job, "review", str(root), json.dumps(config), status, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                (
                    job,
                    "s-" + job,
                    kind,
                    "finalize",
                    status,
                    json.dumps({"errors": 1 if job == A else 0, "password": "summary-secret"}),
                    timestamp,
                    timestamp,
                ),
            )

        def add(job, index, path, score, group, rank, status, payload=None, error=None):
            file_id = job[0] + str(index)
            connection.execute(
                "INSERT INTO job_files VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    file_id,
                    job,
                    path,
                    group,
                    rank,
                    status,
                    "decode_error" if error else None,
                    error,
                    score,
                    "people",
                    "fixture",
                ),
            )
            if payload is not None:
                text = payload if isinstance(payload, str) else json.dumps(payload)
                connection.execute(
                    "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                    (file_id + "-art", job, file_id, "score_payload", "memory://score", text, "1"),
                )
            return file_id

        add(
            A,
            0,
            paths[0],
            8.0,
            "same-group",
            1,
            "done",
            {
                "score_total": 8.0,
                "decision": "keep",
                "meta": _fact("reject", role="group_coverage"),
            },
        )
        add(A, 1, paths[1], None, "same-group", 2, "error", error="original decode failure")
        add(
            A,
            2,
            paths[2],
            float("inf"),
            "same-group",
            2,
            "done",
            {
                "score_total": float("inf"),
                "decision": "review",
                "meta": {
                    "quality_assessment": {"version": 1, "decision": ["reject"], "reasons": []},
                    "selection": {
                        "version": 2,
                        "decision": "keep",
                        "role": "future",
                        "reasons": [],
                    },
                    "_quality": {
                        "aggregate_score": 0,
                        "signals": {"musiq": {"raw_score": float("nan"), "normalized_score": 0}},
                    },
                },
            },
        )
        add(A, 3, paths[3], "bad-score", None, 7, "done", "{malformed")
        duplicate = add(
            A, 4, paths[4], 6.0, "same-group", 99, "done", {"decision": "keep", "meta": _fact()}
        )
        connection.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
            ("extra", A, duplicate, "score_payload", "memory://duplicate", "{}", "2"),
        )
        add(A, 5, paths[5], 4.0, None, 1, "done", {"decision": "review"})
        add(
            B,
            0,
            paths[0],
            7.5,
            "same-group",
            1,
            "done",
            {"score_total": 7.5, "decision": "keep", "meta": _fact()},
        )
        add(
            B,
            1,
            paths[1],
            5.0,
            "same-group",
            2,
            "done",
            {"decision": "review", "meta": _fact("review", selection="review")},
        )
        add(B, 2, paths[2], 9.0, "same-group", 3, "done", {"decision": "keep", "meta": _fact()})
        add(B, 3, str(source / "case.ARW"), 3.0, "same-group", 4, "done", {"decision": "review"})
        add(B, 4, paths[4], 2.0, None, 1, "done", {"meta": _fact("reject", selection="reject")})
        add(
            B,
            5,
            paths[5],
            0.0,
            None,
            None,
            "done",
            {
                "decision": "reject",
                "meta": {
                    "quality_assessment": {"version": True, "decision": "keep", "reasons": []},
                    "selection": {"version": 1, "decision": "keep", "reasons": []},
                },
            },
        )
        add(NEW, 0, str(source / "newer-unselected.ARW"), 99.0, "same-group", 1, "done", {})
    return {
        "database": database,
        "input": source,
        "other": other,
        "photo": photo,
        "paths": paths,
        "output": tmp_path / "report",
    }


def review(corpus, **kwargs):
    return build_score_review(
        input_root=corpus["input"],
        database_path=corpus["database"],
        output_root=corpus["output"],
        sample_count=18,
        job_id=A,
        no_previews=True,
        **kwargs,
    )


def test_pinned_no_preview_comparison_retains_all_rows_facts_and_scope(corpus, monkeypatch):
    before_database = corpus["database"].read_bytes()
    before_photo = corpus["photo"].read_bytes()
    monkeypatch.setattr(
        "material_agent.commands.score_review.decode_raw",
        lambda *args, **kwargs: pytest.fail("no decoder allowed"),
    )
    original_stat = Path.stat

    def stat(path, *args, **kwargs):
        if str(path).endswith(".ARW"):
            pytest.fail("no photo stat allowed")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    result = review(corpus, compare_job_id=B)
    assert result["schema"] == "material-agent-score-review-v3"
    assert [cohort["job"]["id"] for cohort in result["cohorts"]] == [A, B]
    assert (
        result["sample_count_rendered"] == 0
        and result["contact_sheet"] is None
        and result["samples"] == []
    )
    first, second = result["cohorts"]
    assert first["job"]["status"] == "finished_with_errors"
    assert first["job"]["summary"]["errors"] == 1
    assert first["config"]["future_setting"] == {"preserve": [1, 2]}
    assert first["historical_application_revision"]["status"] == "unknown"
    assert second["historical_application_revision"]["value"] == "saved-revision"
    assert first["distribution"]["row_count"] == second["distribution"]["row_count"] == 6
    assert first["distribution"]["finite_score_count"] == 3
    assert first["distribution"]["score_states"] == {
        "finite": 3,
        "invalid_type": 1,
        "missing": 1,
        "nonfinite": 1,
    }
    assert first["distribution"]["error_count"] == 1
    assert first["distribution"]["groups"]["size_histogram"] == {"1": 2, "4": 1}
    group = next(group for group in first["distribution"]["groups"]["items"] if group["group_id"])
    assert group["member_count"] == 4 and group["finite_score_count"] == 2
    assert group["duplicate_ranks"] == {"2": 2} and group["rank_above_member_count_count"] == 1
    assert first["distribution"]["ranks"]["above_group_size_count"] == 2
    facts = {fact["file_path"]: fact for fact in first["rows"]}
    shared = facts[corpus["paths"][0]]
    assert shared["quality_assessment"]["raw"]["decision"] == "reject"
    assert shared["selection"]["raw"]["decision"] == shared["legacy_decision"]["value"] == "keep"
    assert shared["selection"]["raw"]["role"] == "group_coverage"
    assert facts[corpus["paths"][1]]["score_total"] is None
    infinite = facts[corpus["paths"][2]]
    assert infinite["score"]["raw"] == {"invalid_number": "+Inf"}
    assert infinite["quality_assessment"]["status"] == "malformed"
    assert infinite["selection"]["status"] == "unsupported_version"
    assert infinite["quality_metric_diagnostics"]["status"] == "invalid_or_missing"
    assert infinite["model_evidence"]["_quality"]["signals"]["musiq"]["raw_score"] == {
        "invalid_number": "NaN"
    }
    assert facts[corpus["paths"][4]]["artifact_count"] == 2
    assert facts[corpus["paths"][4]]["payload_diagnostic"]["status"] == "duplicate_artifacts"
    assert facts[corpus["paths"][5]]["quality_assessment"]["status"] == "missing"
    assert facts[corpus["paths"][5]]["selection"]["raw"] is None
    comparison = result["comparison"]
    assert comparison["delta_direction"] == "compare_job_minus_job"
    assert comparison["finite_pair_count"] == 3
    pair = next(
        pair for pair in comparison["finite_pairs"] if pair["file_path"] == corpus["paths"][0]
    )
    assert pair["delta"] == -0.5
    assert comparison["exact_paths"]["a_only"] == [corpus["paths"][3]]
    assert comparison["exact_paths"]["b_only"] == [str(corpus["input"] / "case.ARW")]
    assert comparison["root_differences"]["different"] is True
    assert any(
        difference["path"] == "/preview/max_size" for difference in comparison["config_differences"]
    )
    encoded = json.dumps(result, allow_nan=False)
    assert (
        "secret-a" not in encoded and "secret-b" not in encoded and "summary-secret" not in encoded
    )
    assert NEW not in encoded and "newer-unselected" not in encoded
    assert corpus["database"].read_bytes() == before_database
    assert corpus["photo"].read_bytes() == before_photo
    assert set(path.name for path in corpus["output"].iterdir()) == {"review.json"}
    assert os.stat(corpus["output"]).st_mode & 0o777 == 0o700
    assert os.stat(corpus["output"] / "review.json").st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "kwargs",
    [
        {"job_id": None, "no_previews": True},
        {"job_id": None, "compare_job_id": B, "no_previews": True},
        {"job_id": A, "compare_job_id": B, "no_previews": False},
        {"job_id": A, "compare_job_id": A, "no_previews": True},
        {"job_id": "missing", "no_previews": True},
        {"job_id": OPEN, "no_previews": True},
        {"job_id": WRONG, "no_previews": True},
    ],
)
def test_no_latest_fallback_for_invalid_explicit_selection(corpus, kwargs):
    with pytest.raises(ValueError, match="job|comparison"):
        build_score_review(
            input_root=corpus["input"],
            database_path=corpus["database"],
            output_root=corpus["output"],
            sample_count=18,
            **kwargs,
        )
    assert not corpus["output"].exists()


def test_no_preview_does_not_require_any_source_directory_or_photo_to_exist(corpus, monkeypatch):
    corpus["photo"].unlink()
    corpus["input"].rmdir()
    monkeypatch.setattr(
        "material_agent.commands.score_review.decode_raw",
        lambda *a, **k: pytest.fail("no decoding"),
    )
    assert review(corpus)["cohorts"][0]["distribution"]["row_count"] == 6


@pytest.mark.parametrize("location", ["primary", "secondary", "parent", "symlink"])
def test_no_preview_output_protects_lexical_and_resolved_all_session_roots(corpus, location):
    if location == "primary":
        corpus["output"] = corpus["input"] / "report"
    elif location == "secondary":
        corpus["output"] = corpus["other"] / "report"
    elif location == "parent":
        corpus["output"] = corpus["input"].parent
    else:
        alias = corpus["input"].parent / "alias"
        alias.symlink_to(corpus["input"], target_is_directory=True)
        corpus["output"] = alias / "report"
    with pytest.raises(ValueError, match="outside and separate"):
        review(corpus, compare_job_id=B)


def test_duplicate_exact_paths_are_not_arbitrarily_paired(corpus):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "INSERT INTO job_files VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("b-extra", B, corpus["paths"][0], None, None, "done", None, None, 9.0, None, None),
        )
    result = review(corpus, compare_job_id=B)
    assert result["cohorts"][1]["distribution"]["row_count"] == 7
    assert result["comparison"]["ambiguous_pair_paths"] == [corpus["paths"][0]]
    assert result["comparison"]["finite_pair_count"] == 2


def test_transaction_binds_both_cohorts_before_concurrent_update(corpus, monkeypatch):
    with sqlite3.connect(corpus["database"]) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
    original_connect = sqlite3.connect
    traced, updated = [], []

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)

        def trace(sql):
            traced.append(sql)
            if "WHERE jf.job_id=" in sql and B in sql and not updated:
                updated.append(True)
                with original_connect(corpus["database"]) as writer:
                    writer.execute("UPDATE job_files SET score_total=99 WHERE id='b0'")

        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(audit.sqlite3, "connect", connect)
    result = review(corpus, compare_job_id=B)
    second = result["cohorts"][1]
    assert (
        next(fact for fact in second["rows"] if fact["job_file_id"] == "b0")["score_total"] == 7.5
    )
    assert sum(sql == "BEGIN" for sql in traced) == 1
    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE")) for sql in traced
    )


def test_nonfinite_delta_and_persisted_boolean_signal_remain_invalid(corpus):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE job_files SET score_total=? WHERE id='a0'", (-sys.float_info.max,)
        )
        connection.execute(
            "UPDATE job_files SET score_total=? WHERE id='b0'", (sys.float_info.max,)
        )
        connection.execute(
            "UPDATE artifacts SET metadata_json=? WHERE id='a0-art'",
            (
                json.dumps(
                    {
                        "meta": {
                            "_quality": {
                                "aggregate_score": 0,
                                "signals": {"musiq": {"raw_score": True, "normalized_score": "0"}},
                            }
                        }
                    }
                ),
            ),
        )
    result = review(corpus, compare_job_id=B)
    pair = next(
        pair
        for pair in result["comparison"]["finite_pairs"]
        if pair["file_path"] == corpus["paths"][0]
    )
    assert pair["delta"] is None and pair["delta_status"] == "nonfinite"
    diagnostic = next(fact for fact in result["cohorts"][0]["rows"] if fact["job_file_id"] == "a0")[
        "quality_metric_diagnostics"
    ]
    assert diagnostic["numbers"]["signals/musiq/raw_score"]["status"] == "invalid_type"
    json.dumps(result, allow_nan=False)


def test_cli_command_and_parser_pass_explicit_ids_and_no_previews(corpus, capsys):
    from material_agent.shells.cli.main import build_parser

    args = build_parser().parse_args(
        [
            "review-scores",
            "--input-dir",
            str(corpus["input"]),
            "--work-dir",
            str(corpus["database"].parent),
            "--output-dir",
            str(corpus["output"]),
            "--job-id",
            A,
            "--compare-job-id",
            B,
            "--no-previews",
        ]
    )
    assert args.job_id == A and args.compare_job_id == B and args.no_previews
    assert cmd_review_scores(args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["job_id"] == A and summary["samples"] == 0
    report = json.loads((corpus["output"] / "review.json").read_text())
    assert [cohort["job"]["id"] for cohort in report["cohorts"]] == [A, B]


def test_unrepresentable_historical_raw_score_is_an_explicit_invalid_number(corpus):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE artifacts SET metadata_json=? WHERE id='a0-art'",
            (
                json.dumps(
                    {
                        "meta": {
                            "_quality": {
                                "aggregate_score": 0,
                                "signals": {
                                    "musiq": {"raw_score": 10**1000, "normalized_score": 0}
                                },
                            }
                        }
                    }
                ),
            ),
        )
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    number = row["quality_metric_diagnostics"]["numbers"]["signals/musiq/raw_score"]
    assert number["status"] == "unrepresentable" and number["value"] is None
    assert number["raw"]["decimal"] == str(10**1000)
    assert row["payload_diagnostic"]["status"] == "invalid_numbers"
    assert audit.number_diagnostic(10**1000)["status"] == "unrepresentable"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "payload",
    [
        '{"meta":{"quality_assessment":{"version":2,"version":1,"decision":"keep","reasons":[]}}}',
        '{"decision":"reject","decision":"keep"}',
        '{"meta":{"selection":{"version":1,"decision":"reject","decision":"keep","role":"quality_policy","reasons":[]}}}',
    ],
)
def test_duplicate_payload_keys_are_ambiguous_not_current_fact_absence(corpus, payload):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute("UPDATE artifacts SET metadata_json=? WHERE id='a0-art'", (payload,))
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    assert row["payload_diagnostic"]["status"] == "ambiguous_duplicate_keys"
    assert row["quality_assessment"]["status"] == row["selection"]["status"] == "unresolved"
    assert row["legacy_decision"]["present"] is None
    assert row["legacy_decision"]["status"] == "unresolved"


@pytest.mark.parametrize(
    "payload", ["{malformed", '{"meta":null}', '{"meta":"broken"}', '{"meta":NaN}']
)
def test_malformed_parent_cannot_claim_quality_or_selection_fact_absence(corpus, payload):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute("UPDATE artifacts SET metadata_json=? WHERE id='a0-art'", (payload,))
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    assert row["quality_assessment"]["status"] == row["selection"]["status"] == "unresolved"
    assert row["quality_metric_diagnostics"]["status"] == "unresolved"


def test_duplicate_configuration_keys_cannot_be_reported_as_equal_valid_config(corpus):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE sessions SET config_snapshot=? WHERE id=?",
            ('{"preview":{"max_size":1024,"max_size":2048}}', "s-" + A),
        )
    result = review(corpus, compare_job_id=B)
    assert result["cohorts"][0]["config_diagnostic"]["status"] == "ambiguous_duplicate_keys"
    assert result["comparison"]["config_comparison_status"] == "unresolved"


def test_runtime_vector_is_not_serialized_into_diagnostic_facts(corpus):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE artifacts SET metadata_json=? WHERE id='a0-art'",
            (json.dumps({"meta": {"embedding": {"runtime": "openvino", "vector": [1, 2, 3]}}}),),
        )
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    assert row["model_evidence"]["embedding"] == {"runtime": "openvino"}


def test_invalid_sqlite_blob_score_and_group_do_not_break_strict_json(corpus):
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE job_files SET score_total=?,group_id=? WHERE id='a0'",
            (b"not numeric", b"not a group"),
        )
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    assert row["score"]["status"] == "invalid_type" and row["score_total"] is None
    assert row["group_status"] == "invalid_type"
    assert row["group_id"]["invalid_type"] == "bytes"
    json.dumps(result, allow_nan=False)


def test_explicit_single_job_with_previews_uses_its_full_cohort_and_recorded_config(
    corpus, monkeypatch
):
    calls = []

    def render(samples, **kwargs):
        calls.append((samples, kwargs))
        return "fixture-contact.jpg"

    monkeypatch.setattr("material_agent.commands.score_review._render_contact_sheet", render)
    result = build_score_review(
        input_root=corpus["input"],
        database_path=corpus["database"],
        output_root=corpus["output"],
        sample_count=6,
        job_id=A,
    )
    assert result["cohorts"][0]["job"]["id"] == A
    assert result["cohorts"][0]["distribution"]["row_count"] == 6
    assert calls and calls[0][1]["preview_config"] == {"max_size": 1024, "jpeg_quality": 85}
    assert len(calls[0][0]) == 3
    assert NEW not in json.dumps(result)


def test_actual_backend_meta_routing_preserves_quality_runtime_and_detection(corpus):
    from material_agent.domain.scoring_engine import _merge_backend_meta

    raw_backend = {
        "_quality": {
            "status": "model",
            "aggregate_score": 0.0,
            "aggregates": {"quality": 0.0},
            "signals": {
                "musiq": {
                    "raw_score": float("nan"),
                    "normalized_score": 0.0,
                    "raw_min": 0.0,
                    "raw_max": 100.0,
                    "weight": 1.0,
                }
            },
            "execution": {"status": "success", "runtime": "pyiqa"},
        },
        "_runtime": "cpu+pyiqa:cpu",
        "_runtime_components": ["cpu", "pyiqa:cpu"],
        "_configured_runtime": "cpu",
        "_model_stack": ["musiq"],
        "_scoring_mode": "hybrid",
        "_detection": {
            "status": "model",
            "runtime": "openvino",
            "execution_devices": ["CPU"],
            "model_name": "ssd",
            "model_digest": "frozen-model-digest",
        },
        "_semantic": {"status": "fallback"},
        "_face": {"status": "disabled"},
        "_aesthetic": {"runtime": "openvino"},
        "_embedding": {"runtime": "openvino", "vector": [1, 2]},
    }
    meta = {}
    _merge_backend_meta(meta, raw_backend)
    assert "quality" in meta and "_quality" not in meta
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE artifacts SET metadata_json=? WHERE id='a0-art'", (json.dumps({"meta": meta}),)
        )
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    evidence = row["model_evidence"]
    assert evidence["runtime"] == "cpu+pyiqa:cpu"
    assert evidence["runtime_components"] == ["cpu", "pyiqa:cpu"]
    assert evidence["configured_runtime"] == "cpu"
    assert evidence["model_stack"] == ["musiq"] and evidence["scoring_mode"] == "hybrid"
    assert evidence["detection"] == raw_backend["_detection"]
    assert (
        evidence["semantic"] == raw_backend["_semantic"]
        and evidence["face"] == raw_backend["_face"]
    )
    assert evidence["aesthetic"] == raw_backend["_aesthetic"]
    assert evidence["embedding"] == {"runtime": "openvino"}
    assert evidence["quality"]["signals"]["musiq"]["raw_score"] == {"invalid_number": "NaN"}
    diagnostics = row["quality_metric_diagnostics"]
    assert diagnostics["source_key"] == "quality" and diagnostics["alias_status"] == "actual_only"
    assert diagnostics["status"] == "invalid_or_missing"
    assert diagnostics["numbers"]["signals/musiq/raw_score"]["status"] == "nonfinite"
    assert diagnostics["numbers"]["signals/musiq/weight"]["value"] == 1.0
    json.dumps(result, allow_nan=False)


def test_conflicting_actual_and_legacy_aliases_are_preserved_and_ambiguous(corpus):
    actual = {
        "status": "model",
        "aggregate_score": 8.0,
        "signals": {"musiq": {"raw_score": 80.0, "normalized_score": 8.0}},
    }
    legacy = {
        "status": "model",
        "aggregate_score": 0.0,
        "signals": {"musiq": {"raw_score": float("nan"), "normalized_score": 0.0}},
    }
    with sqlite3.connect(corpus["database"]) as connection:
        connection.execute(
            "UPDATE artifacts SET metadata_json=? WHERE id='a0-art'",
            (
                json.dumps(
                    {
                        "meta": {
                            "quality": actual,
                            "_quality": legacy,
                            "runtime": "cpu-current",
                            "_runtime": "legacy-runtime",
                            "detection": {"runtime": "openvino"},
                            "_detection": {"runtime": "legacy"},
                        }
                    }
                ),
            ),
        )
    result = review(corpus)
    row = next(row for row in result["cohorts"][0]["rows"] if row["job_file_id"] == "a0")
    evidence = row["model_evidence"]
    assert evidence["quality"] == actual
    assert evidence["_quality"]["signals"]["musiq"]["raw_score"] == {"invalid_number": "NaN"}
    assert evidence["runtime"] == "cpu-current" and evidence["_runtime"] == "legacy-runtime"
    assert evidence["detection"] != evidence["_detection"]
    diagnostic = row["quality_metric_diagnostics"]
    assert diagnostic["status"] == "ambiguous_aliases" and diagnostic["source_key"] is None
    assert diagnostic["numbers"] == {}
    assert diagnostic["alias_diagnostics"]["quality"]["status"] == "finite"
    assert diagnostic["alias_diagnostics"]["_quality"]["status"] == "invalid_or_missing"


def test_quality_actual_key_is_preferred_only_when_aliases_match_and_legacy_can_fallback():
    value = {
        "aggregate_score": 8.0,
        "signals": {"musiq": {"raw_score": 80.0, "normalized_score": 8.0}},
    }
    actual = audit.quality_metric_diagnostics({"quality": value, "_quality": value})
    assert actual["source_key"] == "quality" and actual["alias_status"] == "matching"
    legacy = audit.quality_metric_diagnostics({"_quality": value})
    assert legacy["source_key"] == "_quality" and legacy["alias_status"] == "legacy_fallback"
    assert audit.quality_metric_diagnostics({"quality": None})["status"] == "malformed"
    assert (
        audit.quality_metric_diagnostics({"quality": None, "_quality": value})["status"]
        == "ambiguous_aliases"
    )
