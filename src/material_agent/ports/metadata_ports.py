from typing import Protocol


class MetadataWritePort(Protocol):
    def write(
        self,
        *,
        file_path: str,
        rating: int,
        subject_tags: list[str],
        instructions: str,
        description: str,
    ) -> None: ...
