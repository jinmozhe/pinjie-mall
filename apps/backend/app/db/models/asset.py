import uuid

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("uploader_type IN ('admin', 'user', 'system')", name="ck_assets_uploader_type"),
        CheckConstraint("storage_driver IN ('local')", name="ck_assets_storage_driver"),
        CheckConstraint("file_size > 0", name="ck_assets_file_size_positive"),
        CheckConstraint(
            "(width IS NULL AND height IS NULL AND frame_count IS NULL) OR "
            "(width IS NOT NULL AND height IS NOT NULL AND frame_count IS NOT NULL "
            "AND width > 0 AND height > 0 AND frame_count > 0)",
            name="ck_assets_image_metadata",
        ),
        CheckConstraint("char_length(file_hash) = 64", name="ck_assets_file_hash_length"),
        UniqueConstraint(
            "uploader_type",
            "uploader_id",
            "scene",
            "file_hash",
            name="uq_assets_uploader_scene_hash",
        ),
        Index("ix_assets_created", "created_at"),
        Index("ix_assets_scene_created", "scene", "created_at"),
        Index("ix_assets_uploader_created", "uploader_type", "uploader_id", "created_at"),
        {"comment": "统一文件与多媒体资产元数据"},
    )

    uploader_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="上传主体类型")
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, comment="上传主体 ID，系统任务可为空")
    storage_driver: Mapped[str] = mapped_column(String(20), nullable=False, comment="存储驱动代码")
    file_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, comment="存储相对文件键")
    original_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="上传原始文件名")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, comment="探测得到的真实 MIME 类型")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件字节数")
    width: Mapped[int | None] = mapped_column(Integer, comment="按 EXIF 方向解释的图片宽度，像素")
    height: Mapped[int | None] = mapped_column(Integer, comment="按 EXIF 方向解释的图片高度，像素")
    frame_count: Mapped[int | None] = mapped_column(Integer, comment="完整解码确认的图片帧数")
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="SHA-256 内容哈希")
    url: Mapped[str] = mapped_column(String(1000), nullable=False, comment="公开访问 URL 或站内路径")
    scene: Mapped[str] = mapped_column(String(50), nullable=False, comment="受控文件使用场景")


__all__ = ["Asset"]
