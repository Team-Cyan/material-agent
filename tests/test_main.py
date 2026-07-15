"""Regression tests for CLI command handlers in material_agent/main.py."""

import copy
import os
import sqlite3
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from material_agent.app.dto import JobStage, JobStatus
from material_agent.commands.scoring import (
    build_score_cache_key,
    load_config,
    load_raw_config,
)
from material_agent.main import cmd_fix_db, cmd_rescore, cmd_scan_scenes, cmd_remap_scenes
from material_agent.utils.constants import SCENE_LIST
from material_agent.utils.runtime_paths import build_runtime_paths
from material_agent.utils.state import State


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(d: str) -> str:
    """Create a minimal runtime DB in the hidden workdir and return its path."""
    db_path = build_runtime_paths(d).db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                scene TEXT,
                scene_raw TEXT,
                total_score REAL,
                star_rating INTEGER,
                group_rank INTEGER,
                group_size INTEGER,
                score_composition REAL,
                score_color REAL,
                score_subject REAL,
                score_lighting REAL,
                score_clarity REAL,
                score_depth REAL,
                score_mood REAL,
                score_exposure REAL,
                score_sharpness REAL,
                overexpose_ratio REAL,
                underexpose_ratio REAL,
                laplacian_variance REAL,
                commentary_group_issues TEXT,
                commentary_shooting TEXT,
                commentary_post TEXT,
                group_boosted INTEGER,
                group_id TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT
            );
        """)
        conn.commit()
    return str(db_path)


def _run_args(input_dir: str | Path, *, allow_empty: bool = False) -> Namespace:
    return Namespace(
        input_dir=str(input_dir),
        config="config.yaml",
        reprocess=False,
        dry_run=False,
        allow_empty=allow_empty,
        scorers=None,
        no_visual_merge=False,
    )


def _legacy_backend_config(backend: str) -> dict:
    """Build an explicit compatibility config without changing repo defaults."""

    config = load_config("config.yaml")
    config["backend"] = backend
    config["legacy"]["enabled"] = True
    config["omlx"] = {
        "base_url": "http://127.0.0.1:11435",
        "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
        "timeout": 120,
        "runtime": {
            "probe_on_run": True,
            "enforce_dedicated_instance": False,
        },
    }
    config["ollama"] = {
        "base_url": "http://127.0.0.1:11434",
        "vision_model": "llava:7b",
        "commentary_model": "llama3.2:3b",
        "timeout": 120,
    }
    return config


def _mock_finished_job(monkeypatch, status: str = "finished") -> None:
    monkeypatch.setattr(
        "material_agent.adapters.state.sqlite_runtime.SQLiteRuntimeRepository.get_job_result",
        lambda *_args: {"status": status, "summary": {}},
    )


# ---------------------------------------------------------------------------
# cmd_scan_scenes
# ---------------------------------------------------------------------------


def test_scan_scenes_missing_db(capsys):
    with tempfile.TemporaryDirectory() as d:
        args = Namespace(dir=d)
        result = cmd_scan_scenes(args)
        out = capsys.readouterr().out
        assert "Error" in out
        assert "no database" in out
        assert result == 1


def test_scan_scenes_shows_distribution(capsys):
    with tempfile.TemporaryDirectory() as d:
        db_path = _make_db(d)
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT INTO processed (file_path, status, scene, scene_raw) VALUES (?,?,?,?)",
                [
                    ("/a.arw", "done", "people", "舞台上的主唱特写"),
                    ("/b.arw", "done", "people", "全身人像"),
                    ("/c.arw", "done", "landscape", "山间日落"),
                ],
            )
            conn.commit()

        args = Namespace(dir=d)
        cmd_scan_scenes(args)
        out = capsys.readouterr().out
        assert "people" in out
        assert "landscape" in out
        assert "2" in out  # portrait has 2 photos


def test_repo_default_screening_thresholds_are_low_for_poor_photo_sets():
    cfg = load_config("config.yaml")
    assert cfg["screening"]["tier1_threshold"] == 0.5
    assert cfg["screening"]["tier2_threshold"] == 0.25


def test_repo_default_backend_uses_local_openvino_profile():
    cfg = load_config("config.yaml")
    assert cfg["backend"] == "local"
    assert cfg["commentary_enabled"] is False
    assert cfg["inference"]["runtime"] == "openvino"
    assert cfg["inference"]["device"] == "CPU"
    assert cfg["inference"]["fallback_device"] == "CPU"
    assert cfg["inference"]["provider_tags"] == ["intel-openvino", "cpu"]
    assert cfg["inference"]["enforce_available"] is False
    assert "omlx" not in cfg
    assert "ollama" not in cfg


def test_repo_default_local_settings_are_normalized():
    cfg = load_config("config.yaml")
    assert "max_concurrent" not in cfg["local"]
    assert cfg["inference"]["model_cache_dir"] == "~/.material-agent/models"
    assert cfg["review_pipeline"]["score_prefetch_window"] == 2


@pytest.mark.parametrize("content", ["", "- one\n- two\n"])
def test_load_raw_config_rejects_non_mapping_documents(tmp_path, content):
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="top-level mapping"):
        load_raw_config(str(config_path))


def test_cmd_run_rejects_missing_input_before_any_runtime_write(tmp_path, monkeypatch):
    from material_agent.commands.scoring import cmd_run

    input_dir = tmp_path / "missing"
    monkeypatch.setattr(
        "material_agent.commands.scoring._check_exiftool_version",
        lambda: pytest.fail("ExifTool must not run for invalid input"),
    )

    with pytest.raises(ValueError, match="does not exist"):
        cmd_run(_run_args(input_dir), load_config("config.yaml"))

    assert not (input_dir / ".material-agent").exists()


def test_cmd_run_rejects_file_input_before_any_runtime_write(tmp_path, monkeypatch):
    from material_agent.commands.scoring import cmd_run

    input_path = tmp_path / "photo.ARW"
    input_path.write_bytes(b"not-a-directory")
    monkeypatch.setattr(
        "material_agent.commands.scoring._check_exiftool_version",
        lambda: pytest.fail("ExifTool must not run for invalid input"),
    )

    with pytest.raises(ValueError, match="not a directory"):
        cmd_run(_run_args(input_path), load_config("config.yaml"))

    assert not (tmp_path / ".material-agent").exists()


def test_cmd_run_rejects_unreadable_input_before_any_runtime_write(tmp_path, monkeypatch):
    from material_agent.commands.scoring import cmd_run

    monkeypatch.setattr("material_agent.commands.scoring.os.access", lambda *_args: False)
    monkeypatch.setattr(
        "material_agent.commands.scoring._check_exiftool_version",
        lambda: pytest.fail("ExifTool must not run for invalid input"),
    )

    with pytest.raises(ValueError, match="not readable"):
        cmd_run(_run_args(tmp_path), load_config("config.yaml"))

    assert not (tmp_path / ".material-agent").exists()


def test_cmd_run_rejects_empty_discovery_before_any_runtime_write(tmp_path, monkeypatch):
    from material_agent.commands.scoring import cmd_run

    monkeypatch.setattr(
        "material_agent.commands.scoring._check_exiftool_version",
        lambda: pytest.fail("ExifTool must not run for empty input"),
    )

    with pytest.raises(ValueError, match="--allow-empty"):
        cmd_run(_run_args(tmp_path), load_config("config.yaml"))

    assert not (tmp_path / ".material-agent").exists()


def test_score_cache_key_tracks_score_grouping_and_terminal_output_inputs():
    config = load_config("config.yaml")
    baseline = build_score_cache_key(config)

    operational_only = copy.deepcopy(config)
    operational_only["log_level"] = "debug"
    operational_only["review_pipeline"]["score_prefetch_window"] = 1
    assert build_score_cache_key(operational_only) == baseline

    scoring_change = copy.deepcopy(config)
    scoring_change["scorers"]["exposure"]["weight"] += 0.01
    assert build_score_cache_key(scoring_change) != baseline

    scene_change = copy.deepcopy(config)
    scene_change["scene_weights"]["default"]["composition"] += 0.01
    assert build_score_cache_key(scene_change) != baseline

    grouping_change = copy.deepcopy(config)
    grouping_change["grouping"]["time_gap_seconds"] += 1
    assert build_score_cache_key(grouping_change) != baseline

    output_change = copy.deepcopy(config)
    output_change["commentary_enabled"] = not config["commentary_enabled"]
    assert build_score_cache_key(output_change) != baseline


def test_score_cache_key_redacts_credentials_before_hashing():
    config = load_config("config.yaml")
    config["legacy"]["enabled"] = True
    config["backend"] = "omlx"
    config["omlx"] = {"api_key": "first-secret", "full_vision_model": "fixture"}
    baseline = build_score_cache_key(config)

    config["omlx"]["api_key"] = "rotated-secret"

    assert build_score_cache_key(config) == baseline


def test_score_cache_key_tracks_pipeline_revision(monkeypatch):
    config = load_config("config.yaml")
    baseline = build_score_cache_key(config)

    monkeypatch.setattr(
        "material_agent.commands.scoring._SCORE_PIPELINE_CACHE_REVISION",
        "material-agent.score-output.next",
    )

    assert build_score_cache_key(config) != baseline


def test_cmd_run_rejects_missing_raw_omlx_config():
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        args = Namespace(
            input_dir=d,
            config="config.yaml",
            reprocess=False,
            dry_run=True,
            scorers=None,
            no_visual_merge=False,
        )
        raw_cfg = {
            "backend": "omlx",
            "scorers": {},
            "grouping": {},
            "preview": {},
            "scoring": {},
        }

        with pytest.raises(SystemExit):
            cmd_run(args, raw_cfg)


def test_repo_default_screening_backend_uses_musiq():
    cfg = load_config("config.yaml")
    assert cfg["screening"]["backend"] == "musiq"
    assert cfg["screening"]["musiq"]["metric"] == "musiq"


def test_repo_default_inference_uses_cpu_fallback():
    cfg = load_config("config.yaml")
    assert cfg["inference"]["fallback_device"] == "CPU"


def test_repo_default_output_language_is_zh():
    cfg = load_config("config.yaml")
    assert cfg["output_language"] == "zh"


def test_cli_shell_builds_parser_for_run_command():
    from material_agent.shells.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["run", "/tmp/photos"])

    assert args.command == "run"
    assert args.input_dir == "/tmp/photos"


def test_cli_shell_owns_run_parser_flags():
    from material_agent.shells.cli.main import build_parser

    parser = build_parser()
    subparsers_action = next(
        action for action in parser._actions if getattr(action, "dest", None) == "command"
    )
    run_parser = subparsers_action.choices["run"]
    help_text = run_parser.format_help()

    assert "--dry-run" in help_text
    assert "--allow-empty" in help_text
    assert "--no-visual-merge" in help_text


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--conf", "config.yaml", "/tmp/photos"],
        ["run", "--scor", "exposure", "/tmp/photos"],
    ],
)
def test_cli_shell_rejects_abbreviated_run_options(argv):
    from material_agent.shells.cli.main import build_parser

    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(argv)

    assert exc_info.value.code == 2


def test_cli_shell_excludes_legacy_omlx_commands():
    from material_agent.shells.cli.main import build_parser

    parser = build_parser()
    subparsers_action = next(
        action for action in parser._actions if getattr(action, "dest", None) == "command"
    )
    commands = set(subparsers_action.choices)

    assert {"run", "scan-scenes", "rescore", "rewrite-commentary"}.issubset(commands)
    assert {
        "omlx-setup",
        "omlx-start",
        "omlx-status",
        "omlx-benchmark",
        "omlx-harness",
    }.isdisjoint(commands)


def test_cli_shell_builds_parser_for_rewrite_commentary():
    from material_agent.shells.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "rewrite-commentary",
            "--dir",
            "/tmp/photos",
            "--config",
            "config.yaml",
            "--rewrite-xmp",
            "--dry-run",
        ]
    )

    assert args.command == "rewrite-commentary"
    assert args.dir == "/tmp/photos"
    assert args.config == "config.yaml"
    assert args.rewrite_xmp is True
    assert args.dry_run is True


def test_cli_shell_builds_parser_for_reset_ai():
    from material_agent.shells.cli.main import build_parser

    parser = build_parser()
    default_args = parser.parse_args(
        [
            "reset-ai",
            "--dir",
            "/tmp/photos",
            "--dry-run",
        ]
    )
    clear_args = parser.parse_args(
        ["reset-ai", "--dir", "/tmp/photos", "--clear-xmp"]
    )
    compatibility_args = parser.parse_args(
        ["reset-ai", "--dir", "/tmp/photos", "--keep-xmp"]
    )

    assert default_args.command == "reset-ai"
    assert default_args.dir == "/tmp/photos"
    assert default_args.dry_run is True
    assert default_args.clear_xmp is False
    assert clear_args.clear_xmp is True
    assert compatibility_args.clear_xmp is False


def test_legacy_main_delegates_to_cli_shell(monkeypatch):
    from material_agent import main as legacy_main

    called = {}

    def fake_cli_main():
        called["yes"] = True

    monkeypatch.setattr(legacy_main, "cli_main", fake_cli_main)
    legacy_main.main()

    assert called == {"yes": True}


def test_legacy_main_exports_rewrite_commentary_wrapper(monkeypatch):
    from material_agent import main as legacy_main

    called = {}

    def fake_cmd_rewrite_commentary(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs

    monkeypatch.setattr(
        "material_agent.commands.io.cmd_rewrite_commentary",
        fake_cmd_rewrite_commentary,
    )

    legacy_main.cmd_rewrite_commentary("sentinel", rewrite_xmp=True)

    assert called["args"] == ("sentinel",)
    assert called["kwargs"] == {"rewrite_xmp": True}


def test_cli_main_rejects_legacy_omlx_management_commands(monkeypatch):
    import importlib

    cli_main = importlib.import_module("material_agent.shells.cli.main")

    def forbidden_load_config(_path):
        raise AssertionError("legacy OMLX management commands must fail before config loading")

    monkeypatch.setattr(cli_main, "load_raw_config", forbidden_load_config)
    monkeypatch.setattr(cli_main, "load_config", forbidden_load_config)

    for command in ("omlx-setup", "omlx-start", "omlx-status", "omlx-harness"):
        monkeypatch.setattr(sys, "argv", ["material-agent", command])
        with pytest.raises(SystemExit):
            cli_main.main()


def test_cli_main_run_passes_raw_config_to_cmd_run(monkeypatch):
    import importlib

    cli_main = importlib.import_module("material_agent.shells.cli.main")

    raw_config = {
        "backend": "omlx",
        "scorers": {},
        "grouping": {},
        "preview": {},
        "scoring": {},
    }
    captured = {}

    monkeypatch.setattr(cli_main, "load_raw_config", lambda _path: raw_config)

    def forbidden_load_config(_path):
        raise AssertionError("run entry must not call load_config()")

    monkeypatch.setattr(cli_main, "load_config", forbidden_load_config)

    def fake_cmd_run(args, config):
        captured["args"] = args
        captured["config"] = config

    monkeypatch.setattr(cli_main, "cmd_run", fake_cmd_run)
    monkeypatch.setattr(
        sys, "argv", ["material-agent", "run", "/tmp/photos", "--config", "config.yaml"]
    )

    cli_main.main()

    assert captured["args"].input_dir == "/tmp/photos"
    assert captured["config"] is raw_config
    assert "omlx" not in captured["config"]


def test_cli_main_returns_delegated_command_exit_code(monkeypatch):
    import importlib

    cli_main = importlib.import_module("material_agent.shells.cli.main")
    monkeypatch.setattr(cli_main, "cmd_scan_scenes", lambda _args: 7)
    monkeypatch.setattr(
        sys,
        "argv",
        ["material-agent", "scan-scenes", "--dir", "/tmp/photos"],
    )

    assert cli_main.main() == 7


def test_cli_main_returns_130_for_sigterm_cancellation(monkeypatch, capsys):
    import importlib

    from material_agent.app.errors import RunCancelled

    cli_main = importlib.import_module("material_agent.shells.cli.main")
    monkeypatch.setattr(cli_main, "load_raw_config", lambda _path: {})
    monkeypatch.setattr(
        cli_main,
        "cmd_run",
        lambda _args, _config: (_ for _ in ()).throw(RunCancelled("received SIGTERM")),
    )
    monkeypatch.setattr(sys, "argv", ["material-agent", "run", "/tmp/photos"])

    assert cli_main.main() == 130
    assert "Run cancelled: received SIGTERM" in capsys.readouterr().err


def test_cli_main_routes_rewrite_commentary(monkeypatch):
    import importlib

    cli_main = importlib.import_module("material_agent.shells.cli.main")

    called = {}

    def fake_cmd_rewrite_commentary(args):
        called["args"] = args

    monkeypatch.setattr(cli_main, "cmd_rewrite_commentary", fake_cmd_rewrite_commentary)
    monkeypatch.setattr(
        sys,
        "argv",
        ["material-agent", "rewrite-commentary", "--dir", "/tmp/photos", "--rewrite-xmp"],
    )

    cli_main.main()

    assert called["args"].dir == "/tmp/photos"
    assert called["args"].rewrite_xmp is True


def test_cmd_rewrite_commentary_returns_nonzero_for_xmp_errors(
    tmp_path, monkeypatch, capsys
):
    from material_agent.commands.io import cmd_rewrite_commentary

    _make_db(str(tmp_path))

    class _FailingRewriteService:
        def run(self, *_args, **_kwargs):
            return {
                "done_rows": 2,
                "updated": 2,
                "rewritten_xmp": 1,
                "xmp_errors": 1,
            }

    monkeypatch.setattr(
        "material_agent.commands.io.RewriteCommentaryService",
        lambda: _FailingRewriteService(),
    )
    monkeypatch.setattr("material_agent.commands.io.load_config", lambda _path: {})
    args = Namespace(
        dir=str(tmp_path),
        config="config.yaml",
        dry_run=False,
        rewrite_xmp=True,
    )

    assert cmd_rewrite_commentary(args) == 1
    assert "1 errors" in capsys.readouterr().out


def test_cli_main_routes_reset_ai(monkeypatch):
    import importlib

    cli_main = importlib.import_module("material_agent.shells.cli.main")

    called = {}

    def fake_cmd_reset_ai(args):
        called["args"] = args

    monkeypatch.setattr(cli_main, "cmd_reset_ai", fake_cmd_reset_ai)
    monkeypatch.setattr(
        sys,
        "argv",
        ["material-agent", "reset-ai", "--dir", "/tmp/photos", "--clear-xmp"],
    )

    cli_main.main()

    assert called["args"].dir == "/tmp/photos"
    assert called["args"].clear_xmp is True


def test_cli_main_import_does_not_eagerly_import_scoring_stack():
    import importlib

    module_names = (
        "material_agent.shells.cli.main",
        "material_agent.commands.scoring",
        "material_agent.app.review_runtime",
        "material_agent.domain.scoring_engine",
    )
    previous_modules = {name: sys.modules.get(name) for name in module_names}
    try:
        for module_name in module_names:
            sys.modules.pop(module_name, None)

        importlib.import_module("material_agent.shells.cli.main")

        assert "material_agent.commands.scoring" not in sys.modules
        assert "material_agent.app.review_runtime" not in sys.modules
        assert "material_agent.domain.scoring_engine" not in sys.modules
    finally:
        for module_name in module_names:
            sys.modules.pop(module_name, None)
            previous = previous_modules[module_name]
            if previous is not None:
                sys.modules[module_name] = previous


def test_cmd_run_creates_runtime_session_and_job(monkeypatch):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = load_config("config.yaml")
        args = Namespace(
            input_dir=d,
            config="config.yaml",
            reprocess=False,
            dry_run=False,
            allow_empty=True,
            scorers=None,
            no_visual_merge=False,
        )

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        monkeypatch.setattr(
            "material_agent.commands.scoring._sync_shared_omlx_models_if_needed",
            lambda _config: None,
        )
        monkeypatch.setattr(
            "material_agent.app.review_service.scan_arw_files", lambda *_args, **_kwargs: []
        )

        class _FakeExecutor:
            def run(self, job_id, file_paths):
                return {"status": JobStatus.FINISHED.value}

        monkeypatch.setattr(
            "material_agent.commands.scoring._build_review_job_executor",
            lambda *args, **kwargs: _FakeExecutor(),
        )

        result = cmd_run(args, cfg)

        db_path = build_runtime_paths(d).db_path
        with sqlite3.connect(db_path) as conn:
            job_row = conn.execute(
                "SELECT stage, status FROM jobs ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
            session_row = conn.execute(
                "SELECT kind, status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
            runtime_probe = conn.execute(
                "SELECT metadata_json FROM artifacts WHERE kind='runtime_probe' ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()

        assert session_row[:2] == ("cli", "finished")
        assert session_row[2] is not None
        assert job_row == (JobStage.DISCOVER.value, JobStatus.QUEUED.value)
        assert runtime_probe is None
        assert result == 0


def test_cmd_run_delegates_runtime_start_to_review_run_service(monkeypatch):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = load_config("config.yaml")
        args = Namespace(
            input_dir=d,
            config="config.yaml",
            reprocess=False,
            dry_run=False,
            allow_empty=True,
            scorers=None,
            no_visual_merge=False,
        )
        called = {}

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        monkeypatch.setattr(
            "material_agent.adapters.models.omlx.instance.is_configured_shared_omlx_runtime",
            lambda _config: True,
        )
        monkeypatch.setattr(
            "material_agent.commands.scoring._sync_shared_omlx_models_if_needed",
            lambda _config: None,
        )

        class _FakeReviewRunService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                return "job-123"

        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        monkeypatch.setattr(
            "material_agent.adapters.state.sqlite_runtime.SQLiteRuntimeRepository.get_job_result",
            lambda *_args: {"status": "finished", "summary": {}},
        )

        result = cmd_run(args, cfg)

        assert called["kwargs"]["input_dir"] == d
        assert called["kwargs"]["config"]["input_dir"] == d
        assert called["kwargs"]["dry_run"] is False
        assert result == 0


def test_cmd_run_returns_nonzero_for_partial_errors_and_passes_score_cache_key(
    tmp_path,
    monkeypatch,
):
    from material_agent.commands.scoring import cmd_run

    photo = tmp_path / "one.ARW"
    photo.write_bytes(b"fake")
    config = load_config("config.yaml")
    expected_cache_key = build_score_cache_key(config)
    captured = {}

    class _FakeProcessedRepository:
        def __init__(self, input_dir, *, reprocess, score_cache_key):
            captured["processed_input"] = input_dir
            captured["reprocess"] = reprocess
            captured["score_cache_key"] = score_cache_key

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class _FakeReviewRunService:
        def __init__(self, repository):
            captured["runtime_repository"] = repository

        def run(self, **kwargs):
            captured["file_paths"] = kwargs["file_paths"]
            return "job-with-errors"

    monkeypatch.setattr(
        "material_agent.commands.scoring._check_exiftool_version", lambda: None
    )
    monkeypatch.setattr(
        "material_agent.commands.scoring._sync_shared_omlx_models_if_needed",
        lambda _config: None,
    )
    monkeypatch.setattr(
        "material_agent.commands.scoring.SQLiteProcessedRepository",
        _FakeProcessedRepository,
    )
    monkeypatch.setattr(
        "material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService
    )
    monkeypatch.setattr(
        "material_agent.adapters.state.sqlite_runtime.SQLiteRuntimeRepository.get_job_result",
        lambda *_args: {"status": "finished_with_errors", "summary": {"error_files": 1}},
    )

    result = cmd_run(_run_args(tmp_path), config)

    assert result == 1
    assert captured["file_paths"] == [str(photo)]
    assert captured["score_cache_key"] == expected_cache_key


def test_review_runtime_marks_done_with_commentary_in_single_write(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    with tempfile.TemporaryDirectory() as d:
        cfg = load_config("config.yaml")
        cfg["input_dir"] = d
        cfg["commentary_enabled"] = True
        state = MagicMock()
        state.is_done.return_value = False
        state.is_scored.return_value = False
        progress = MagicMock()
        repo = MagicMock()
        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")

        class _Bundle:
            total = 5.5
            scores = {"exposure": 6.0, "sharpness": 5.0}
            meta = {}
            scene = "people"
            scene_raw = "舞台上的人物"
            instructions = "exp:6.0 sharp:5.0"
            decision = "keep"
            decision_reasons = ["best in burst"]
            screening_prior = 5.0
            visible_breakdown = {}
            policy_version = "layered-v1"
            signals = []

        async def fake_compute_scores(*_args, **_kwargs):
            return _Bundle()

        class _Commentary:
            def __init__(self, *args, **kwargs):
                pass

            async def for_group(self, group_summary, score_details=None):
                return "【组内问题】整体偏暗。\n【拍摄建议】拍摄时补一点面光。"

            async def for_photo(self, score_line, group_commentary, scores=None, **kwargs):
                return "【后期指导】后期把阴影提一点。"

        fake_writer = MagicMock()
        fake_writer.score_to_stars.return_value = 3
        fake_writer.build_subject_tags.return_value = ["pj:score=5.5"]

        monkeypatch.setattr("material_agent.app.review_runtime.make_client", lambda config: object())
        monkeypatch.setattr("material_agent.app.review_runtime.decode_raw", lambda file_path, preview: object())
        monkeypatch.setattr("material_agent.app.review_runtime.compute_scores", fake_compute_scores)
        monkeypatch.setattr("material_agent.app.review_runtime.CommentaryGenerator", _Commentary)
        monkeypatch.setattr("material_agent.app.review_runtime.ExifToolXMPWriter", lambda *_args, **_kwargs: fake_writer)

        executor = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=progress,
            dry_run=False,
        )
        executor.run("job-123", [str(arw)])

        assert state.mark_done.call_count == 1
        kwargs = state.mark_done.call_args.kwargs
        assert kwargs["commentary_group_issues"] == "【组内问题】整体偏暗。"
        assert kwargs["commentary_shooting"] == "【拍摄建议】拍摄时补一点面光。"
        assert kwargs["commentary_post"] == "【后期指导】后期把阴影提一点。"
        state.update_commentary.assert_not_called()


def test_cmd_run_restarts_shared_omlx_models_for_local_desktop_runtime(monkeypatch, capsys):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = _legacy_backend_config("omlx")
        cfg["omlx"]["runtime"]["enforce_dedicated_instance"] = False
        args = _run_args(d, allow_empty=True)
        called = {}

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        monkeypatch.setattr(
            "material_agent.adapters.models.omlx.instance.is_configured_shared_omlx_runtime",
            lambda _config: True,
        )

        class _FakeService:
            def sync_shared(self, config):
                called["synced_config"] = config
                return {
                    "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
                    "inactive_models": ["gemma-4-e2b-it-4bit"],
                    "changed": True,
                }

            def status(self, config):
                called["status_config"] = config
                return {"reachable": True}

            def restart_shared(self, config):
                called["restarted_config"] = config
                return {
                    "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
                    "inactive_models": ["gemma-4-e2b-it-4bit"],
                    "changed": True,
                }

        class _FakeReviewRunService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                return "job-123"

        monkeypatch.setattr(
            "material_agent.app.omlx_instance_service.OMLXInstanceService",
            lambda: _FakeService(),
        )
        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        _mock_finished_job(monkeypatch)

        result = cmd_run(args, cfg)
        out = capsys.readouterr().out

        assert called["synced_config"]["backend"] == "omlx"
        assert called["status_config"]["backend"] == "omlx"
        assert called["restarted_config"]["backend"] == "omlx"
        assert result == 0
        assert "Restarted shared oMLX runtime with active models: Qwen3-VL-4B-Instruct-4bit" in out
        assert "Inactive shared desktop models remain installed but unpinned: gemma-4-e2b-it-4bit" in out


def test_cmd_run_skips_shared_omlx_sync_for_dedicated_runtime(monkeypatch):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = _legacy_backend_config("omlx")
        cfg["omlx"]["runtime"]["enforce_dedicated_instance"] = True
        args = _run_args(d, allow_empty=True)

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        class _FakeService:
            def sync_shared(self, config):
                raise AssertionError("shared desktop sync should be skipped for dedicated runtime mode")

        class _FakeReviewRunService:
            def __init__(self, repository):
                self.repository = repository

            def run(self, **kwargs):
                return "job-123"

        monkeypatch.setattr(
            "material_agent.app.omlx_instance_service.OMLXInstanceService",
            lambda: _FakeService(),
        )
        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        _mock_finished_job(monkeypatch)

        assert cmd_run(args, cfg) == 0


def test_cmd_run_starts_shared_omlx_when_desktop_runtime_is_unreachable(monkeypatch, capsys):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = _legacy_backend_config("omlx")
        cfg["omlx"]["runtime"]["enforce_dedicated_instance"] = False
        args = _run_args(d, allow_empty=True)
        called = {}

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        monkeypatch.setattr(
            "material_agent.adapters.models.omlx.instance.is_configured_shared_omlx_runtime",
            lambda _config: True,
        )

        class _FakeService:
            def sync_shared(self, config):
                called["synced_config"] = config
                return {
                    "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
                    "inactive_models": [],
                    "changed": False,
                }

            def status(self, config):
                called["status_config"] = config
                return {"reachable": False}

            def restart_shared(self, config):
                called["restarted_config"] = config
                return {
                    "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
                    "inactive_models": [],
                    "changed": False,
                }

        class _FakeReviewRunService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                return "job-123"

        monkeypatch.setattr(
            "material_agent.app.omlx_instance_service.OMLXInstanceService",
            lambda: _FakeService(),
        )
        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        _mock_finished_job(monkeypatch)

        result = cmd_run(args, cfg)
        out = capsys.readouterr().out

        assert called["synced_config"]["backend"] == "omlx"
        assert called["status_config"]["backend"] == "omlx"
        assert called["restarted_config"]["backend"] == "omlx"
        assert result == 0
        assert "Restarted shared oMLX runtime with active models: Qwen3-VL-4B-Instruct-4bit" in out


def test_cmd_run_skips_shared_omlx_sync_for_non_desktop_local_runtime(monkeypatch):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = _legacy_backend_config("omlx")
        cfg["omlx"]["base_url"] = "http://127.0.0.1:22445"
        args = _run_args(d, allow_empty=True)

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        monkeypatch.setattr(
            "material_agent.adapters.models.omlx.instance.is_configured_shared_omlx_runtime",
            lambda _config: False,
        )

        class _FakeService:
            def sync_shared(self, config):
                raise AssertionError("shared desktop sync should be skipped for non-desktop local runtime configs")

        class _FakeReviewRunService:
            def __init__(self, repository):
                self.repository = repository

            def run(self, **kwargs):
                return "job-123"

        monkeypatch.setattr(
            "material_agent.app.omlx_instance_service.OMLXInstanceService",
            lambda: _FakeService(),
        )
        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        _mock_finished_job(monkeypatch)

        assert cmd_run(args, cfg) == 0


@pytest.mark.parametrize(
    ("backend", "probe_on_run", "expects_hook"),
    [
        ("omlx", True, True),
        ("omlx", False, False),
        ("ollama", True, False),
    ],
)
def test_cmd_run_only_builds_runtime_probe_hook_for_enabled_omlx_backend(
    monkeypatch,
    backend,
    probe_on_run,
    expects_hook,
):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        cfg = _legacy_backend_config(backend)
        cfg["omlx"]["runtime"]["probe_on_run"] = probe_on_run
        args = _run_args(d, allow_empty=True)
        called = {}

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)
        monkeypatch.setattr(
            "material_agent.commands.scoring._sync_shared_omlx_models_if_needed",
            lambda _config: None,
        )

        class _FakeReviewRunService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                return "job-123"

        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        _mock_finished_job(monkeypatch)

        result = cmd_run(args, cfg)

        assert ("preflight_hook" in called["kwargs"]) is True
        assert callable(called["kwargs"]["preflight_hook"]) is expects_hook
        assert called["kwargs"]["input_dir"] == d
        assert result == 0


def test_cmd_run_with_local_backend_uses_local_preflight(monkeypatch):
    from material_agent.commands.scoring import cmd_run

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "one.ARW").write_bytes(b"fake")
        cfg = load_config("config.yaml")
        args = Namespace(
            input_dir=d,
            config="config.yaml",
            reprocess=False,
            dry_run=False,
            scorers=None,
            no_visual_merge=False,
        )
        called = {}

        monkeypatch.setattr("material_agent.commands.scoring._check_exiftool_version", lambda: None)

        class _FakeReviewRunService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                assert callable(kwargs["preflight_hook"])
                return "job-123"

        monkeypatch.setattr("material_agent.commands.scoring.ReviewRunService", _FakeReviewRunService)
        monkeypatch.setattr(
            "material_agent.adapters.state.sqlite_runtime.SQLiteRuntimeRepository.get_job_result",
            lambda *_args: {"status": "finished", "summary": {}},
        )

        result = cmd_run(args, cfg)

        assert called["kwargs"]["config"]["backend"] == "local"
        assert callable(called["kwargs"]["preflight_hook"])
        assert result == 0


def test_cmd_rescore_delegates_to_rescore_service(monkeypatch):
    from material_agent.commands.scoring import cmd_rescore

    with tempfile.TemporaryDirectory() as d:
        _make_db(d)
        cfg = {
            "scene_weights": {"default": {"composition": 1.0}},
            "scoring": {"pixel_weight": 0.3, "vision_weight": 0.7},
            "scorers": {
                "exposure": {"enabled": True, "weight": 0.5, "min_score": 0.0},
                "sharpness": {"enabled": True, "weight": 0.5, "min_score": 0.0},
            },
        }
        args = Namespace(dir=d, scene=["people"])
        called = {}

        class _FakeRescoreService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                return 3

        monkeypatch.setattr("material_agent.commands.scoring.RescoreService", _FakeRescoreService)

        cmd_rescore(args, cfg)

        assert called["kwargs"]["scene_filters"] == ["people"]
        assert called["kwargs"]["scene_weights"] == {
            "default": {
                "aesthetic_weights": {
                    "subject_moment": 0.0,
                    "composition": 1.0,
                    "lighting": 0.0,
                    "color": 0.0,
                    "depth_separation": 0.0,
                    "mood_story": 0.0,
                }
            }
        }


def test_cmd_rescore_missing_db_returns_nonzero(tmp_path, capsys):
    from material_agent.commands.scoring import cmd_rescore

    result = cmd_rescore(Namespace(dir=str(tmp_path), scene=None), {})

    assert result == 1
    assert "no database" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("clear_xmp", "expected"),
    [(None, False), (True, True)],
)
def test_cmd_reset_ai_only_clears_xmp_when_explicitly_requested(
    tmp_path,
    monkeypatch,
    clear_xmp,
    expected,
):
    from material_agent.commands.io import cmd_reset_ai

    _make_db(str(tmp_path))
    captured = {}

    class _FakeResetService:
        def run(self, input_dir, **kwargs):
            captured["input_dir"] = input_dir
            captured.update(kwargs)
            return {
                "files": 0,
                "processed_rows_deleted": 0,
                "signal_rows_deleted": 0,
                "xmp_cleared": 0,
            }

    monkeypatch.setattr(
        "material_agent.commands.io.ResetAiJudgementService", _FakeResetService
    )
    args = Namespace(dir=str(tmp_path), dry_run=False)
    if clear_xmp is not None:
        args.clear_xmp = clear_xmp

    result = cmd_reset_ai(args)

    assert result == 0
    assert captured["input_dir"] == str(tmp_path)
    assert captured["clear_xmp"] is expected


# ---------------------------------------------------------------------------
# cmd_remap_scenes
# ---------------------------------------------------------------------------


def test_remap_scenes_invalid_target(capsys):
    with tempfile.TemporaryDirectory() as d:
        _make_db(d)
        args = Namespace(dir=d, from_="candid", to="not_a_valid_scene")
        result = cmd_remap_scenes(args)
        out = capsys.readouterr().out
        assert "Error" in out
        assert "not valid" in out
        assert result == 2


def test_remap_scenes_missing_db(capsys):
    with tempfile.TemporaryDirectory() as d:
        args = Namespace(dir=d, from_="candid", to="城市")
        result = cmd_remap_scenes(args)
        out = capsys.readouterr().out
        assert "Error" in out
        assert "no database" in out
        assert result == 1


def test_remap_scenes_updates_rows(capsys):
    with tempfile.TemporaryDirectory() as d:
        db_path = _make_db(d)
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT INTO processed (file_path, status, scene, scene_raw) VALUES (?,?,?,?)",
                [
                    ("/a.arw", "done", "other", "夜晚城市街景"),
                    ("/b.arw", "done", "other", "夜晚城市街景"),
                    ("/c.arw", "done", "people", "棚拍人像"),
                ],
            )
            conn.commit()

        args = Namespace(dir=d, from_="夜晚城市街景", to="城市")
        cmd_remap_scenes(args)
        out = capsys.readouterr().out
        assert "2" in out  # 2 rows updated

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT scene FROM processed WHERE scene_raw='夜晚城市街景'"
            ).fetchall()
        assert all(r[0] == "city" for r in rows)


# ---------------------------------------------------------------------------
# cmd_fix_db
# ---------------------------------------------------------------------------


def test_fix_db_missing_db(capsys):
    with tempfile.TemporaryDirectory() as d:
        args = Namespace(dir=d)
        result = cmd_fix_db(args)
        out = capsys.readouterr().out
        assert "Error" in out
        assert "no database" in out
        assert result == 1


def test_mutating_maintenance_command_rejects_active_run(tmp_path):
    from material_agent.utils.run_control import exclusive_run_lock

    db_path = Path(_make_db(str(tmp_path)))

    with exclusive_run_lock(db_path.parent / "run.lock"):
        with pytest.raises(ValueError, match="already active"):
            cmd_fix_db(Namespace(dir=str(tmp_path)))


def test_fix_db_repairs_star_rating(capsys):
    with tempfile.TemporaryDirectory() as d:
        db_path = _make_db(d)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO processed (file_path, status, total_score, star_rating) "
                "VALUES ('/a.arw', 'done', 8.0, NULL)"
            )
            conn.commit()

        args = Namespace(dir=d)
        cmd_fix_db(args)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT star_rating FROM processed WHERE file_path='/a.arw'"
            ).fetchone()
        # ROUND(8.0 / 2.0) = 4
        assert row[0] == 4
        out = capsys.readouterr().out
        assert "star_rating repaired" in out


def test_fix_db_repairs_group_info(capsys):
    with tempfile.TemporaryDirectory() as d:
        db_path = _make_db(d)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO processed (file_path, status, group_rank, group_size) "
                "VALUES ('/b.arw', 'done', NULL, NULL)"
            )
            conn.commit()

        args = Namespace(dir=d)
        cmd_fix_db(args)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT group_rank, group_size FROM processed WHERE file_path='/b.arw'"
            ).fetchone()
        assert row[0] == 1
        assert row[1] == 1
        out = capsys.readouterr().out
        assert "group info repaired" in out


def test_fix_db_clears_bad_scene_raw(capsys):
    with tempfile.TemporaryDirectory() as d:
        db_path = _make_db(d)
        with sqlite3.connect(db_path) as conn:
            # scene_raw contains a bare scene label — should be cleared
            conn.execute(
                "INSERT INTO processed (file_path, status, scene, scene_raw) "
                "VALUES ('/c.arw', 'done', 'people', '人物')"
            )
            # scene_raw is a real description — should be preserved
            conn.execute(
                "INSERT INTO processed (file_path, status, scene, scene_raw) "
                "VALUES ('/d.arw', 'done', 'people', '穿西装的人物')"
            )
            conn.commit()

        args = Namespace(dir=d)
        cmd_fix_db(args)

        with sqlite3.connect(db_path) as conn:
            bad = conn.execute(
                "SELECT scene_raw FROM processed WHERE file_path='/c.arw'"
            ).fetchone()[0]
            good = conn.execute(
                "SELECT scene_raw FROM processed WHERE file_path='/d.arw'"
            ).fetchone()[0]

        assert bad == ""
        assert good == "穿西装的人物"
        out = capsys.readouterr().out
        assert "bad scene_raw cleared" in out


def test_fix_db_case_insensitive_scene_raw(capsys):
    """Scene labels in mixed case should also be cleared."""
    with tempfile.TemporaryDirectory() as d:
        db_path = _make_db(d)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO processed (file_path, status, scene, scene_raw) "
                "VALUES ('/e.arw', 'done', 'landscape', '  Landscape  ')"
            )
            conn.commit()

        args = Namespace(dir=d)
        cmd_fix_db(args)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT scene_raw FROM processed WHERE file_path='/e.arw'"
            ).fetchone()[0]
        assert row == ""


# ---------------------------------------------------------------------------
# cmd_rescore with pixel scores
# ---------------------------------------------------------------------------


def test_rescore_includes_pixel_scores():
    """When exposure + sharpness exist in DB, rescore should weigh them in."""
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.conn.execute(
            """
                INSERT INTO processed (file_path, status, scene,
                    score_exposure, score_sharpness,
                    score_subject, score_composition, score_lighting, score_color,
                    score_clarity, score_depth, score_mood)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("/px.arw", "done", "other", 4.0, 4.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0),
        )
        s.conn.commit()

        cfg = {
            "scene_weights": {
                "default": {
                    "subject": 1 / 7,
                    "composition": 1 / 7,
                    "lighting": 1 / 7,
                    "color": 1 / 7,
                    "clarity": 1 / 7,
                    "depth": 1 / 7,
                    "mood": 1 / 7,
                }
            },
            "scoring": {"pixel_weight": 0.3, "vision_weight": 0.7},
            "scorers": {
                "exposure": {"enabled": True, "weight": 0.5, "min_score": 0.0},
                "sharpness": {"enabled": True, "weight": 0.5, "min_score": 0.0},
            },
        }
        cmd_rescore(Namespace(dir=d), cfg)

        row = s.conn.execute(
            "SELECT total_score FROM processed WHERE file_path='/px.arw'"
        ).fetchone()
        assert abs(row[0] - 8.99) < 0.05


