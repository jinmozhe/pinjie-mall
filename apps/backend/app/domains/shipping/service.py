from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.shipping import ShippingTemplate

from .repository import ShippingRepository
from .schemas import (
    FreightQuote,
    FreightQuoteInput,
    ShippingTemplateInput,
    ShippingTemplateRead,
    ShippingTemplateUpdate,
    calculate_freight,
)


class ShippingService:
    """领域命令由应用层拥有事务，不在这里提交。"""

    def __init__(self, repository: ShippingRepository) -> None:
        self.repository = repository

    async def read(self, template_id: UUID, *, lock: bool = False) -> ShippingTemplateRead:
        template = await self.repository.get(template_id, lock=lock)
        if template is None:
            raise AppException(status_code=404, code=ErrorCode.SHIPPING_NOT_FOUND, message="运费模板不存在")
        return ShippingTemplateRead.model_validate(template)

    async def require_active(self, template_id: UUID) -> None:
        template = await self.read(template_id, lock=True)
        if not template.is_active:
            raise AppException(status_code=409, code=ErrorCode.SHIPPING_INACTIVE, message="运费模板已停用")

    async def page(self, page: int, page_size: int) -> PageResult[ShippingTemplateRead]:
        rows, total = await self.repository.page(page, page_size)
        return PageResult[ShippingTemplateRead].create(
            items=[ShippingTemplateRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def create(self, data: ShippingTemplateInput, actor_id: UUID) -> ShippingTemplateRead:
        template = ShippingTemplate(
            id=new_uuid7(),
            **data.model_dump(exclude={"regions"}),
            regions=[region.model_dump(mode="json") for region in data.regions],
            revision=1,
            updated_by_id=actor_id,
        )
        await self.repository.save(template)
        return ShippingTemplateRead.model_validate(template)

    async def update(self, template_id: UUID, data: ShippingTemplateUpdate, actor_id: UUID) -> ShippingTemplateRead:
        template = await self.repository.get(template_id, lock=True)
        if template is None:
            raise AppException(status_code=404, code=ErrorCode.SHIPPING_NOT_FOUND, message="运费模板不存在")
        if data.revision != template.revision:
            raise AppException(
                status_code=409, code=ErrorCode.SHIPPING_REVISION_CONFLICT, message="运费模板已变更，请重新读取"
            )
        template.name = data.name
        template.pricing_method = data.pricing_method
        template.regions = [region.model_dump(mode="json") for region in data.regions]
        template.free_shipping_threshold = data.free_shipping_threshold
        template.excluded_provinces = data.excluded_provinces
        template.is_active = data.is_active
        template.updated_by_id = actor_id
        template.revision += 1
        await self.repository.save(template)
        return ShippingTemplateRead.model_validate(template)

    async def quote(self, template_id: UUID, data: FreightQuoteInput) -> FreightQuote:
        template = await self.read(template_id)
        try:
            freight = calculate_freight(template, data)
        except ValueError as exc:
            raise AppException(status_code=409, code=ErrorCode.SHIPPING_QUOTE_REJECTED, message=str(exc)) from exc
        return FreightQuote(
            template_id=template.id, revision=template.revision, freight=freight, free_shipping=freight == 0
        )
