from __future__ import annotations

import asyncio
import hashlib
import json
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
            task = asyncio.create_task(asyncio.to_thread(self._stage_delete_sync, file_key))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Do not release the IO slot or lose the mapping while rename is still running.
                deletion = await self._settle(task)
                restore = asyncio.create_task(asyncio.to_thread(self._restore_sync, deletion))
                await self._settle(restore)
                raise

    @staticmethod
    async def _settle[T](task: asyncio.Task[T]) -> T:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        return task.result()

    def _trash_root(self) -> Path:
        root = self._root.parent / f".{self._root.name}-trash"
        if root.resolve() != root:
            raise ValueError("trash directory must not be a link")
        return root

    @staticmethod
    def _sync_directory(path: Path) -> None:
        if os.name != "nt":
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _deletion_paths(self, deletion: StagedDeletion) -> tuple[Path, Path]:
        token = Path(deletion.token)
        if (
            token.parent != self._trash_root()
            or token.resolve() != token
            or uuid.UUID(hex=token.name).hex != token.name
        ):
            raise ValueError("invalid deletion token")
        journal = token.with_suffix(".json")
        if journal.resolve() != journal:
            raise ValueError("deletion journal must not be a link")
        return token, journal

    def _stage_delete_sync(self, file_key: str) -> StagedDeletion:
        source = self._safe_path(file_key)
        if not source.is_file():
            raise FileNotFoundError(file_key)
        trash_root = self._trash_root()
        trash_root.mkdir(parents=True, exist_ok=True)
        self._sync_directory(trash_root.parent)
        target = trash_root / uuid.uuid4().hex
        # Publish and fsync the recovery mapping BEFORE moving the original file.
        journal = target.with_suffix(".json")
        with source.open("rb") as original:
            digest = hashlib.file_digest(original, "sha256").hexdigest()
        temporary = target.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump({"schema_version": 1, "file_key": file_key, "sha256": digest}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, journal)
        self._sync_directory(trash_root)
        deletion = StagedDeletion(token=str(target), file_key=file_key)
        try:
            os.replace(source, target)
            self._sync_directory(source.parent)
            self._sync_directory(trash_root)
        except BaseException:
            self._restore_sync(deletion)
            raise
        return deletion

    async def restore(self, deletion: StagedDeletion) -> None:
        async with self._semaphore:
            task = asyncio.create_task(asyncio.to_thread(self._restore_sync, deletion))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await self._settle(task)
                raise

    def _restore_sync(self, deletion: StagedDeletion) -> None:
        source, journal = self._deletion_paths(deletion)
        target = self._safe_path(deletion.file_key)
        if not journal.exists():
            if source.exists() or not target.is_file():
                raise ValueError("deletion recovery mapping is missing")
            return
        try:
            record = self._read_journal(journal)
        except FileNotFoundError:
            if source.exists() or not target.is_file():
                raise
            return
        if record["file_key"] != deletion.file_key:
            raise ValueError("deletion recovery mapping does not match")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # A completed restore or a crash before rename is safe only for the recorded bytes.
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                    raise OSError("recovery destination contains different content")
            if source.exists() and not source.samefile(target):
                raise OSError("both deletion source and destination exist; manual review required")
        else:
            try:
                with source.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                        raise OSError("recovery content does not match")
                # Linking is atomic and refuses to overwrite a concurrently created destination.
                try:
                    os.link(source, target)
                except FileExistsError:
                    if not source.samefile(target):
                        raise OSError("recovery destination was replaced") from None
            except FileNotFoundError:
                # Another recovery may have completed the same restore after our existence check.
                with target.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                        raise OSError("recovery destination contains different content") from None
            self._sync_directory(target.parent)
        source.unlink(missing_ok=True)
        self._sync_directory(source.parent)
        journal.unlink(missing_ok=True)
        self._sync_directory(journal.parent)

    async def purge(self, deletion: StagedDeletion) -> None:
        async with self._semaphore:
            task = asyncio.create_task(asyncio.to_thread(self._purge_sync, deletion))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await self._settle(task)
                raise

    def _purge_sync(self, deletion: StagedDeletion) -> None:
        target, journal = self._deletion_paths(deletion)
        if not journal.exists():
            if target.exists():
                raise ValueError("deletion recovery mapping is missing")
            return
        try:
            record = self._read_journal(journal)
        except FileNotFoundError:
            if target.exists():
                raise
            return
        if record["file_key"] != deletion.file_key:
            raise ValueError("deletion recovery mapping does not match")
        try:
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                    raise OSError("deletion content does not match")
        except FileNotFoundError:
            pass  # A previous purge may have removed the bytes before clearing the journal.
        target.unlink(missing_ok=True)
        self._sync_directory(target.parent)
        journal.unlink(missing_ok=True)
        self._sync_directory(journal.parent)

    def _read_journal(self, path: Path) -> dict[str, str]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("invalid deletion recovery mapping")
        key, digest = value.get("file_key"), value.get("sha256")
        if (
            not isinstance(key, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("invalid deletion recovery fields")
        self._safe_path(key)
        return {"file_key": key, "sha256": digest}

    async def pending_deletions(self) -> list[StagedDeletion]:
        async with self._semaphore:
            return await asyncio.to_thread(self._pending_deletions_sync)

    def _pending_deletions_sync(self) -> list[StagedDeletion]:
        result = []
        for journal in sorted(self._trash_root().glob("*.json")):
            token = journal.with_suffix("")
            deletion = StagedDeletion(token=str(token), file_key="")
            self._deletion_paths(deletion)
            try:
                record = self._read_journal(journal)
            except FileNotFoundError:
                if token.exists():
                    raise
                continue
            result.append(StagedDeletion(token=str(token), file_key=record["file_key"]))
        return result

    def _safe_path(self, file_key: str) -> Path:
        candidate = (self._root / file_key).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("file key escapes storage root")
        return candidate


__all__ = ["LocalStorageProvider"]