# ---------------------------------------------------------------------------
# SCENE_LIST completeness check
# ---------------------------------------------------------------------------


def test_scene_weights_cover_all_scenes():
    """Every scene in SCENE_LIST (except 'other') should have a key in config."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    weights = cfg.get("scene_weights", {})
    missing = [s for s in SCENE_LIST if s != "other" and s not in weights]
    assert missing == [], f"Missing scene_weights for: {missing}"


def test_scene_weights_sum_to_one():
    """Each per-scene weight dict should sum to ≤ 1.0 (normalised downstream)."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    for scene, w in cfg.get("scene_weights", {}).items():
        total = sum(w.values())
        assert abs(total - 1.0) < 1e-6, f"scene_weights[{scene}] sums to {total}, expected 1.0"


# ---------------------------------------------------------------------------
# cmd_rescore --scene filter
# ---------------------------------------------------------------------------


def test_rescore_scene_filter_only_updates_matching_scene():
    with tempfile.TemporaryDirectory() as d:
        state = State(d)
        # Insert two files with different scenes
        state.conn.execute(
            "INSERT INTO processed (file_path, status, scene, total_score, "
            "score_exposure, score_sharpness) VALUES (?,?,?,?,?,?)",
            ("/people.arw", "done", "people", 5.0, 7.0, 6.0),
        )
        state.conn.execute(
            "INSERT INTO processed (file_path, status, scene, total_score, "
            "score_exposure, score_sharpness) VALUES (?,?,?,?,?,?)",
            ("/landscape.arw", "done", "landscape", 5.0, 7.0, 6.0),
        )
        state.conn.commit()

        cfg = {
            "scene_weights": {
                "people": {
                    "subject": 0.0,
                    "composition": 0.0,
                    "lighting": 0.0,
                    "color": 0.0,
                    "clarity": 0.0,
                    "depth": 0.0,
                    "mood": 0.0,
                }
            },
            "scoring": {"pixel_weight": 1.0, "vision_weight": 0.0},
            "scorers": {
                "exposure": {"enabled": True, "weight": 0.5, "min_score": 0.0},
                "sharpness": {"enabled": True, "weight": 0.5, "min_score": 0.0},
            },
        }
        args = Namespace(dir=d, config="config.yaml", scene=["people"])
        cmd_rescore(args, cfg)

        rows = state.conn.execute(
            "SELECT file_path, total_score FROM processed ORDER BY file_path"
        ).fetchall()
        paths = {r[0]: r[1] for r in rows}
        # people was rescored (score may differ from 5.0)
        # landscape was NOT touched, should still be 5.0
        assert paths["/landscape.arw"] == 5.0
