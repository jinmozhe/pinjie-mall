from datetime import UTC, datetime
from uuid import UUID

from app.core.identifiers import new_uuid7
from app.db.models.catalog import (
    CategorySpecAttribute,
    ProductAttributeValue,
    ProductSkuSpecValue,
    ProductSpecAttribute,
    ProductSpecValue,
)
from app.db.models.product import Product, ProductSku

from .catalog_schemas import CandidateAppend, DescriptionSet, DescriptionUpdate, SkuFields, SpecificationSet
from .catalog_service import CatalogService, catalog_conflict, normalized_text, specification_key


class SpecificationService(CatalogService):
    async def require_current_template_match(
        self,
        product: Product,
        adoption: ProductSpecAttribute,
        templates: dict[UUID, CategorySpecAttribute] | None = None,
    ) -> None:
        if adoption.attribute_id is None or adoption.source_category_id is None:
            return
        if adoption.source_category_id != product.category_id:
            raise catalog_conflict("当前商品采用的来源分类已变更，请重新采用或使用规格转换")
        current_templates = (
            {row.attribute_id: row for row in await self.repository.template(product.category_id)}
            if templates is None
            else templates
        )
        template = current_templates.get(adoption.attribute_id)
        if template is None:
            raise catalog_conflict("当前商品采用已不在分类模板中，请重新采用或使用规格转换")
        if (
            adoption.is_variant != template.is_variant
            or adoption.is_required != template.is_required
            or adoption.allow_custom_value != template.allow_custom_value
        ):
            raise catalog_conflict("当前商品采用已与分类模板用途、必填或局部候选规则不一致，请重新采用或使用规格转换")

    async def append_candidates(self, product: Product, adoption_id: UUID, data: CandidateAppend) -> None:
        adoption = next(
            (
                row
                for row in await self.repository.adoptions(product.id)
                if row.id == adoption_id and row.is_current and row.is_variant
            ),
            None,
        )
        if adoption is None:
            raise catalog_conflict("销售采用不属于当前商品")
        await self.require_current_template_match(product, adoption)
        if adoption.attribute_id is not None:
            attribute = await self.require_attribute(adoption.attribute_id)
            if not attribute.is_active or attribute.revision != data.source_attribute_revision:
                raise catalog_conflict("公共属性已变更或停用，请重新读取")
        elif data.source_attribute_revision is not None:
            raise catalog_conflict("商品独有规格没有公共来源版本")
        existing = [
            row
            for row in await self.repository.candidates(product.id)
            if row.adoption_id == adoption.id and row.is_current
        ]
        if len(existing) + len(data.candidates) > 100:
            raise catalog_conflict("每个销售维度最多一百个候选值")
        texts = {row.normalized_value for row in existing}
        standards = {row.value_id for row in existing if row.value_id is not None}
        for item in data.candidates:
            if item.value_id is not None:
                standard = await self.repository.standard_value(item.value_id)
                if standard is None or standard.attribute_id != adoption.attribute_id or not standard.is_active:
                    raise catalog_conflict("标准值归属错误或已停用")
                if standard.id in standards:
                    raise catalog_conflict("标准候选值重复")
                standards.add(standard.id)
                display = standard.name
            else:
                if not adoption.allow_custom_value or item.display_value is None:
                    raise catalog_conflict("当前采用不允许局部候选值")
                display = item.display_value
            normalized = normalized_text(display)
            if not normalized or normalized in texts:
                raise catalog_conflict("候选文本重复或为空")
            texts.add(normalized)
            await self.repository.save_entity(
                ProductSpecValue(
                    id=new_uuid7(),
                    adoption_id=adoption.id,
                    product_id=product.id,
                    attribute_id=adoption.attribute_id,
                    value_id=item.value_id,
                    display_value=display,
                    normalized_value=normalized,
                    is_current=True,
                )
            )

    async def set_descriptions(self, product: Product, data: DescriptionSet) -> None:
        category = next((row for row in await self.repository.categories() if row.id == product.category_id), None)
        if category is None or category.revision != data.category_revision:
            raise catalog_conflict("分类模板版本已变更，请重新读取")
        previous = await self.repository.adoptions(product.id)
        current = [row for row in previous if row.is_current]
        descriptions = {row.id: row for row in current if not row.is_variant}
        variants = [row for row in current if row.is_variant]
        keep_ids = {row.adoption_id for row in data.existing}
        if not keep_ids <= descriptions.keys():
            raise catalog_conflict("描述采用不属于当前商品")
        if len(variants) + len(data.existing) + len(data.added) > 50:
            raise catalog_conflict("商品属性最多五十项")
        templates = {row.attribute_id: row for row in await self.repository.template(product.category_id)}
        retained = variants + [descriptions[key] for key in keep_ids]
        for adoption in retained:
            await self.require_current_template_match(product, adoption, templates)
        supplied = {row.attribute_id for row in retained} | {row.attribute_id for row in data.added}
        if any(row.is_required and row.attribute_id not in supplied for row in templates.values()):
            raise catalog_conflict("不能移除分类模板必填属性")
        if any(row.is_required and row.id not in keep_ids for row in descriptions.values()):
            raise catalog_conflict("不能移除已冻结的必填描述属性")
        version = max((row.adoption_version for row in previous), default=0) + 1
        additions: list[tuple[ProductSpecAttribute, str | list[str] | None, dict[str, str]]] = []
        names = {row.name_snapshot for row in retained}
        public_ids = {row.attribute_id for row in retained if row.attribute_id is not None}
        for definition in data.added:
            adoption = await self.make_adoption(
                product.id,
                product.category_id,
                category.revision,
                version,
                definition,
                templates.get(definition.attribute_id) if definition.attribute_id is not None else None,
            )
            if adoption.name_snapshot in names or (
                adoption.attribute_id is not None and adoption.attribute_id in public_ids
            ):
                raise catalog_conflict("商品当前属性名称或公共属性不能重复")
            names.add(adoption.name_snapshot)
            if adoption.attribute_id is not None:
                public_ids.add(adoption.attribute_id)
            value, display = await self.description_value(adoption, definition.value)
            additions.append((adoption, value, display))
        for row in descriptions.values():
            if row.id not in keep_ids:
                row.is_current = False
                await self.repository.save_entity(row)
        saved = {row.adoption_id: row for row in await self.repository.descriptions(product.id)}
        for item in data.existing:
            old = saved.get(item.adoption_id)
            serialized = [str(value) for value in item.value] if isinstance(item.value, list) else item.value
            if serialized != (old.value if old is not None else None):
                await self.replace_description(
                    product,
                    item.adoption_id,
                    DescriptionUpdate(revision=data.revision, value=item.value),
                    templates,
                )
        # Existing edits may have advanced the adoption version. New definitions share a fresh version.
        version = max((row.adoption_version for row in await self.repository.adoptions(product.id)), default=0) + 1
        for adoption, value, display in additions:
            adoption.adoption_version = version
            await self.repository.save_entity(adoption)
            if value is not None:
                await self.repository.save_entity(
                    ProductAttributeValue(
                        adoption_id=adoption.id,
                        product_id=product.id,
                        attribute_id=adoption.attribute_id,
                        value=value,
                        display_snapshot=display,
                        schema_version=1,
                    )
                )

    async def build_specifications(self, product: Product, data: SpecificationSet) -> None:
        category = next((row for row in await self.repository.categories() if row.id == product.category_id), None)
        if category is None or category.revision != data.category_revision:
            raise catalog_conflict("分类及模板版本已变更，请重新读取")
        templates = {row.attribute_id: row for row in await self.repository.template(product.category_id)}
        supplied = {row.attribute_id for row in data.attributes if row.attribute_id is not None}
        if any(row.is_required and row.attribute_id not in supplied for row in templates.values()):
            raise catalog_conflict("商品缺少分类模板要求的属性")
        previous = await self.repository.adoptions(product.id)
        version = max((row.adoption_version for row in previous), default=0) + 1
        aliases: dict[tuple[str, str], UUID] = {}
        names: set[str] = set()
        for definition in data.attributes:
            adoption = await self.make_adoption(
                product.id,
                product.category_id,
                category.revision,
                version,
                definition,
                templates.get(definition.attribute_id) if definition.attribute_id is not None else None,
            )
            if adoption.name_snapshot in names:
                raise catalog_conflict("商品当前属性名称不能重复")
            names.add(adoption.name_snapshot)
            await self.repository.save_entity(adoption)
            seen_text: set[str] = set()
            seen_standard: set[UUID] = set()
            for candidate in definition.candidates:
                if candidate.value_id is not None:
                    standard = await self.repository.standard_value(candidate.value_id)
                    if standard is None or standard.attribute_id != adoption.attribute_id or not standard.is_active:
                        raise catalog_conflict("销售标准值不存在、归属错误或已停用")
                    if standard.id in seen_standard:
                        raise catalog_conflict("同采用下标准值不能重复")
                    seen_standard.add(standard.id)
                    display = standard.name
                else:
                    if not adoption.allow_custom_value or candidate.display_value is None:
                        raise catalog_conflict("此属性采用不允许局部候选值")
                    display = candidate.display_value
                normalized = normalized_text(display)
                if not normalized or normalized in seen_text:
                    raise catalog_conflict("同采用下候选值文本不能重复或为空")
                seen_text.add(normalized)
                row = ProductSpecValue(
                    id=new_uuid7(),
                    adoption_id=adoption.id,
                    product_id=product.id,
                    attribute_id=adoption.attribute_id,
                    value_id=candidate.value_id,
                    display_value=display,
                    normalized_value=normalized,
                    is_current=True,
                )
                await self.repository.save_entity(row)
                aliases[definition.key, candidate.key] = row.id
            if not adoption.is_variant:
                value, display_snapshot = await self.description_value(adoption, definition.value)
                if value is not None:
                    await self.repository.save_entity(
                        ProductAttributeValue(
                            adoption_id=adoption.id,
                            product_id=product.id,
                            attribute_id=adoption.attribute_id,
                            value=value,
                            schema_version=1,
                            display_snapshot=display_snapshot,
                        )
                    )
        variant_mode = any(item.is_variant for item in data.attributes)
        for index, sku in enumerate(data.skus):
            selected = [aliases[key, value] for key, value in sku.selections.items()]
            await self.insert_sku(product.id, sku, selected, index + 1 if variant_mode else 0)

    async def combination(
        self, product_id: UUID, selected: list[UUID]
    ) -> tuple[str, dict[str, str], list[ProductSpecValue]]:
        adoptions = {
            row.id: row for row in await self.repository.adoptions(product_id) if row.is_current and row.is_variant
        }
        values = {row.id: row for row in await self.repository.candidates(product_id) if row.is_current}
        candidates: list[ProductSpecValue] = []
        for value_id in selected:
            candidate = values.get(value_id)
            if candidate is None or candidate.adoption_id not in adoptions:
                raise catalog_conflict("规格值不属于本商品当前销售采用")
            candidates.append(candidate)
        if len(candidates) != len(adoptions) or {row.adoption_id for row in candidates} != set(adoptions):
            raise catalog_conflict("SKU 必须对全部当前销售维度各选择一个值")
        pairs = [
            (adoptions[row.adoption_id].attribute_id or row.adoption_id, row.value_id, row.id) for row in candidates
        ]
        display = {adoptions[row.adoption_id].name_snapshot: row.display_value for row in candidates}
        return specification_key(pairs), display, candidates

    @staticmethod
    def set_sku_fields(row: ProductSku, data: SkuFields) -> None:
        row.code, row.price, row.cost_price, row.market_price = (
            data.code,
            data.price,
            data.cost_price,
            data.market_price,
        )
        row.wholesale_prices = [tier.model_dump(mode="json") for tier in data.wholesale_prices]
        row.weight_grams, row.is_active = data.weight_grams, data.is_active

    async def insert_sku(self, product_id: UUID, data: SkuFields, selected: list[UUID], sku_no: int) -> ProductSku:
        if await self.repository.code_exists(data.code):
            raise catalog_conflict("SKU 编码已经使用，归档货品编码也不能重用")
        key, display, candidates = await self.combination(product_id, selected)
        if any(
            row.archived_at is None and row.specification_key == key for row in await self.repository.skus(product_id)
        ):
            raise catalog_conflict("当前 SKU 规格组合已存在")
        row = ProductSku(
            id=new_uuid7(), product_id=product_id, sku_no=sku_no, specification_key=key, specifications=display
        )
        self.set_sku_fields(row, data)
        await self.repository.save(row)
        for candidate in candidates:
            await self.repository.save_entity(
                ProductSkuSpecValue(
                    product_id=product_id,
                    sku_id=row.id,
                    adoption_id=candidate.adoption_id,
                    attribute_id=candidate.attribute_id,
                    spec_value_id=candidate.id,
                )
            )
        return row

    async def retire_specifications(self, product_id: UUID) -> list[UUID]:
        now = datetime.now(UTC)
        retired: list[UUID] = []
        for sku in await self.repository.skus(product_id):
            if sku.archived_at is None:
                sku.archived_at = now
                retired.append(sku.id)
        for adoption in await self.repository.adoptions(product_id):
            adoption.is_current = False
        for candidate in await self.repository.candidates(product_id):
            candidate.is_current = False
        await self.repository.flush()
        return sorted(retired)

    async def sku_is_available(
        self, sku: ProductSku, adoptions: list[ProductSpecAttribute], selections: list[ProductSkuSpecValue]
    ) -> bool:
        if sku.archived_at is not None or not sku.is_active:
            return False
        for adoption in adoptions:
            if not adoption.is_current:
                continue
            if adoption.attribute_id is not None:
                attribute = await self.repository.attribute(adoption.attribute_id)
                if attribute is None or not attribute.is_active:
                    return False
        candidates = {row.id: row for row in await self.repository.candidates(sku.product_id)}
        for selection in selections:
            if selection.sku_id != sku.id:
                continue
            candidate = candidates.get(selection.spec_value_id)
            if candidate is None or not candidate.is_current:
                return False
            if candidate.value_id is not None:
                standard = await self.repository.standard_value(candidate.value_id)
                if standard is None or not standard.is_active:
                    return False
        return True

    async def replace_description(
        self,
        product: Product,
        adoption_id: UUID,
        data: DescriptionUpdate,
        templates: dict[UUID, CategorySpecAttribute] | None = None,
    ) -> None:
        all_adoptions = await self.repository.adoptions(product.id)
        previous = next(
            (row for row in all_adoptions if row.id == adoption_id and row.is_current and not row.is_variant), None
        )
        if previous is None:
            raise catalog_conflict("描述属性不属于当前商品采用")
        await self.require_current_template_match(product, previous, templates)
        # 更新生成新采用，原定义和原值保留，不覆盖历史快照。
        copied = {
            column.name: getattr(previous, column.name)
            for column in previous.__table__.columns
            if column.name not in {"id", "created_at", "is_current", "adoption_version"}
        }
        new = ProductSpecAttribute(
            id=new_uuid7(),
            **copied,
            adoption_version=max(row.adoption_version for row in all_adoptions) + 1,
            is_current=True,
        )
        value, display = await self.description_value(new, data.value)
        previous.is_current = False
        await self.repository.save_entity(previous)
        await self.repository.save_entity(new)
        if value is not None:
            await self.repository.save_entity(
                ProductAttributeValue(
                    adoption_id=new.id,
                    product_id=product.id,
                    attribute_id=new.attribute_id,
                    value=value,
                    display_snapshot=display,
                    schema_version=1,
                )
            )
