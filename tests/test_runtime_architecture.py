from dataclasses import is_dataclass
import importlib
from pathlib import Path
import sys

from material_agent.app.dto import (
    ArtifactRef,
    JobRecord,
    JobStage,
    JobStatus,
    JobType,
    JobFileRecord,
    JobFileStatus,
    SessionKind,
    SessionRecord,
    SessionStatus,
)
from material_agent.ports.artifact_ports import ArtifactStorePort
from material_agent.ports.metadata_ports import MetadataWritePort
from material_agent.ports.model_ports import CommentaryPort, FastScreeningPort, VisionScoringPort
from material_agent.ports.progress_ports import EventSinkPort
from material_agent.ports.state_ports import JobRepositoryPort, SessionRepositoryPort


def test_runtime_packages_import_cleanly():
    import material_agent.app  # noqa: F401
    import material_agent.domain  # noqa: F401
    import material_agent.ports  # noqa: F401
    import material_agent.adapters  # noqa: F401


def test_domain_modules_export_business_rules():
    from material_agent.domain.commentary import CommentaryGenerator
    from material_agent.domain.grouper import Grouper
    from material_agent.domain.scoring_engine import RawFrame, ScoreBundle, compute_scores, decode_raw

    assert CommentaryGenerator is not None
    assert Grouper is not None
    assert RawFrame is not None
    assert ScoreBundle is not None
    assert callable(compute_scores)
    assert callable(decode_raw)


def test_core_modules_remain_compatibility_shims_for_domain_rules():
    from material_agent.core.commentary import CommentaryGenerator as CoreCommentaryGenerator
    from material_agent.core.grouper import Grouper as CoreGrouper
    from material_agent.core.scoring_engine import ScoreBundle as CoreScoreBundle
    from material_agent.domain.commentary import CommentaryGenerator as DomainCommentaryGenerator
    from material_agent.domain.grouper import Grouper as DomainGrouper
    from material_agent.domain.scoring_engine import ScoreBundle as DomainScoreBundle

    assert CoreCommentaryGenerator is DomainCommentaryGenerator
    assert issubclass(CoreGrouper, DomainGrouper)
    assert CoreScoreBundle is DomainScoreBundle


def test_core_shims_follow_domain_symbols_after_domain_module_reload():
    for module_name in (
        "material_agent.core.scoring_engine",
        "material_agent.domain.scoring_engine",
        "material_agent.core.commentary",
        "material_agent.domain.commentary",
    ):
        sys.modules.pop(module_name, None)

    core_scoring = importlib.import_module("material_agent.core.scoring_engine")
    core_commentary = importlib.import_module("material_agent.core.commentary")

    first_score_bundle = importlib.import_module("material_agent.domain.scoring_engine").ScoreBundle
    first_commentary_generator = importlib.import_module(
        "material_agent.domain.commentary"
    ).CommentaryGenerator

    assert core_scoring.ScoreBundle is first_score_bundle
    assert core_commentary.CommentaryGenerator is first_commentary_generator

    sys.modules.pop("material_agent.domain.scoring_engine", None)
    sys.modules.pop("material_agent.domain.commentary", None)

    reloaded_score_bundle = importlib.import_module("material_agent.domain.scoring_engine").ScoreBundle
    reloaded_commentary_generator = importlib.import_module(
        "material_agent.domain.commentary"
    ).CommentaryGenerator

    assert core_scoring.ScoreBundle is reloaded_score_bundle
    assert core_commentary.CommentaryGenerator is reloaded_commentary_generator


def test_core_shims_preserve_legacy_public_exports():
    from material_agent.core.commentary import (
        CommentaryGenerator,
        build_group_commentary_input,
        build_photo_commentary_context,
        regenerate_group_commentary,
        regenerate_post_commentary,
    )
    from material_agent.core.scoring_engine import build_visible_breakdown_instructions
    from material_agent.domain.commentary import (
        CommentaryGenerator as DomainCommentaryGenerator,
        build_group_commentary_input as domain_build_group_commentary_input,
        build_photo_commentary_context as domain_build_photo_commentary_context,
        regenerate_group_commentary as domain_regenerate_group_commentary,
        regenerate_post_commentary as domain_regenerate_post_commentary,
    )
    from material_agent.domain.scoring_engine import (
        build_visible_breakdown_instructions as domain_build_visible_breakdown_instructions,
    )

    assert CommentaryGenerator is DomainCommentaryGenerator
    assert build_group_commentary_input is domain_build_group_commentary_input
    assert build_photo_commentary_context is domain_build_photo_commentary_context
    assert regenerate_group_commentary is domain_regenerate_group_commentary
    assert regenerate_post_commentary is domain_regenerate_post_commentary
    assert build_visible_breakdown_instructions is domain_build_visible_breakdown_instructions


