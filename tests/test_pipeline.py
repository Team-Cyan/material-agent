import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from types import SimpleNamespace

import numpy as np

from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobStage, JobType, SessionKind
from material_agent.app.job_service import JobService
from material_agent.app.session_service import SessionService
from material_agent.core.pipeline import Pipeline
from material_agent.core.scoring_engine import ScoreBundle


def _config(input_dir):
    return {
        "input_dir": input_dir,
        "reprocess": False,
        "grouping": {
            "enabled": False,
            "time_gap_seconds": 30,
            "visual_similarity": {
                "enabled": False,
                "hash_threshold": 10,
                "max_merge_gap_minutes": 10,
            },
            "group_guard": {"enabled": True, "min_score": 7.0},
        },
        "scorers": {
            "exposure": {
                "enabled": True,
                "weight": 0.5,
                "min_score": 0.0,
                "overexpose_threshold": 0.02,
                "overexpose_hard_limit": 2.0,
                "underexpose_threshold": 0.20,
                "underexpose_hard_limit": 2.0,
            },
            "sharpness": {
                "enabled": True,
                "weight": 0.5,
                "min_score": 0.0,
                "min_variance": 50,
                "max_variance": 1000,
            },
            "subject": {"enabled": False, "weight": 0.0, "min_score": 0.0},
            "composition": {"enabled": False, "weight": 0.0, "min_score": 0.0},
            "lighting": {"enabled": False, "weight": 0.0, "min_score": 0.0},
            "color": {"enabled": False, "weight": 0.0, "min_score": 0.0},
            "clarity": {"enabled": False, "weight": 0.0, "min_score": 0.0},
            "depth": {"enabled": False, "weight": 0.0, "min_score": 0.0},
            "mood": {"enabled": False, "weight": 0.0, "min_score": 0.0},
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "timeout": 30,
            "vision_model": "llava:13b",
            "commentary_model": "llava:13b",
            "commentary_enabled": False,
        },
        "scoring": {
            "pixel_weight": 0.3,
            "vision_weight": 0.7,
        },
        "preview": {"max_size": 256, "jpeg_quality": 85},
    }


def test_pipeline_skips_done_files():
    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        state = MagicMock()
        state.is_done.return_value = True
        state.is_scored.return_value = False
        progress = MagicMock()
        pipeline = Pipeline(cfg, state=state, progress=progress)
        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")
        pipeline.run([str(arw)])
        state.mark_done.assert_not_called()


def test_pipeline_empty_file_list():
    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        progress = MagicMock()
        pipeline = Pipeline(cfg, progress=progress)
        pipeline.run([])  # 不应抛出异常
        progress.on_start.assert_not_called()


def test_review_runtime_builder_writes_commentary_into_description_and_state(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        cfg["commentary_enabled"] = True

        repo = SQLiteRuntimeRepository(":memory:")
        session_id = SessionService(repo).create_session(
            kind=SessionKind.CLI,
            input_root=d,
            config_snapshot=cfg,
        )
        job_id = JobService(repo).create_job(
            session_id=session_id,
            job_type=JobType.REVIEW_PHOTOS,
            initial_stage=JobStage.DISCOVER,
        )
        state = MagicMock()
        state.is_done.return_value = False
        state.is_scored.return_value = False
        state.get_scored.return_value = None
        progress = MagicMock()

        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")

        async def fake_compute_scores(frame, client, config, *, fast_screening=None):
            return ScoreBundle(
                scores={"exposure": 6.0, "sharpness": 5.0},
                total=5.5,
                boosted=False,
                meta={},
                scene="people",
                scene_raw="舞台上的人物",
                instructions="exp:6.0 sharp:5.0",
            )

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
        monkeypatch.setattr("material_agent.app.review_runtime.ExifToolXMPWriter", lambda: fake_writer)

        executor = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=progress,
            dry_run=False,
        )
        executor.run(job_id, [str(arw)])

        kwargs = fake_writer.write.call_args.kwargs
        assert "【拍摄建议】拍摄时补一点面光。" in kwargs["description"]
        assert "【后期指导】后期把阴影提一点。" in kwargs["description"]
        state.mark_done.assert_called_once()
        mark_done_kwargs = state.mark_done.call_args.kwargs
        assert mark_done_kwargs["commentary_group_issues"] == "【组内问题】整体偏暗。"
        assert mark_done_kwargs["commentary_shooting"] == "【拍摄建议】拍摄时补一点面光。"
        assert mark_done_kwargs["commentary_post"] == "【后期指导】后期把阴影提一点。"


