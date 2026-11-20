import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.identifiers import new_uuid7


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid7, sort_order=-1000)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        sort_order=2000,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        sort_order=2001,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="软删除时间，非空表示已进入回收站",
        sort_order=1000,
    )
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="执行软删除的主体 ID",
        sort_order=1001,
    )
    deleted_by_type: Mapped[str | None] = mapped_column(
        # The value is constrained by each soft-deletable model's lifecycle policy.
        String(16),
        nullable=True,
        comment="执行软删除的主体类型",
        sort_order=1002,
    )
    deletion_reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
        comment="软删除原因，可为空",
        sort_order=1003,
    )