def test_core_shim_star_imports_keep_legacy_public_names():
    commentary_namespace: dict[str, object] = {}
    scoring_namespace: dict[str, object] = {}

    exec("from material_agent.core.commentary import *", commentary_namespace)
    exec("from material_agent.core.scoring_engine import *", scoring_namespace)

    for name in (
        "CommentaryGenerator",
        "build_group_commentary_input",
        "build_photo_commentary_context",
        "regenerate_group_commentary",
        "regenerate_post_commentary",
    ):
        assert name in commentary_namespace

    for name in (
        "RawFrame",
        "ScoreBundle",
        "build_visible_breakdown_instructions",
        "compute_scores",
    ):
        assert name in scoring_namespace


def test_core_package_exports_follow_latest_compatibility_symbols():
    for module_name in (
        "material_agent.core",
        "material_agent.core.scoring_engine",
        "material_agent.domain.scoring_engine",
        "material_agent.core.commentary",
        "material_agent.domain.commentary",
    ):
        sys.modules.pop(module_name, None)

    core_package = importlib.import_module("material_agent.core")

    first_score_bundle = importlib.import_module("material_agent.domain.scoring_engine").ScoreBundle
    first_commentary_generator = importlib.import_module(
        "material_agent.domain.commentary"
    ).CommentaryGenerator

    assert core_package.ScoreBundle is first_score_bundle
    assert core_package.CommentaryGenerator is first_commentary_generator

    sys.modules.pop("material_agent.domain.scoring_engine", None)
    sys.modules.pop("material_agent.domain.commentary", None)

    reloaded_score_bundle = importlib.import_module("material_agent.domain.scoring_engine").ScoreBundle
    reloaded_build_visible_breakdown_instructions = importlib.import_module(
        "material_agent.domain.scoring_engine"
    ).build_visible_breakdown_instructions
    reloaded_commentary_generator = importlib.import_module(
        "material_agent.domain.commentary"
    ).CommentaryGenerator

    assert core_package.ScoreBundle is reloaded_score_bundle
    assert core_package.CommentaryGenerator is reloaded_commentary_generator
    assert (
        core_package.build_visible_breakdown_instructions
        is reloaded_build_visible_breakdown_instructions
    )


def test_runtime_status_and_record_types_exist():
    assert SessionStatus.RUNNING.value == "running"
    assert SessionKind.CLI.value == "cli"
    assert JobStatus.QUEUED.value == "queued"
    assert JobStage.SCORE.value == "score"
    assert JobType.REVIEW_PHOTOS.value == "review_photos"
    assert JobFileStatus.WRITTEN.value == "written"

    for cls in (SessionRecord, JobRecord, JobFileRecord, ArtifactRef):
        assert is_dataclass(cls)

    session = SessionRecord(
        id="s1",
        kind=SessionKind.CLI,
        input_root=Path("/tmp/photos"),
        config_snapshot={"backend": "omlx"},
        status=SessionStatus.OPEN,
    )
    job = JobRecord(
        id="j1",
        session_id="s1",
        type=JobType.REVIEW_PHOTOS,
        stage=JobStage.DISCOVER,
        status=JobStatus.QUEUED,
    )
    assert session.id == "s1"
    assert job.session_id == "s1"


def test_runtime_ports_define_required_interfaces():
    for port in (
        FastScreeningPort,
        VisionScoringPort,
        CommentaryPort,
        SessionRepositoryPort,
        JobRepositoryPort,
        ArtifactStorePort,
        MetadataWritePort,
        EventSinkPort,
    ):
        assert getattr(port, "__dict__", None) is not None
