from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import uuid
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image, UnidentifiedImageError

from app.domains.settings.schemas import SiteLogoValue

_CHUNK_SIZE = 64 * 1024
_MAX_BYTES = 2 * 1024 * 1024
_MAX_EDGE = 4096
_MAX_PIXELS = 16_000_000
_FORMAT_POLICY = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


@dataclass(frozen=True, slots=True)
class StagedSiteLogo:
    token: str
    extension: str
    mime_type: str
    file_size: int
    sha256: str

    def value(self) -> SiteLogoValue:
        return SiteLogoValue(
            path=f"site/logo.{self.extension}",
            mime_type=self.mime_type,
            file_size=self.file_size,
            sha256=self.sha256,
        )


@dataclass(frozen=True, slots=True)
class FileMove:
    file_key: str
    trash_token: str


@dataclass(frozen=True, slots=True)
class PreparedMediaOperation:
    operation_id: str
    kind: str
    manifest_path: str
    old_revision: int
    new_revision: int
    old_logo: dict[str, Any] | None
    new_logo: dict[str, Any] | None
    target_key: str | None
    old_files: tuple[FileMove, ...]


class SettingsMediaStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        parent = self.root.parent
        self.staging_root = parent / f".{self.root.name}-staging"
        self.trash_root = parent / f".{self.root.name}-trash"
        self.operations_root = parent / f".{self.root.name}-operations"
        self._lock = asyncio.Lock()

    async def ensure_layout(self) -> None:
        await asyncio.to_thread(self._ensure_layout_sync)

    def _ensure_layout_sync(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.trash_root.mkdir(parents=True, exist_ok=True)
        self.operations_root.mkdir(parents=True, exist_ok=True)

    async def stage_site_logo(self, source: BinaryIO) -> StagedSiteLogo:
        async with self._lock:
            return await asyncio.to_thread(self._stage_site_logo_sync, source)

    def _stage_site_logo_sync(self, source: BinaryIO) -> StagedSiteLogo:
        self._ensure_layout_sync()
        descriptor, raw_path = tempfile.mkstemp(prefix="site-logo-", dir=self.staging_root)
        path = Path(raw_path)
        size = 0
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, "wb") as target:
                while chunk := source.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > _MAX_BYTES:
                        raise ValueError("file_too_large")
                    digest.update(chunk)
                    target.write(chunk)
                if size == 0:
                    raise ValueError("empty_file")
                target.flush()
                os.fsync(target.fileno())
            image_format = self._validate_image(path)
            extension, mime_type = _FORMAT_POLICY[image_format]
            return StagedSiteLogo(
                token=str(path),
                extension=extension,
                mime_type=mime_type,
                file_size=size,
                sha256=digest.hexdigest(),
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _validate_image(path: Path) -> str:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image_format = image.format
                    if image_format not in _FORMAT_POLICY:
                        raise ValueError("unsupported_image_format")
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError("animated_image_not_allowed")
                    width, height = image.size
                    if width <= 0 or height <= 0 or max(width, height) > _MAX_EDGE or width * height > _MAX_PIXELS:
                        raise ValueError("image_dimensions_invalid")
                    image.verify()
                with Image.open(path) as decoded:
                    decoded.load()
            assert image_format is not None
            return image_format
        except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError) as exc:
            raise ValueError("invalid_image") from exc

    async def prepare_replace(
        self,
        *,
        staged: StagedSiteLogo,
        old_logo: SiteLogoValue | None,
        old_revision: int,
        new_revision: int,
    ) -> PreparedMediaOperation:
        async with self._lock:
            return await asyncio.to_thread(
                self._prepare_sync,
                kind="replace",
                staged=staged,
                old_logo=old_logo,
                old_revision=old_revision,
                new_revision=new_revision,
            )

    async def prepare_delete(
        self,
        *,
        old_logo: SiteLogoValue | None,
        old_revision: int,
        new_revision: int,
    ) -> PreparedMediaOperation:
        async with self._lock:
            return await asyncio.to_thread(
                self._prepare_sync,
                kind="delete",
                staged=None,
                old_logo=old_logo,
                old_revision=old_revision,
                new_revision=new_revision,
            )

    def _prepare_sync(
        self,
        *,
        kind: str,
        staged: StagedSiteLogo | None,
        old_logo: SiteLogoValue | None,
        old_revision: int,
        new_revision: int,
    ) -> PreparedMediaOperation:
        self._ensure_layout_sync()
        operation_id = uuid.uuid4().hex
        target_key = f"site/logo.{staged.extension}" if staged is not None else None
        old_files = tuple(
            FileMove(file_key=key, trash_token=str(self.trash_root / f"{operation_id}-{Path(key).suffix[1:]}"))
            for key in self._existing_logo_keys()
        )
        operation = PreparedMediaOperation(
            operation_id=operation_id,
            kind=kind,
            manifest_path=str(self.operations_root / f"{operation_id}.json"),
            old_revision=old_revision,
            new_revision=new_revision,
            old_logo=old_logo.model_dump(mode="json") if old_logo is not None else None,
            new_logo=staged.value().model_dump(mode="json") if staged is not None else None,
            target_key=target_key,
            old_files=old_files,
        )
        self._write_manifest(operation, state="prepared")
        try:
            for move in old_files:
                source = self._safe_path(move.file_key)
                if source.is_file():
                    os.replace(source, move.trash_token)
            if staged is not None and target_key is not None:
                target = self._safe_path(target_key)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged.token, target)
            self._write_manifest(operation, state="swapped")
            return operation
        except BaseException:
            self._rollback_sync(operation)
            raise

    async def rollback(self, operation: PreparedMediaOperation) -> None:
        async with self._lock:
            await asyncio.to_thread(self._rollback_sync, operation)

    def _rollback_sync(self, operation: PreparedMediaOperation) -> None:
        if operation.target_key is not None:
            target = self._safe_path(operation.target_key)
            if target.is_file() and self._matches_logo(target, operation.new_logo):
                target.unlink()
        for move in reversed(operation.old_files):
            trash = Path(move.trash_token)
            if trash.is_file():
                target = self._safe_path(move.file_key)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(trash, target)
        Path(operation.manifest_path).unlink(missing_ok=True)

    async def finalize(self, operation: PreparedMediaOperation) -> None:
        async with self._lock:
            await asyncio.to_thread(self._finalize_sync, operation)

    def _finalize_sync(self, operation: PreparedMediaOperation) -> None:
        self._write_manifest(operation, state="committed")
        for move in operation.old_files:
            Path(move.trash_token).unlink(missing_ok=True)
        Path(operation.manifest_path).unlink(missing_ok=True)

    async def discard(self, staged: StagedSiteLogo) -> None:
        await asyncio.to_thread(Path(staged.token).unlink, missing_ok=True)

    async def validate_logo(self, logo: SiteLogoValue) -> bool:
        return await asyncio.to_thread(self._matches_logo, self._safe_path(logo.path), logo.model_dump(mode="json"))

    def pending_manifests(self) -> list[Path]:
        self._ensure_layout_sync()
        return sorted(self.operations_root.glob("*.json"))

    def load_manifest(self, path: Path) -> PreparedMediaOperation:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return PreparedMediaOperation(
            operation_id=payload["operation_id"],
            kind=payload["kind"],
            manifest_path=str(path),
            old_revision=payload["old_revision"],
            new_revision=payload["new_revision"],
            old_logo=payload["old_logo"],
            new_logo=payload["new_logo"],
            target_key=payload["target_key"],
            old_files=tuple(FileMove(**item) for item in payload["old_files"]),
        )

    def _write_manifest(self, operation: PreparedMediaOperation, *, state: str) -> None:
        path = Path(operation.manifest_path)
        payload = asdict(operation)
        payload["state"] = state
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as target:
            json.dump(payload, target, ensure_ascii=True, separators=(",", ":"))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)

    def _existing_logo_keys(self) -> list[str]:
        return [key for key in ("site/logo.png", "site/logo.jpg", "site/logo.webp") if self._safe_path(key).is_file()]

    def _matches_logo(self, path: Path, value: dict[str, Any] | None) -> bool:
        if value is None or not path.is_file() or path.stat().st_size != value.get("file_size"):
            return False
        try:
            image_format = self._validate_image(path)
            extension, mime_type = _FORMAT_POLICY[image_format]
            if path.suffix != f".{extension}" or value.get("mime_type") != mime_type:
                return False
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(_CHUNK_SIZE):
                    digest.update(chunk)
            return digest.hexdigest() == value.get("sha256")
        except OSError, ValueError:
            return False

    def _safe_path(self, file_key: str) -> Path:
        candidate = (self.root / file_key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("settings media path escapes storage root")
        return candidate


__all__ = ["PreparedMediaOperation", "SettingsMediaStore", "StagedSiteLogo"]
