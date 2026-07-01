from typing import Any

from .dto import SessionKind, SessionStatus


class SessionService:
    def __init__(self, repository):
        self.repository = repository

    def create_session(
        self,
        *,
        kind: SessionKind,
        input_root: str,
        config_snapshot: dict[str, Any],
        status: SessionStatus = SessionStatus.OPEN,
    ) -> str:
        return self.repository.create_session(
            kind=kind,
            input_root=input_root,
            config_snapshot=config_snapshot,
            status=status,
        )

    def update_session(self, session_id: str, *, status: SessionStatus) -> None:
        self.repository.update_session(session_id, status=status)

    def list_sessions(self):
        return self.repository.list_sessions()
