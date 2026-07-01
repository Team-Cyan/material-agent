from typing import Any, Protocol


class ArtifactStorePort(Protocol):
    def put_artifact(
        self,
        *,
        kind: str,
        uri: str,
        metadata: dict[str, Any] | None = None,
        job_id: str | None = None,
        job_file_id: str | None = None,
    ) -> str: ...
