from typing import Protocol


class FastScreeningPort(Protocol):
    async def score_image_fast(self, jpeg_bytes: bytes) -> float | dict[str, float]: ...


class VisionScoringPort(Protocol):
    async def score_image(self, jpeg_bytes: bytes) -> dict: ...


class CommentaryPort(Protocol):
    async def generate_group_commentary(self, group_data: str) -> str: ...

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str: ...
