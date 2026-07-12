from typing import Protocol


class FastScreeningPort(Protocol):
    async def score_image_fast(self, jpeg_bytes: bytes) -> float | dict[str, float]: ...


class VisionScoringPort(Protocol):
    async def score_image(self, jpeg_bytes: bytes) -> dict: ...


class SemanticClassifierPort(Protocol):
    async def classify_image(self, jpeg_bytes: bytes) -> dict: ...


class QualityScoringPort(Protocol):
    async def score_quality(self, jpeg_bytes: bytes) -> dict: ...


class ImageEmbeddingPort(Protocol):
    async def embed_image(self, jpeg_bytes: bytes) -> dict: ...


class FaceSignalPort(Protocol):
    async def detect_faces(self, jpeg_bytes: bytes) -> dict: ...


class CommentaryPort(Protocol):
    async def generate_group_commentary(self, group_data: str) -> str: ...

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str: ...
