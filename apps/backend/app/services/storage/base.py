from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

from .images import ImageMetadata


@dataclass(frozen=True, slots=True)
class StagedFile:
    token: str
    file_size: int
    file_hash: str
    mime_type: str
    image: ImageMetadata | None = None


@dataclass(frozen=True, slots=True)
class StagedDeletion:
    token: str
    file_key: str


class StorageProvider(Protocol):
    driver: str

    async def stage(
        self, source: BinaryIO, *, extension: str, max_bytes: int, inspect_image: bool = False
    ) -> StagedFile: ...

    async def inspect_image(
        self, file_key: str, *, expected_hash: str, mime_type: str, max_bytes: int
    ) -> ImageMetadata: ...

    async def commit(self, staged: StagedFile, *, file_key: str) -> None: ...

    async def discard(self, staged: StagedFile) -> None: ...

    async def exists(self, file_key: str) -> bool: ...

    async def stage_delete(self, file_key: str) -> StagedDeletion: ...

    async def restore(self, deletion: StagedDeletion) -> None: ...

    async def purge(self, deletion: StagedDeletion) -> None: ...


__all__ = ["StagedDeletion", "StagedFile", "StorageProvider"]
