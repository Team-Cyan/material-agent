import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobStage, JobType, SessionKind
from material_agent.app.job_service import JobService
from material_agent.app.jobs.review_photos import ReviewPhotosJob
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


def test_pipeline_passes_done_files_to_review_service_without_prefiltering(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        state = MagicMock()
        state.is_done.return_value = True
        state.is_scored.return_value = False
        progress = MagicMock()
        pipeline = Pipeline(cfg, state=state, progress=progress)
        arw = Path(d) / "test.ARW"
        arw.write_bytes(b"fake")
        captured = {}

        class _FakeReviewRunService:
            def __init__(self, _repository):
                pass

            def run(self, **kwargs):
                captured.update(kwargs)
                return "job-123"

        monkeypatch.setattr(
            "material_agent.core.pipeline.ReviewRunService", _FakeReviewRunService
        )
        monkeypatch.setattr(
            SQLiteRuntimeRepository,
            "get_job_result",
            lambda *_args: {"status": "finished", "summary": {"skipped_files": 1}},
        )

        result = pipeline.run([str(arw)])

        assert captured["file_paths"] == [str(arw)]
        assert captured["state"] is state
        assert result == {
            "job_id": "job-123",
            "status": "finished",
            "summary": {"skipped_files": 1},
        }
        state.is_done.assert_not_called()
        state.is_scored.assert_not_called()
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
        state.get_cached_score_payload.return_value = None
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
        monkeypatch.setattr("material_agent.app.review_runtime.ExifToolXMPWriter", lambda *_args, **_kwargs: fake_writer)

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
        state.get_cached_score_payload.return_value = None
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
        monkeypatch.setattr("material_agent.app.review_runtime.ExifToolXMPWriter", lambda *_args, **_kwargs: fake_writer)

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


def test_review_runtime_dry_run_does_not_pollute_processed_cache(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    class _DisabledCommentary:
        enabled = False

        def __init__(self, *args, **kwargs):
            pass

        async def for_group(self, *args, **kwargs):
            raise AssertionError("disabled group commentary must not be scheduled")

        async def for_photo(self, *args, **kwargs):
            raise AssertionError("disabled photo commentary must not be scheduled")

    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
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
        state.get_cached_score_payload.return_value = None
        progress = MagicMock()
        photo = Path(d) / "test.ARW"
        photo.write_bytes(b"raw")

        async def fake_compute_scores(frame, client, config, *, fast_screening=None):
            return ScoreBundle(
                scores={"exposure": 7.0, "sharpness": 6.0},
                total=6.5,
                boosted=False,
                meta={"_runtime": "fixture"},
                scene="other",
                scene_raw="fixture",
                instructions="fixture",
            )

        monkeypatch.setattr("material_agent.app.review_runtime.make_client", lambda config: object())
        monkeypatch.setattr("material_agent.app.review_runtime.decode_raw", lambda *_args: object())
        monkeypatch.setattr("material_agent.app.review_runtime.compute_scores", fake_compute_scores)
        monkeypatch.setattr(
            "material_agent.app.review_runtime.CommentaryGenerator",
            _DisabledCommentary,
        )

        summary = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=progress,
            dry_run=True,
        ).run(job_id, [str(photo)])

        row = repo.conn.execute(
            "SELECT status FROM job_files WHERE job_id=?",
            (job_id,),
        ).fetchone()
        event_types = {event["event_type"] for event in repo.list_events(job_id)}
        assert row["status"] == "simulated"
        assert summary["written_files"] == 0
        assert summary["simulated_files"] == 1
        assert "job_file_simulated" in event_types
        assert "job_file_written" not in event_types
        state.mark_scored.assert_not_called()
        state.mark_done.assert_not_called()


def test_review_runtime_dry_run_records_cached_done_file_as_skipped(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
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
        photo = str(Path(d) / "done.ARW")
        state = MagicMock()
        state.get_cached_score_payload.return_value = {
            "status": "done",
            "total": 7.5,
            "scores": {"exposure": 7.0, "sharpness": 8.0},
            "meta": {},
            "scene": "other",
            "scene_raw": "cached fixture",
            "decision_reasons": [],
            "signals": [],
            "group_info": {
                "group_id": ReviewPhotosJob._group_id([photo]),
                "group_rank": 1,
                "group_size": 1,
            },
        }
        progress = MagicMock()

        monkeypatch.setattr(
            "material_agent.app.review_runtime.make_client", lambda _config: object()
        )

        summary = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=progress,
            dry_run=True,
        ).run(job_id, [photo])

        row = repo.conn.execute(
            "SELECT status FROM job_files WHERE job_id=?", (job_id,)
        ).fetchone()
        event_types = [event["event_type"] for event in repo.list_events(job_id)]
        assert row["status"] == "skipped"
        assert summary["written_files"] == 0
        assert summary["simulated_files"] == 0
        assert summary["skipped_files"] == 1
        assert "job_file_written" not in event_types
        state.mark_scored.assert_not_called()
        state.mark_done.assert_not_called()


def test_review_runtime_keeps_done_group_members_for_cross_run_rank(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        cfg["grouping"]["enabled"] = True
        cfg["screening_policy"] = {"top1_review_fallback": False}
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
        first = str(Path(d) / "first.ARW")
        second = str(Path(d) / "second.ARW")
        for path in (first, second):
            Path(path).write_bytes(b"raw")
        current_group_id = ReviewPhotosJob._group_id([first, second])

        def cached(path):
            return {
                "status": "done" if path == first else "scored",
                "total": 9.0 if path == first else 8.0,
                "scores": {"exposure": 8.0, "sharpness": 8.0},
                "meta": {},
                "scene": "people",
                "scene_raw": "group fixture",
                "decision": "keep",
                "decision_reasons": [],
                "visible_breakdown": {},
                "signals": [],
                "group_info": {
                    "group_id": current_group_id,
                    "group_rank": 1 if path == first else 2,
                    "group_size": 2,
                },
            }

        state = MagicMock()
        state.get_cached_score_payload.side_effect = cached
        progress = MagicMock()
        fake_writer = MagicMock()
        fake_writer.score_to_stars.return_value = 4
        fake_writer.build_subject_tags.return_value = ["pj:score=8.0"]

        class _Grouper:
            def __init__(self, *_args, **_kwargs):
                pass

            def group(self, file_paths, *, state, progress):
                return [list(file_paths)]

        monkeypatch.setattr("material_agent.app.review_runtime.Grouper", _Grouper)
        monkeypatch.setattr("material_agent.app.review_runtime.make_client", lambda config: object())
        monkeypatch.setattr(
            "material_agent.app.review_runtime.ExifToolXMPWriter",
            lambda *_args, **_kwargs: fake_writer,
        )

        summary = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=progress,
            dry_run=False,
        ).run(job_id, [first, second])

        fake_writer.write.assert_called_once()
        state.mark_done.assert_called_once()
        group_info = state.mark_done.call_args.kwargs["group_info"]
        assert group_info == {
            "group_id": current_group_id,
            "group_rank": 2,
            "group_size": 2,
        }
        assert summary["written_files"] == 1
        assert summary["skipped_files"] == 1


def test_review_runtime_rewrites_done_members_when_incremental_group_changes(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    with tempfile.TemporaryDirectory() as d:
        cfg = _config(d)
        cfg["grouping"]["enabled"] = True
        cfg["screening_policy"] = {"top1_review_fallback": False}
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
        first = str(Path(d) / "existing.ARW")
        second = str(Path(d) / "new-higher-score.ARW")
        for path in (first, second):
            Path(path).write_bytes(b"raw")

        def cached(path):
            return {
                "status": "done" if path == first else "scored",
                "total": 8.0 if path == first else 9.0,
                "scores": {"exposure": 8.0, "sharpness": 8.0},
                "meta": {},
                "scene": "people",
                "scene_raw": "incremental fixture",
                "decision": "keep",
                "decision_reasons": [],
                "visible_breakdown": {},
                "signals": [],
                "group_info": {
                    "group_id": ReviewPhotosJob._group_id([first]),
                    "group_rank": 1,
                    "group_size": 1,
                },
            }

        state = MagicMock()
        state.get_cached_score_payload.side_effect = cached
        writer = MagicMock()
        writer.score_to_stars.return_value = 4
        writer.build_subject_tags.return_value = ["pj:score=8.0"]

        class _Grouper:
            def __init__(self, *_args, **_kwargs):
                pass

            def group(self, file_paths, *, state, progress):
                return [list(file_paths)]

        monkeypatch.setattr("material_agent.app.review_runtime.Grouper", _Grouper)
        monkeypatch.setattr(
            "material_agent.app.review_runtime.make_client", lambda _config: object()
        )
        monkeypatch.setattr(
            "material_agent.app.review_runtime.ExifToolXMPWriter",
            lambda *_args, **_kwargs: writer,
        )

        summary = build_review_job_executor(
            repository=repo,
            config=cfg,
            state=state,
            progress=MagicMock(),
            dry_run=False,
        ).run(job_id, [first, second])

        assert writer.write.call_count == 2
        assert state.mark_done.call_count == 2
        group_info_by_file = {
            call.args[0]: call.kwargs["group_info"] for call in state.mark_done.call_args_list
        }
        current_group_id = ReviewPhotosJob._group_id([first, second])
        assert group_info_by_file[first] == {
            "group_id": current_group_id,
            "group_rank": 2,
            "group_size": 2,
        }
        assert group_info_by_file[second] == {
            "group_id": current_group_id,
            "group_rank": 1,
            "group_size": 2,
        }
        assert summary["written_files"] == 2
        assert summary["skipped_files"] == 0


def test_review_runtime_uses_content_addressed_embedding_model_key(monkeypatch):
    from material_agent.app.review_runtime import build_review_job_executor

    cfg = _config("/tmp")
    cfg["backend"] = "local"
    cfg["local"] = {"embedding": {"enabled": True, "runtime": "openvino"}}
    cfg["grouping"]["enabled"] = True
    cfg["grouping"]["embedding_similarity"] = {"enabled": True, "threshold": 0.9}
    captured = {}

    class _Grouper:
        def __init__(self, _config, *, embedding_loader, embedding_model_key):
            captured["embedding_loader"] = embedding_loader
            captured["embedding_model_key"] = embedding_model_key

        def group(self, file_paths, *, state, progress):
            return [list(file_paths)]

    monkeypatch.setattr("material_agent.app.review_runtime.Grouper", _Grouper)
    monkeypatch.setattr("material_agent.app.review_runtime.make_client", lambda _config: object())
    monkeypatch.setattr(
        "material_agent.app.review_runtime.build_local_embedding_cache_key",
        lambda _config: "embedding-cache-v2:content-digest",
    )

    executor = build_review_job_executor(
        repository=MagicMock(),
        config=cfg,
        state=MagicMock(),
        progress=MagicMock(),
        dry_run=True,
    )

    assert executor.review_job.group_files(["/tmp/a.ARW"]) == [["/tmp/a.ARW"]]
    assert captured["embedding_model_key"] == "embedding-cache-v2:content-digest"
    assert callable(captured["embedding_loader"])


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
        monkeypatch.setattr(
            SQLiteRuntimeRepository,
            "get_job_result",
            lambda *_args: {"status": "finished", "summary": {}},
        )

        pipeline = Pipeline(cfg, state=state, progress=progress)
        result = pipeline.run([str(arw)])

        assert called["kwargs"]["input_dir"] == d
        assert called["kwargs"]["file_paths"] == [str(arw)]
        assert result["job_id"] == "job-123"


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
        monkeypatch.setattr(
            SQLiteRuntimeRepository,
            "get_job_result",
            lambda *_args: {"status": "finished", "summary": {}},
        )

        pipeline = Pipeline(cfg, progress=progress)
        result = pipeline.run([str(arw)])

        assert seen["db_path"].endswith(".material-agent/state.db")
        assert Path(seen["db_path"]).parent == Path(d) / ".material-agent"
        assert result["status"] == "finished"


def test_pipeline_creates_and_closes_managed_processed_state_with_score_cache_key(
    tmp_path,
    monkeypatch,
):
    cfg = _config(str(tmp_path))
    photo = tmp_path / "test.ARW"
    photo.write_bytes(b"fake")
    captured = {}

    class _FakeProcessedRepository:
        def __init__(self, db_path, *, reprocess, score_cache_key):
            captured["db_path"] = Path(db_path)
            captured["reprocess"] = reprocess
            captured["score_cache_key"] = score_cache_key
            captured["managed_state"] = self

        def __enter__(self):
            captured["state_entered"] = True
            return self

        def __exit__(self, *_args):
            captured["state_closed"] = True

    class _FakeReviewRunService:
        def __init__(self, _repository):
            pass

        def run(self, **kwargs):
            captured["service_state"] = kwargs["state"]
            return "job-managed-state"

    monkeypatch.setattr(
        "material_agent.core.pipeline.SQLiteProcessedRepository",
        _FakeProcessedRepository,
    )
    monkeypatch.setattr(
        "material_agent.core.pipeline.build_score_cache_key",
        lambda _config: "score-config-v1:test",
    )
    monkeypatch.setattr(
        "material_agent.core.pipeline.ReviewRunService", _FakeReviewRunService
    )
    monkeypatch.setattr(
        SQLiteRuntimeRepository,
        "get_job_result",
        lambda *_args: {"status": "finished", "summary": {}},
    )

    Pipeline(cfg, progress=MagicMock()).run([str(photo)])

    assert captured["db_path"] == tmp_path / ".material-agent" / "state.db"
    assert captured["reprocess"] is False
    assert captured["score_cache_key"] == "score-config-v1:test"
    assert captured["service_state"] is captured["managed_state"]
    assert captured["state_entered"] is True
    assert captured["state_closed"] is True


def test_pipeline_reconciles_closes_and_returns_partial_result_under_run_controls(
    tmp_path,
    monkeypatch,
):
    cfg = _config(str(tmp_path))
    photo = tmp_path / "test.ARW"
    photo.write_bytes(b"fake")
    injected_state = MagicMock()
    events = []

    @contextmanager
    def _fake_lock(path):
        events.append(("lock_enter", Path(path)))
        yield
        events.append(("lock_exit", Path(path)))

    @contextmanager
    def _fake_sigterm_context():
        events.append("sigterm_enter")
        yield
        events.append("sigterm_exit")

    class _FakeRuntimeRepository:
        def __init__(self, db_path):
            events.append(("repo_open", Path(db_path)))

        def reconcile_abandoned_runs(self):
            events.append("reconcile")
            return {"sessions": 1, "jobs": 1}

        def get_job_result(self, job_id):
            events.append(("get_result", job_id))
            return {
                "status": "finished_with_errors",
                "summary": {"error_files": 2, "written_files": 1},
            }

        def close(self):
            events.append("repo_close")

    class _FakeReviewRunService:
        def __init__(self, repository):
            assert isinstance(repository, _FakeRuntimeRepository)

        def run(self, **kwargs):
            events.append(("run", list(kwargs["file_paths"])))
            assert kwargs["state"] is injected_state
            return "job-partial"

    monkeypatch.setattr(
        "material_agent.core.pipeline.exclusive_run_lock", _fake_lock
    )
    monkeypatch.setattr(
        "material_agent.core.pipeline.sigterm_as_cancellation", _fake_sigterm_context
    )
    monkeypatch.setattr(
        "material_agent.core.pipeline.SQLiteRuntimeRepository",
        _FakeRuntimeRepository,
    )
    monkeypatch.setattr(
        "material_agent.core.pipeline.ReviewRunService", _FakeReviewRunService
    )

    result = Pipeline(
        cfg,
        state=injected_state,
        progress=MagicMock(),
    ).run([str(photo)])

    assert result == {
        "job_id": "job-partial",
        "status": "finished_with_errors",
        "summary": {"error_files": 2, "written_files": 1},
    }
    assert events == [
        ("lock_enter", tmp_path / ".material-agent" / "run.lock"),
        ("repo_open", tmp_path / ".material-agent" / "state.db"),
        "reconcile",
        "sigterm_enter",
        ("run", [str(photo)]),
        "sigterm_exit",
        ("get_result", "job-partial"),
        "repo_close",
        ("lock_exit", tmp_path / ".material-agent" / "run.lock"),
    ]
