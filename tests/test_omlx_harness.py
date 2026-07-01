import json
from pathlib import Path

from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository
from material_agent.app.omlx_harness_service import OMLXHarnessService


def _config() -> dict:
    return {
        "backend": "omlx",
        "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
        "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "raw_extensions": ["ARW"],
        "omlx": {
            "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
            "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
            "admin": {
                "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
                "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
                "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
            },
            "requests": {"model_profile_mode": "auto"},
        },
    }


def _scores() -> dict:
    return {
        "exposure": 5.0,
        "sharpness": 4.0,
        "subject": 7.0,
        "composition": 7.5,
        "lighting": 5.5,
        "color": 6.0,
        "clarity": 4.5,
        "depth": 6.0,
        "mood": 6.5,
    }


def test_omlx_harness_service_writes_summary_and_detects_invalid_commentary(tmp_path):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    for name in ("a.ARW", "b.ARW", "c.ARW"):
        (sample_dir / name).write_bytes(b"raw")

    def _fake_run(args, config):
        input_dir = Path(args.input_dir)
        assert config["omlx"]["full_vision_model"] == "Qwen3-VL-4B-Instruct-4bit"
        assert config["omlx"]["requests"]["model_profile_mode"] == "off"
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            files = sorted(str(path) for path in input_dir.glob("*.ARW"))
            repo.mark_done(
                files[0],
                total_score=7.2,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 2},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.update_commentary(
                files[0],
                "【组内问题】这组反复掉分的是锐度=4.6和光线=5.5，问题多出现在人物场景。",
                "【拍摄建议】拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
                "【后期指导】这张更该先救锐度和光线，先把人物状态和轮廓保住；锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域；优先拉开主体和背景的局部明暗关系，让主光落点更明确。",
            )
            repo.mark_done(
                files[1],
                total_score=6.4,
                star_rating=3,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 2, "group_size": 2},
                scene="people",
                scene_raw="馆内人像",
                decision="review",
            )
            repo.update_commentary(
                files[1],
                "【组内问题】锐度=4.5, 曝光=5.3, 色彩=5.5, 构图=8.0, 主体=7.5",
                "【拍摄建议】拍摄时优先保住主体亮度。",
                "【后期指导】拍摄时先确保对焦在人物眼睛上，使用三脚架保持机身稳定。",
            )
            repo.mark_error(files[2], "boom")

    service = OMLXHarnessService(
        run_command=_fake_run,
        capture_runtime_status=False,
        restore_runtime_after_run=False,
    )
    summary = service.run(
        _config(),
        models=["Qwen3-VL-4B-Instruct-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=3,
        profile_mode="off",
    )

    assert Path(summary["report_path"]).exists()
    assert Path(summary["config_snapshot_path"]).exists()
    assert Path(summary["request_path"]).exists()
    assert summary["best_model"] == "Qwen3-VL-4B-Instruct-4bit"
    assert "ranked first because verdict=runtime_unstable, shared_runtime_drift=False" in summary["best_model_reason"]
    assert summary["recommended_order"] == ["Qwen3-VL-4B-Instruct-4bit"]
    result = summary["results"][0]
    assert result["done_count"] == 2
    assert result["error_count"] == 1
    assert result["invalid_post_count"] == 1
    assert result["invalid_group_issue_count"] == 1
    assert result["verdict"] == "runtime_unstable"
    assert result["action_hint"] == "Fix runtime/probe issues first before comparing prompt quality."
    assert "runtime errors occurred during the live run" in result["primary_risks"]
    assert "run_contains_errors" in result["warnings"]
    assert "post_commentary_contains_shooting_or_group_text" in result["warnings"]
    assert "group_issue_looks_like_raw_score_dump" in result["warnings"]
    assert Path(result["report_path"]).exists()
    assert Path(result["config_snapshot_path"]).exists()
    loaded = json.loads((Path(summary["run_dir"]) / "summary.json").read_text(encoding="utf-8"))
    assert loaded["sample_count"] == 3
    assert loaded["results"][0]["invalid_post_count"] == 1
    config_snapshot = json.loads(Path(summary["config_snapshot_path"]).read_text(encoding="utf-8"))
    assert config_snapshot["omlx"]["requests"]["model_profile_mode"] == "auto"


def test_omlx_harness_service_reports_phase1_scoring_metrics(tmp_path):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    for name in ("a.ARW", "b.ARW"):
        (sample_dir / name).write_bytes(b"raw")

    def _fake_run(args, config):
        input_dir = Path(args.input_dir)
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            files = sorted(str(path) for path in input_dir.glob("*.ARW"))
            repo.mark_done(
                files[0],
                total_score=7.2,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 2},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.mark_done(
                files[1],
                total_score=6.4,
                star_rating=3,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 2, "group_size": 2},
                scene="people",
                scene_raw="馆内人像",
                decision="review",
            )

    service = OMLXHarnessService(
        run_command=_fake_run,
        capture_runtime_status=False,
        restore_runtime_after_run=False,
    )
    summary = service.run(
        _config(),
        models=["Qwen3-VL-4B-Instruct-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=2,
        profile_mode="off",
    )

    scoring_metrics = summary["results"][0]["scoring_metrics"]
    assert scoring_metrics["score_range"] == 0.8
    assert scoring_metrics["favorite_value_ratio"] == 0.429
    assert scoring_metrics["repeated_score_vector_ratio"] == 1.0
    assert scoring_metrics["multi_frame_group_count"] == 1
    assert scoring_metrics["avg_group_score_range"] == 0.8


def test_omlx_harness_service_warns_when_shared_runtime_linked_models_drift(tmp_path):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.ARW").write_bytes(b"raw")

    def _fake_run(args, config):
        input_dir = Path(args.input_dir)
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            file_path = str(next(input_dir.glob("*.ARW")))
            repo.mark_done(
                file_path,
                total_score=7.2,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.update_commentary(
                file_path,
                "【组内问题】这组反复掉分的是锐度=4.6和光线=5.5，问题多出现在人物场景。",
                "【拍摄建议】拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
                "【后期指导】这张更该先救锐度和光线，先把人物状态和轮廓保住；锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域；优先拉开主体和背景的局部明暗关系，让主光落点更明确。",
            )

    status_calls = iter(
        [
            {"linked_models": ["Qwen3-VL-4B-Instruct-4bit"], "served_models": ["Qwen3-VL-4B-Instruct-4bit"]},
            {
                "linked_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "served_models": ["Qwen3-VL-4B-Instruct-4bit", "gemma-4-e2b-it-4bit"],
                "instance_matches": False,
            },
        ]
    )
    service = OMLXHarnessService(
        run_command=_fake_run,
        runtime_status_provider=lambda config: next(status_calls),
        capture_runtime_status=True,
        restore_runtime_after_run=False,
    )
    summary = service.run(
        _config(),
        models=["gemma-4-e2b-it-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=1,
        profile_mode="off",
    )

    result = summary["results"][0]
    assert result["shared_runtime_drift_detected"] is True
    assert result["verdict"] == "ready_for_default_path"
    assert result["action_hint"] == (
        "Investigate shared runtime model pinning before trusting speed or cache comparisons."
    )
    assert "shared_runtime_linked_models_drift" in result["warnings"]
    assert "shared runtime linked models drifted away from the candidate model set" in result["primary_risks"]
    assert Path(result["runtime_status_before_path"]).exists()
    assert Path(result["runtime_status_after_path"]).exists()


def test_omlx_harness_service_warns_when_effective_model_set_does_not_match(tmp_path):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.ARW").write_bytes(b"raw")

    def _fake_run(args, config):
        input_dir = Path(args.input_dir)
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            file_path = str(next(input_dir.glob("*.ARW")))
            repo.mark_done(
                file_path,
                total_score=7.2,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.update_commentary(
                file_path,
                "【组内问题】这组反复掉分的是锐度=4.6和光线=5.5，问题多出现在人物场景。",
                "【拍摄建议】拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
                "【后期指导】这张更该先救锐度和光线，先把人物状态和轮廓保住；锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域；优先拉开主体和背景的局部明暗关系，让主光落点更明确。",
            )

    status_calls = iter(
        [
            {
                "linked_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "served_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "effective_model_set_matches": True,
            },
            {
                "linked_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "served_models": [],
                "effective_model_set_matches": False,
                "instance_matches": False,
            },
        ]
    )
    service = OMLXHarnessService(
        run_command=_fake_run,
        runtime_status_provider=lambda config: next(status_calls),
        capture_runtime_status=True,
        restore_runtime_after_run=False,
    )
    summary = service.run(
        _config(),
        models=["Qwen3-VL-4B-Instruct-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=1,
        profile_mode="off",
    )

    result = summary["results"][0]
    assert result["runtime_effective_model_set_matches_after"] is False
    assert result["action_hint"] == "Investigate runtime readiness before trusting this comparison."
    assert "runtime_effective_model_set_mismatch" in result["warnings"]
    assert "runtime did not effectively expose the expected model set after the run" in result["primary_risks"]


def test_omlx_harness_report_explains_shared_desktop_runtime_status(tmp_path):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.ARW").write_bytes(b"raw")

    def _fake_run(args, config):
        input_dir = Path(args.input_dir)
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            file_path = str(next(input_dir.glob("*.ARW")))
            repo.mark_done(
                file_path,
                total_score=7.2,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.update_commentary(
                file_path,
                "【组内问题】这组反复掉分的是锐度=4.6和光线=5.5，问题多出现在人物场景。",
                "【拍摄建议】拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
                "【后期指导】这张更该先救锐度和光线，先把人物状态和轮廓保住；锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域；优先拉开主体和背景的局部明暗关系，让主光落点更明确。",
            )

    status_calls = iter(
        [
            {
                "runtime_mode": "shared_desktop",
                "shared_desktop_running": True,
                "linked_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "served_models": ["Qwen3-VL-4B-Instruct-4bit", "gemma-4-e2b-it-4bit"],
                "instance_matches": False,
                "effective_model_set_matches": True,
                "served_models_catalog_superset": True,
            },
            {
                "runtime_mode": "shared_desktop",
                "shared_desktop_running": True,
                "linked_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "served_models": ["Qwen3-VL-4B-Instruct-4bit", "gemma-4-e2b-it-4bit"],
                "instance_matches": False,
                "effective_model_set_matches": True,
                "served_models_catalog_superset": True,
            },
        ]
    )
    service = OMLXHarnessService(
        run_command=_fake_run,
        runtime_status_provider=lambda config: next(status_calls),
        capture_runtime_status=True,
        restore_runtime_after_run=False,
    )
    summary = service.run(
        _config(),
        models=["Qwen3-VL-4B-Instruct-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=1,
        profile_mode="off",
    )

    report = Path(summary["results"][0]["report_path"]).read_text(encoding="utf-8")
    comparison_report = Path(summary["report_path"]).read_text(encoding="utf-8")
    assert "- Runtime mode after: `shared_desktop`" in report
    assert (
        "- Runtime interpretation: shared desktop runtime looks aligned; "
        "`/v1/models` appears to include installed-model catalog extras."
    ) in report
    assert (
        "runtime: shared desktop runtime looks aligned; "
        "`/v1/models` appears to include installed-model catalog extras."
    ) in comparison_report


def test_omlx_harness_service_syncs_candidate_model_into_grouped_admin(tmp_path):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.ARW").write_bytes(b"raw")

    def _fake_run(args, config):
        assert config["full_vision_model"] == "gemma-4-e2b-it-4bit"
        assert config["commentary_model"] == "gemma-4-e2b-it-4bit"
        assert config["fast_vision_model"] == "gemma-4-e2b-it-4bit"
        assert config["omlx"]["full_vision_model"] == "gemma-4-e2b-it-4bit"
        assert config["omlx"]["commentary_model"] == "gemma-4-e2b-it-4bit"
        assert config["omlx"]["fast_vision_model"] == "gemma-4-e2b-it-4bit"
        assert config["omlx"]["admin"]["full_vision_model"] == "gemma-4-e2b-it-4bit"
        assert config["omlx"]["admin"]["commentary_model"] == "gemma-4-e2b-it-4bit"
        assert config["omlx"]["admin"]["fast_vision_model"] == "gemma-4-e2b-it-4bit"
        input_dir = Path(args.input_dir)
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            file_path = str(next(input_dir.glob("*.ARW")))
            repo.mark_done(
                file_path,
                total_score=7.0,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.update_commentary(
                file_path,
                "【组内问题】这组反复掉分的是锐度=4.6和光线=5.5，问题多出现在人物场景。",
                "【拍摄建议】拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
                "【后期指导】这张更该先救锐度和光线，先把人物状态和轮廓保住；锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域；优先拉开主体和背景的局部明暗关系，让主光落点更明确。",
            )

    service = OMLXHarnessService(
        run_command=_fake_run,
        capture_runtime_status=False,
        restore_runtime_after_run=False,
    )
    summary = service.run(
        _config(),
        models=["gemma-4-e2b-it-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=1,
        profile_mode="off",
    )

    assert summary["recommended_order"] == ["gemma-4-e2b-it-4bit"]


def test_omlx_harness_service_restores_original_shared_runtime(tmp_path, monkeypatch):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.ARW").write_bytes(b"raw")

    restored = []

    def _fake_run(args, config):
        input_dir = Path(args.input_dir)
        with SQLiteProcessedRepository(str(input_dir)) as repo:
            file_path = str(next(input_dir.glob("*.ARW")))
            repo.mark_done(
                file_path,
                total_score=7.0,
                star_rating=4,
                group_boosted=False,
                scores=_scores(),
                metadata={},
                group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
                scene="people",
                scene_raw="桥边的人像",
                decision="keep",
            )
            repo.update_commentary(
                file_path,
                "【组内问题】这组反复掉分的是锐度=4.6和光线=5.5，问题多出现在人物场景。",
                "【拍摄建议】拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
                "【后期指导】这张更该先救锐度和光线，先把人物状态和轮廓保住；锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域；优先拉开主体和背景的局部明暗关系，让主光落点更明确。",
            )

    def _fake_restore(config):
        restored.append(config["omlx"]["full_vision_model"])
        return {
            "restored": True,
            "restarted": True,
            "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
            "linked_models": ["Qwen3-VL-4B-Instruct-4bit"],
            "served_models": ["Qwen3-VL-4B-Instruct-4bit"],
            "drift_detected": False,
        }

    monkeypatch.setattr(
        "material_agent.app.omlx_harness_service.is_configured_shared_omlx_runtime",
        lambda config: True,
    )
    service = OMLXHarnessService(
        run_command=_fake_run,
        capture_runtime_status=False,
        restore_runtime_after_run=True,
        restore_runtime_command=_fake_restore,
    )
    summary = service.run(
        _config(),
        models=["Qwen3-VL-4B-Instruct-4bit", "gemma-4-e2b-it-4bit"],
        sample_set=[str(sample_dir)],
        result_path=str(tmp_path / "results"),
        limit=1,
        profile_mode="off",
    )

    assert restored == ["Qwen3-VL-4B-Instruct-4bit"]
    assert summary["restore_summary"]["restored"] is True
    assert summary["restore_summary"]["active_models"] == ["Qwen3-VL-4B-Instruct-4bit"]
    report = Path(summary["report_path"]).read_text(encoding="utf-8")
    assert "- Restored: `True`" in report
    assert '- Restore active models: `["Qwen3-VL-4B-Instruct-4bit"]`' in report
