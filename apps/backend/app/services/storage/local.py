from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from .base import StagedDeletion, StagedFile
from .images import ImageMetadata, inspect_image_bytes

_CHUNK_SIZE = 64 * 1024
_IMAGE_DECODE_CONCURRENCY = 1
_IMAGE_DECODE_QUEUE_TIMEOUT_SECONDS = 10


def _detected_mime(header: bytes, path: Path, extension: str) -> str | None:
    if header.startswith(b"\xff\xd8\xff") and extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n") and extension == "png":
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")) and extension == "gif":
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP" and extension == "webp":
        return "image/webp"
    if header.startswith(b"%PDF-") and extension == "pdf":
        return "application/pdf"
    if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") and extension in {"doc", "xls"}:
        return "application/msword" if extension == "doc" else "application/vnd.ms-excel"
    if header.startswith(b"PK\x03\x04") and extension in {"docx", "xlsx", "zip"}:
        try:
            with zipfile.ZipFile(path) as archive:
                names = frozenset(archive.namelist())
        except (OSError, zipfile.BadZipFile):  # fmt: skip
            return None
        if extension == "docx" and "[Content_Types].xml" in names and any(name.startswith("word/") for name in names):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if extension == "xlsx" and "[Content_Types].xml" in names and any(name.startswith("xl/") for name in names):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if extension == "zip":
            return "application/zip"
    return None


class LocalStorageProvider:
    driver = "local"

    def __init__(self, root: Path, *, io_concurrency: int) -> None:
        self._root = root.resolve()
        self._semaphore = asyncio.Semaphore(io_concurrency)
        self._image_decode_semaphore = asyncio.Semaphore(_IMAGE_DECODE_CONCURRENCY)

    async def stage(
        self, source: BinaryIO, *, extension: str, max_bytes: int, inspect_image: bool = False
    ) -> StagedFile:
        if not inspect_image:
            return await self._stage(source, extension=extension, max_bytes=max_bytes, inspect_image=False)
        try:
            await asyncio.wait_for(self._image_decode_semaphore.acquire(), timeout=_IMAGE_DECODE_QUEUE_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise ValueError("image_decode_busy") from exc
        try:
            return await self._stage(source, extension=extension, max_bytes=max_bytes, inspect_image=True)
        finally:
            self._image_decode_semaphore.release()

    async def _stage(self, source: BinaryIO, *, extension: str, max_bytes: int, inspect_image: bool) -> StagedFile:
        async with self._semaphore:
            task = asyncio.create_task(asyncio.to_thread(self._stage_sync, source, extension, max_bytes, inspect_image))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Keep the IO slot until the worker finishes; reclaim its unpublished file.
                try:
                    staged = await task
                except Exception:
                    raise
                await asyncio.to_thread(Path(staged.token).unlink, missing_ok=True)
                raise

    def _stage_sync(self, source: BinaryIO, extension: str, max_bytes: int, inspect_image: bool = False) -> StagedFile:
        staging_root = self._root.parent / f".{self._root.name}-staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        header = bytearray()
        descriptor, raw_path = tempfile.mkstemp(prefix="upload-", dir=staging_root)
        path = Path(raw_path)
        try:
            with os.fdopen(descriptor, "wb") as target:
                while chunk := source.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("file_too_large")
                    digest.update(chunk)
                    if len(header) < 16:
                        header.extend(chunk[: 16 - len(header)])
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if size == 0:
                raise ValueError("empty_file")
            mime_type = _detected_mime(bytes(header), path, extension)
            if mime_type is None:
                raise ValueError("file_type_mismatch")
            image = inspect_image_bytes(path.read_bytes(), mime_type) if inspect_image else None
            return StagedFile(
                token=str(path), file_size=size, file_hash=digest.hexdigest(), mime_type=mime_type, image=image
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def inspect_image(
        self, file_key: str, *, expected_hash: str, mime_type: str, max_bytes: int
    ) -> ImageMetadata:
        try:
            await asyncio.wait_for(self._image_decode_semaphore.acquire(), timeout=_IMAGE_DECODE_QUEUE_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise ValueError("image_decode_busy") from exc
        try:
            async with self._semaphore:
                task = asyncio.create_task(
                    asyncio.to_thread(self._inspect_image_sync, file_key, expected_hash, mime_type, max_bytes)
                )
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
        finally:
            self._image_decode_semaphore.release()

    def _inspect_image_sync(self, file_key: str, expected_hash: str, mime_type: str, max_bytes: int) -> ImageMetadata:
        with self._safe_path(file_key).open("rb") as source:
            payload = source.read(max_bytes + 1)
        if len(payload) != max_bytes:
            raise ValueError("image_size_mismatch")
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError("image_hash_mismatch")
        return inspect_image_bytes(payload, mime_type)

    async def commit(self, staged: StagedFile, *, file_key: str) -> None:
        async with self._semaphore:
            await asyncio.to_thread(self._commit_sync, staged, file_key)

    def _commit_sync(self, staged: StagedFile, file_key: str) -> None:
        target = self._safe_path(file_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.token, target)

    async def discard(self, staged: StagedFile) -> None:
        async with self._semaphore:
            await asyncio.to_thread(Path(staged.token).unlink, missing_ok=True)

    async def exists(self, file_key: str) -> bool:
        async with self._semaphore:
            return await asyncio.to_thread(self._safe_path(file_key).is_file)

    async def stage_delete(self, file_key: str) -> StagedDeletion:
        async with self._semaphore:
            return await asyncio.to_thread(self._stage_delete_sync, file_key)

    def _stage_delete_sync(self, file_key: str) -> StagedDeletion:
        source = self._safe_path(file_key)
        if not source.is_file():
            raise FileNotFoundError(file_key)
        trash_root = self._root.parent / f".{self._root.name}-trash"
        trash_root.mkdir(parents=True, exist_ok=True)
        target = trash_root / uuid.uuid4().hex
        os.replace(source, target)
        return StagedDeletion(token=str(target), file_key=file_key)

    async def restore(self, deletion: StagedDeletion) -> None:
        async with self._semaphore:
            await asyncio.to_thread(self._restore_sync, deletion)

    def _restore_sync(self, deletion: StagedDeletion) -> None:
        source = Path(deletion.token)
        if not source.exists():
            return
        target = self._safe_path(deletion.file_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)

    async def purge(self, deletion: StagedDeletion) -> None:
        async with self._semaphore:
            await asyncio.to_thread(Path(deletion.token).unlink, missing_ok=True)

    def _safe_path(self, file_key: str) -> Path:
        candidate = (self._root / file_key).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("file key escapes storage root")
        return candidate


__all__ = ["LocalStorageProvider"]