def test_review_runtime_builder_passes_fast_screening_signals_through_pipeline(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        cfg["screening"] = {"enabled": True, "tier1_threshold": 1.5, "tier2_threshold": 2.5}
        cfg["scorers"]["subject"]["enabled"] = True
        cfg["commentary_enabled"] = True

        repo = SQLiteRuntimeRepository(":memory:")
        session_id = SessionService(repo).create_session(
            kind=SessionKind.CLI,
            input_root=d,
            config_snapshot=cfg,
        )
        job_id = JobService(repo).create_job(
            session_id=session_id,
            job_type=JobType.REVIEW_PHOTOS,
            initial_stage=JobStage.DISCOVER,
        )
        state = MagicMock()
        state.is_done.return_value = False
        state.is_scored.return_value = False
        state.get_scored.return_value = None
        progress = MagicMock()

        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")

        class _SignalFastScreening:
            async def score_image_fast(self, jpeg_bytes):
                return {
                    "technical_ok": 0.1,
                    "subject_clear": 0.2,
                    "composition_ok": 0.2,
                    "usable_for_selection": 0.1,
                }

        class _FakeClient:
            async def score_image(self, jpeg_bytes):
                return {
                    "scene": "people",
                    "scene_raw": "舞台上的人物",
                    "subject": 8.0,
                    "composition": 8.0,
                    "lighting": 8.0,
                    "color": 8.0,
                    "clarity": 8.0,
                    "depth": 8.0,
                    "mood": 8.0,
                }

            async def generate_group_commentary(self, group_data: str) -> str:
                return ""

            async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str:
                return ""

        class _Commentary:
            def __init__(self, *args, **kwargs):
                pass

            async def for_group(self, group_summary, score_details=None):
                return ""

            async def for_photo(self, score_line, group_commentary, scores=None, **kwargs):
                return ""

        fake_writer = MagicMock()
        fake_writer.score_to_stars.return_value = 3
        fake_writer.build_subject_tags.return_value = ["pj:score=5.5"]

        monkeypatch.setattr("material_agent.app.review_runtime.make_client", lambda config: _FakeClient())
        monkeypatch.setattr(
            "material_agent.app.review_runtime.make_fast_screening_port",
            lambda config: _SignalFastScreening(),
        )
        monkeypatch.setattr("material_agent.app.review_runtime.decode_raw", lambda file_path, preview: SimpleNamespace(
            pixels=np.full((8, 8), 32000, dtype=np.uint16),
            jpeg_bytes=b"jpeg",
            gray=np.array([[0, 255] * 4, [255, 0] * 4] * 4, dtype=np.uint8),
        ))
        monkeypatch.setattr("material_agent.app.review_runtime.CommentaryGenerator", _Commentary)
        monkeypatch.setattr("material_agent.app.review_runtime.ExifToolXMPWriter", lambda: fake_writer)

        executor = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=progress,
            dry_run=False,
        )
        executor.run(job_id, [str(arw)])

        mark_scored_kwargs = state.mark_scored.call_args.kwargs
        assert mark_scored_kwargs["screening_prior"] == 0.14
        assert any(
            signal.get("signal_key") == "screening_prior" and signal.get("source") == "musiq"
            for signal in mark_scored_kwargs["signals"]
        )


def test_pipeline_routes_execution_through_review_run_service(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        state = MagicMock()
        state.is_done.return_value = False
        state.is_scored.return_value = False
        progress = MagicMock()
        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")
        called = {}

        class _FakeReviewRunService:
            def __init__(self, repository):
                called["repository"] = repository

            def run(self, **kwargs):
                called["kwargs"] = kwargs
                return "job-123"

        monkeypatch.setattr("material_agent.core.pipeline.ReviewRunService", _FakeReviewRunService)

        pipeline = Pipeline(cfg, state=state, progress=progress)
        pipeline.run([str(arw)])

        assert called["kwargs"]["input_dir"] == d
        assert called["kwargs"]["file_paths"] == [str(arw)]


def test_pipeline_compat_wrapper_uses_real_runtime_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        progress = MagicMock()
        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")
        seen = {}

        class _FakeReviewRunService:
            def __init__(self, repository):
                seen["db_path"] = repository.db_path

            def run(self, **kwargs):
                seen["kwargs"] = kwargs
                return "job-123"

        monkeypatch.setattr("material_agent.core.pipeline.ReviewRunService", _FakeReviewRunService)

        pipeline = Pipeline(cfg, progress=progress)
        pipeline.run([str(arw)])

        assert seen["db_path"].endswith(".material-agent/state.db")
        assert Path(seen["db_path"]).parent == Path(d) / ".material-agent"
