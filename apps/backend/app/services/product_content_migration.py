from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.restricted_html import legacy_text_to_html, restricted_html
from app.db.transaction import transaction_scope
from app.domains.products.repository import ProductRepository


class ProductContentMigration:
    """Bounded, all-or-nothing conversion; caller must explicitly choose the source format."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProductRepository(session)

    async def run(self, ids: list[UUID], *, source: Literal["text", "html"], apply: bool) -> list[UUID]:
        if not ids or len(ids) > 100 or len(set(ids)) != len(ids):
            raise ValueError("必须明确指定 1 至 100 个不重复的商品 ID")
        async with transaction_scope(self.session):
            if apply:
                await self.repository.lock_catalog()
            converted = []
            for product_id in sorted(ids):
                row = await self.repository.get(product_id, lock=apply)
                if row is None or row.description_version != 0:
                    raise ValueError("所选商品不存在或已完成迁移；整批停止")
                content = legacy_text_to_html(row.description) if source == "text" else restricted_html(row.description)
                converted.append((row, content))
            if apply:
                for row, content in converted:
                    row.description = content
                    row.description_version = 1
                    row.revision += 1
                await self.session.flush()
        return ids
