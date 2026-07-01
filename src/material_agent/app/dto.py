from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SessionKind(StrEnum):
    CLI = "cli"
    GUI = "gui"


class SessionStatus(StrEnum):
    OPEN = "open"
    RUNNING = "running"
    FINISHED = "finished"
    FINISHED_WITH_ERRORS = "finished_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    REVIEW_PHOTOS = "review_photos"
    RESCORE = "rescore"
    REWRITE_XMP = "rewrite_xmp"
    SCAN_SCENES = "scan_scenes"
    REMAP_SCENES = "remap_scenes"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FINISHED_WITH_ERRORS = "finished_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    DISCOVER = "discover"
    GROUP = "group"
    SCORE = "score"
    COMMENT = "comment"
    WRITE = "write"
    FINALIZE = "finalize"


class JobFileStatus(StrEnum):
    PENDING = "pending"
    DECODED = "decoded"
    SCREENED = "screened"
    SCORED = "scored"
    COMMENTED = "commented"
    WRITTEN = "written"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(slots=True)
class SessionRecord:
    id: str
    kind: SessionKind
    input_root: Path
    config_snapshot: dict[str, Any]
    status: SessionStatus
    created_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class JobRecord:
    id: str
    session_id: str
    type: JobType
    stage: JobStage
    status: JobStatus
    summary: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class JobFileRecord:
    id: str
    job_id: str
    file_path: Path
    status: JobFileStatus
    group_id: str | None = None
    rank: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    score_total: float | None = None
    scene: str | None = None
    scene_raw: str | None = None


@dataclass(slots=True)
class ArtifactRef:
    id: str
    kind: str
    uri: str
    metadata: dict[str, Any] = field(default_factory=dict)
