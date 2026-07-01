from typing import Any, Protocol


class EventSinkPort(Protocol):
    def publish(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        job_id: str | None = None,
        job_file_id: str | None = None,
    ) -> None: ...
