import type {
  AdoptionInput,
  AdoptionRead,
  AttributeRead,
  AttributeValidationInput,
  CandidateInput,
  NewSkuInput,
  ProductRead,
  SkuRead,
  TemplateItem,
} from "@pinjie/api-client";
import { MinusCircleOutlined, PlusOutlined } from "@ant-design/icons";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Checkbox,
  Divider,
  Flex,
  Form,
  Input,
  InputNumber,
  Select,
  Skeleton,
  Tag,
} from "antd";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";

import { commerceApi } from "@/lib/api/commerce";

type DraftSku = {
  code?: string;
  cost_price?: string | number | null;
  enabled?: boolean;
  initial_quantity?: number;
  is_active?: boolean;
  market_price?: string | number | null;
  price?: string | number;
  selections: Record<string, string>;
  weight_grams?: number | null;
};

type CustomDescription = {
  decimal_places?: number;
  is_required?: boolean;
  max?: string | number;
  max_length?: number;
  min?: string | number;
  name?: string;
  unit?: string;
  value?: string;
  value_type?: "number" | "text";
};

type FormValues = {
  custom?: CustomDescription[];
  descriptions?: Record<string, string | string[] | undefined>;
  selected?: Record<string, boolean | undefined>;
  skus?: DraftSku[];
  variants?: Record<string, string[] | undefined>;
};

type DraftDimension = {
  candidates: Array<{ key: string; label: string }>;
  key: string;
  label: string;
};

export type ProductSpecificationPayload = {
  attributes: AdoptionInput[];
  categoryRevision: number;
  skus: NewSkuInput[];
};

export type ProductSpecificationFormHandle = {
  validate: () => Promise<ProductSpecificationPayload>;
};

type Props = {
  categoryId?: string;
  existingProduct?: ProductRead | null;
  mode: "create" | "conversion";
};

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function descriptionValue(value: unknown): string | string[] | null {
  if (Array.isArray(value)) return asStringArray(value).length ? asStringArray(value) : null;
  if (typeof value !== "string") return null;
  return value.trim() ? value : null;
}

function standardCandidateKey(valueId: string): string {
  return `std-${valueId}`;
}

function selectionKey(selections: Record<string, string>): string {
  return Object.entries(selections)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([attribute, value]) => `${attribute}=${value}`)
    .join("|");
}

function combinations(dimensions: DraftDimension[]): Record<string, string>[] {
  if (!dimensions.length) return [{}];
  if (dimensions.some((dimension) => !dimension.candidates.length)) return [];
  return dimensions.reduce<Record<string, string>[]>(
    (result, dimension) => result.flatMap((current) => dimension.candidates.map((candidate) => ({
      ...current,
      [dimension.key]: candidate.key,
    }))).slice(0, 101),
    [{}],
  );
}

function candidateInputs(attribute: AttributeRead, values: string[], allowCustom: boolean): CandidateInput[] {
  const seen = new Set<string>();
  const candidates: CandidateInput[] = [];
  for (const [index, raw] of values.entries()) {
    const value = raw.trim();
    if (!value) continue;
    if (value.startsWith("std:")) {
      const valueId = value.slice(4);
      if (!valueId || seen.has(`std:${valueId}`)) continue;
      seen.add(`std:${valueId}`);
      candidates.push({ key: standardCandidateKey(valueId), value_id: valueId });
      continue;
    }
    if (!allowCustom) continue;
    const normalized = value.toLocaleLowerCase();
    if (seen.has(`custom:${normalized}`)) continue;
    seen.add(`custom:${normalized}`);
    candidates.push({ key: `custom-${attribute.id.slice(0, 8)}-${index + 1}`, display_value: value });
  }
  return candidates;
}

function customValidation(row: CustomDescription): AttributeValidationInput {
  if (row.value_type === "number") {
    const decimalPlaces = Number(row.decimal_places);
    const min = row.min === undefined || row.min === "" ? undefined : String(row.min);
    const max = row.max === undefined || row.max === "" ? undefined : String(row.max);
    if (!Number.isInteger(decimalPlaces) || decimalPlaces < 0 || decimalPlaces > 6 || min === undefined || max === undefined) {
      throw new Error("数值自定义属性需要填写精度、最小值和最大值");
    }
    return { schema_version: 1, decimal_places: decimalPlaces, min, max };
  }
  const maxLength = Number(row.max_length);
  if (!Number.isInteger(maxLength) || maxLength < 1 || maxLength > 20000) {
    throw new Error("文本自定义属性需要填写 1 至 20000 的最大长度");
  }
  return { schema_version: 1, max_length: maxLength };
}

function legacyAdoption(adoption: AdoptionRead, index: number, attribute?: AttributeRead): AdoptionInput {
  const key = `legacy-${adoption.id}`;
  const candidates: CandidateInput[] = (adoption.candidates ?? []).map((candidate, candidateIndex) => (
    candidate.value_id
      ? { key: `legacy-${candidate.id}`, value_id: candidate.value_id }
      : { key: `legacy-${candidate.id}`, display_value: candidate.display_value || `自定义值${candidateIndex + 1}` }
  ));
  if (adoption.attribute_id) {
    if (!attribute) throw new Error("已有公共属性尚未加载完成，无法转换");
    return {
      key,
      attribute_id: adoption.attribute_id,
      source_attribute_revision: attribute.revision,
      is_variant: adoption.is_variant,
      is_required: adoption.is_required,
      candidates,
      value: descriptionValue(adoption.value),
    };
  }
  const valueType = adoption.value_type_snapshot;
  if (valueType !== "text" && valueType !== "number" && valueType !== "select" && valueType !== "multi_select") {
    throw new Error(`已有属性 ${index + 1} 的类型无效`);
  }
  return {
    key,
    name: adoption.name_snapshot,
    value_type: valueType,
    unit: adoption.unit_snapshot,
    validation: adoption.validation_snapshot as AttributeValidationInput,
    is_variant: adoption.is_variant,
    is_required: adoption.is_required,
    candidates,
    value: descriptionValue(adoption.value),
  };
}

export const ProductSpecificationForm = forwardRef<ProductSpecificationFormHandle, Props>(function ProductSpecificationForm(
  { categoryId, existingProduct, mode },
  ref,
) {
  // 规格字段属于外层商品表单，避免嵌套 HTML form 导致校验和提交状态分离。
  const form = Form.useFormInstance<FormValues>();
  const initialized = useRef<string | undefined>(undefined);
  const templateQuery = useQuery({
    queryKey: ["commerce-category-template", categoryId],
    queryFn: () => commerceApi.categoryTemplate(categoryId!),
    enabled: Boolean(categoryId),
  });
  const template = templateQuery.data;
  const currentAdoptions = useMemo(
    () => (existingProduct?.attributes ?? []).filter((adoption) => adoption.is_current),
    [existingProduct?.attributes],
  );
  const requestedAttributeIds = useMemo(() => {
    const ids = new Set(template?.attributes.map((item) => item.attribute_id) ?? []);
    for (const adoption of currentAdoptions) if (adoption.attribute_id) ids.add(adoption.attribute_id);
    return [...ids].sort();
  }, [currentAdoptions, template?.attributes]);
  const attributeQueries = useQueries({
    queries: requestedAttributeIds.map((id) => ({
      queryKey: ["commerce-spec-attribute", id],
      queryFn: () => commerceApi.attribute(id),
      enabled: Boolean(categoryId),
    })),
  });
  const attributes = useMemo(
    () => attributeQueries.flatMap((query) => query.data ? [query.data] : []),
    [attributeQueries],
  );
  const attributesById = useMemo(() => new Map(attributes.map((attribute) => [attribute.id, attribute])), [attributes]);
  const enumAttributeIds = useMemo(
    () => attributes.filter((attribute) => attribute.value_type === "select" || attribute.value_type === "multi_select").map((attribute) => attribute.id),
    [attributes],
  );
  const valueQueries = useQueries({
    queries: enumAttributeIds.map((id) => ({
      queryKey: ["commerce-spec-attribute-values", id],
      queryFn: () => commerceApi.attributeValues(id),
      enabled: Boolean(categoryId),
    })),
  });
  const valuesByAttribute = useMemo(
    () => new Map(enumAttributeIds.map((id, index) => [id, valueQueries[index]?.data ?? []])),
    [enumAttributeIds, valueQueries],
  );
  const templateRows = useMemo(
    () => (template?.attributes ?? []).flatMap((item) => {
      const attribute = attributesById.get(item.attribute_id);
      return attribute ? [{ item, attribute }] : [];
    }),
    [attributesById, template?.attributes],
  );
  const templateIds = useMemo(() => new Set(templateRows.map(({ attribute }) => attribute.id)), [templateRows]);
  const legacyRows = useMemo(
    () => currentAdoptions.filter((adoption) => !adoption.attribute_id || !templateIds.has(adoption.attribute_id)),
    [currentAdoptions, templateIds],
  );
  const selected = Form.useWatch("selected", form) ?? {};
  const variants = Form.useWatch("variants", form) ?? {};

  const allAttributesLoaded = requestedAttributeIds.length === attributes.length;
  const allValuesLoaded = enumAttributeIds.length === valueQueries.length && valueQueries.every((query) => query.isSuccess);
  const allDefinitionsLoaded = allAttributesLoaded && allValuesLoaded;
  const initializationKey = `${categoryId ?? ""}:${template?.revision ?? ""}:${requestedAttributeIds.join(",")}:${existingProduct?.id ?? ""}:${existingProduct?.revision ?? ""}`;
  useEffect(() => {
    if (!template || !allDefinitionsLoaded || initialized.current === initializationKey) return;
    const existingByAttribute = new Map(
      currentAdoptions.filter((adoption): adoption is AdoptionRead & { attribute_id: string } => Boolean(adoption.attribute_id)).map((adoption) => [adoption.attribute_id, adoption]),
    );
    const selectedInitial: Record<string, boolean> = {};
    const descriptionsInitial: Record<string, string | string[]> = {};
    const variantsInitial: Record<string, string[]> = {};
    for (const { item, attribute } of templateRows) {
      const existing = existingByAttribute.get(attribute.id);
      selectedInitial[attribute.id] = Boolean(existing) || Boolean(item.is_required);
      if (existing?.is_variant) {
        variantsInitial[attribute.id] = (existing.candidates ?? []).map((candidate) => candidate.value_id ? `std:${candidate.value_id}` : candidate.display_value);
      } else if (existing?.value) {
        descriptionsInitial[attribute.id] = existing.value;
      }
    }
    form.setFieldsValue({
      selected: selectedInitial,
      descriptions: descriptionsInitial,
      variants: variantsInitial,
      custom: [],
      skus: [],
    });
    initialized.current = initializationKey;
  }, [allDefinitionsLoaded, currentAdoptions, form, initializationKey, template, templateRows]);

  const legacyDimensions = useMemo<DraftDimension[]>(
    () => legacyRows.filter((adoption) => adoption.is_variant).map((adoption) => ({
      key: `legacy-${adoption.id}`,
      label: adoption.name_snapshot,
      candidates: (adoption.candidates ?? []).map((candidate) => ({ key: `legacy-${candidate.id}`, label: candidate.display_value })),
    })),
    [legacyRows],
  );
  const templateDimensions = useMemo<DraftDimension[]>(
    () => templateRows.flatMap(({ item, attribute }) => {
      if (!item.is_variant || !selected[attribute.id]) return [];
      const candidates = candidateInputs(attribute, asStringArray(variants[attribute.id]), Boolean(item.allow_custom_value))
        .map((candidate) => ({ key: candidate.key, label: candidate.value_id ? valuesByAttribute.get(attribute.id)?.find((value) => value.id === candidate.value_id)?.name ?? candidate.value_id : candidate.display_value ?? "" }));
      return [{ key: `template-${attribute.id}`, label: attribute.name, candidates }];
    }),
    [selected, templateRows, valuesByAttribute, variants],
  );
  const dimensions = useMemo(() => [...templateDimensions, ...legacyDimensions], [legacyDimensions, templateDimensions]);
  const draftCombinations = useMemo(() => combinations(dimensions), [dimensions]);
  const existingSkuBySelection = useMemo(() => {
    const aliases = new Map<string, { dimension: string; value: string }>();
    for (const { attribute } of templateRows) {
      const adoption = currentAdoptions.find((row) => row.attribute_id === attribute.id && row.is_variant);
      for (const candidate of adoption?.candidates ?? []) {
        aliases.set(candidate.id, {
          dimension: `template-${attribute.id}`,
          value: candidate.value_id ? standardCandidateKey(candidate.value_id) : `custom-${attribute.id.slice(0, 8)}-${(adoption?.candidates ?? []).indexOf(candidate) + 1}`,
        });
      }
    }
    for (const adoption of legacyRows.filter((row) => row.is_variant)) {
      for (const candidate of adoption.candidates ?? []) aliases.set(candidate.id, { dimension: `legacy-${adoption.id}`, value: `legacy-${candidate.id}` });
    }
    const result = new Map<string, SkuRead>();
    for (const sku of existingProduct?.skus ?? []) {
      const selections: Record<string, string> = {};
      for (const candidateId of sku.spec_value_ids ?? []) {
        const alias = aliases.get(candidateId);
        if (alias) selections[alias.dimension] = alias.value;
      }
      if (Object.keys(selections).length === dimensions.length) result.set(selectionKey(selections), sku);
    }
    return result;
  }, [currentAdoptions, dimensions.length, existingProduct?.skus, legacyRows, templateRows]);
  const combinationSignature = useMemo(() => JSON.stringify(draftCombinations), [draftCombinations]);
  useEffect(() => {
    if (!initialized.current || draftCombinations.length > 100) return;
    const existingDrafts = new Map((form.getFieldValue("skus") ?? []).map((sku: DraftSku) => [selectionKey(sku.selections), sku]));
    form.setFieldValue("skus", draftCombinations.map((selections) => {
      const key = selectionKey(selections);
      const retained = existingDrafts.get(key);
      if (retained) return { ...retained, selections };
      const prior = existingSkuBySelection.get(key);
      return {
        selections,
        enabled: prior ? true : mode === "create",
        code: prior?.code ?? "",
        price: prior?.price ?? "0",
        cost_price: prior?.cost_price ?? null,
        market_price: prior?.market_price ?? null,
        weight_grams: prior?.weight_grams ?? null,
        is_active: prior?.is_active ?? true,
        initial_quantity: 0,
      };
    }));
  }, [combinationSignature, draftCombinations, existingSkuBySelection, form, mode]);

  useImperativeHandle(ref, () => ({
    validate: async () => {
      if (!categoryId || !template || !allDefinitionsLoaded) throw new Error("请等待分类模板与公共属性加载完成");
      await form.validateFields();
      // 校验结果只包含注册字段，完整 store 才保留 SKU 的规格映射及转换元数据。
      const values: FormValues = form.getFieldsValue(true);
      const attributesPayload: AdoptionInput[] = [];
      const activeDimensions: DraftDimension[] = [];
      for (const { item, attribute } of templateRows) {
        const adopted = Boolean(values.selected?.[attribute.id]);
        if (item.is_required && !adopted) throw new Error(`${attribute.name} 是分类模板必填属性`);
        if (!adopted) continue;
        const key = `template-${attribute.id}`;
        if (item.is_variant) {
          const candidates = candidateInputs(attribute, asStringArray(values.variants?.[attribute.id]), Boolean(item.allow_custom_value));
          if (!candidates.length) throw new Error(`${attribute.name} 至少需要一个销售候选值`);
          attributesPayload.push({
            key,
            attribute_id: attribute.id,
            source_attribute_revision: attribute.revision,
            is_variant: true,
            is_required: item.is_required,
            candidates,
          });
          activeDimensions.push({ key, label: attribute.name, candidates: candidates.map((candidate) => ({ key: candidate.key, label: candidate.display_value ?? candidate.value_id ?? "" })) });
          continue;
        }
        attributesPayload.push({
          key,
          attribute_id: attribute.id,
          source_attribute_revision: attribute.revision,
          is_variant: false,
          is_required: item.is_required,
          value: descriptionValue(values.descriptions?.[attribute.id]),
        });
      }
      for (const [index, adoption] of legacyRows.entries()) {
        const definition = legacyAdoption(
          adoption,
          index,
          adoption.attribute_id ? attributesById.get(adoption.attribute_id) : undefined,
        );
        attributesPayload.push(definition);
        if (definition.is_variant) activeDimensions.push({
          key: definition.key,
          label: definition.name ?? adoption.name_snapshot,
          candidates: (definition.candidates ?? []).map((candidate) => ({ key: candidate.key, label: candidate.display_value ?? candidate.value_id ?? "" })),
        });
      }
      const seenNames = new Set(attributesPayload.map((attribute) => attribute.name?.trim() || attribute.attribute_id || ""));
      for (const [index, row] of (values.custom ?? []).entries()) {
        const name = row.name?.trim();
        if (!name || !row.value_type) throw new Error(`第 ${index + 1} 个自定义描述属性不完整`);
        if (seenNames.has(name)) throw new Error(`描述属性名称重复：${name}`);
        seenNames.add(name);
        attributesPayload.push({
          key: `custom-description-${index + 1}`,
          name,
          value_type: row.value_type,
          unit: row.value_type === "number" ? row.unit?.trim() || undefined : undefined,
          validation: customValidation(row),
          is_variant: false,
          is_required: Boolean(row.is_required),
          value: descriptionValue(row.value),
        });
      }
      if (activeDimensions.length > 10) throw new Error("销售规格最多十个维度");
      const rows = (values.skus ?? []).filter((sku) => sku.enabled);
      if (!rows.length) throw new Error("至少保留一个实际 SKU 组合");
      if (rows.length > 100) throw new Error("SKU 数量不能超过一百个");
      const skuCodes = new Set<string>();
      const seenCombinations = new Set<string>();
      const skus = rows.map((row, index) => {
        const code = row.code?.trim();
        if (!code) throw new Error(`第 ${index + 1} 个 SKU 缺少编码`);
        if (!/^[A-Za-z0-9_-]+$/.test(code)) throw new Error(`第 ${index + 1} 个 SKU 编码只能包含字母、数字、下划线和连字符`);
        if (skuCodes.has(code)) throw new Error("SKU 编码不能重复");
        skuCodes.add(code);
        if (
          !row.selections
          || Object.keys(row.selections).length !== activeDimensions.length
          || activeDimensions.some((dimension) => !dimension.candidates.some((candidate) => candidate.key === row.selections[dimension.key]))
        ) {
          throw new Error(`第 ${index + 1} 个 SKU 规格组合不完整或已失效，请重新选择销售规格`);
        }
        const key = selectionKey(row.selections);
        if (seenCombinations.has(key)) throw new Error("SKU 规格组合不能重复");
        seenCombinations.add(key);
        return {
          code,
          price: row.price ?? "0",
          cost_price: row.cost_price ?? null,
          market_price: row.market_price ?? null,
          weight_grams: row.weight_grams ?? null,
          is_active: row.is_active ?? true,
          selections: row.selections,
          initial_quantity: Number(row.initial_quantity ?? 0),
        } satisfies NewSkuInput;
      });
      return { attributes: attributesPayload, skus, categoryRevision: template.revision };
    },
  }), [allDefinitionsLoaded, attributesById, categoryId, form, legacyRows, template, templateRows]);

  if (!categoryId) return <Alert showIcon type="info" title="选择分类后加载该分类的规格模板" />;
  if (templateQuery.isError || attributeQueries.some((query) => query.isError) || valueQueries.some((query) => query.isError)) {
    return <Alert showIcon type="error" title="规格模板或公共属性加载失败" description="请关闭后重新打开商品编辑，避免使用不完整的属性定义保存。" />;
  }
  if (templateQuery.isLoading || !allDefinitionsLoaded) return <Skeleton active paragraph={{ rows: 6 }} />;

  return (
    <>
      <Divider>分类属性与销售规格</Divider>
      {!templateRows.length && <Alert showIcon type="info" title="该分类尚未配置属性模板，将创建无销售规格的默认 SKU。" />}
      <Flex vertical gap={12}>
        {templateRows.map(({ item, attribute }) => {
          const adopted = Boolean(selected[attribute.id]);
          const options = (valuesByAttribute.get(attribute.id) ?? []).filter((value) => value.is_active).map((value) => ({
            value: item.is_variant ? `std:${value.id}` : value.id,
            label: value.name,
          }));
          return (
            <div key={attribute.id} className="catalog-specification-row">
              <Flex align="center" gap={8} wrap>
                <Form.Item name={["selected", attribute.id]} valuePropName="checked" noStyle initialValue={item.is_required}>
                  <Checkbox disabled={item.is_required}>{attribute.name}</Checkbox>
                </Form.Item>
                <Tag color={item.is_variant ? "blue" : "default"}>{item.is_variant ? "销售规格" : "描述属性"}</Tag>
                {item.is_required && <Tag color="error">必填</Tag>}
                {attribute.unit && <Tag>{attribute.unit}</Tag>}
              </Flex>
              {adopted && item.is_variant && (
                <Form.Item name={["variants", attribute.id]} label="销售候选值" rules={[{ required: true, type: "array", min: 1, message: "至少选择一个候选值" }]} className="mt-8 mb-0">
                  <Select mode={item.allow_custom_value ? "tags" : "multiple"} options={options} placeholder={item.allow_custom_value ? "选择标准值，或输入允许的自定义值" : "选择标准候选值"} />
                </Form.Item>
              )}
              {adopted && !item.is_variant && <DescriptionField attribute={attribute} item={item} values={valuesByAttribute.get(attribute.id) ?? []} />}
            </div>
          );
        })}
      </Flex>

      <Divider>商品自定义描述属性</Divider>
      <Form.List name="custom">
        {(fields, actions) => (
          <Flex vertical gap={8}>
            {fields.map((field) => <CustomDescriptionRow key={field.key} fieldName={field.name} onRemove={() => actions.remove(field.name)} />)}
            <Button icon={<PlusOutlined />} onClick={() => actions.add({ value_type: "text", max_length: 200, is_required: false })}>新增自定义描述属性</Button>
          </Flex>
        )}
      </Form.List>

      <Divider>实际 SKU 组合</Divider>
      {draftCombinations.length > 100 ? (
        <Alert showIcon type="error" title="当前候选值会生成超过 100 个组合，请减少候选值后再创建 SKU。" />
      ) : !draftCombinations.length ? (
        <Alert showIcon type="warning" title="每个已采用的销售规格至少选择一个候选值后，才能生成 SKU 组合。" />
      ) : (
        <Form.List name="skus">
          {(fields) => <Flex vertical gap={8}>{fields.map((field, index) => (
            <SkuCombinationRow key={field.key} fieldName={field.name} index={index} />
          ))}</Flex>}
        </Form.List>
      )}
    </>
  );
});

function SkuCombinationRow({ fieldName, index }: { fieldName: number; index: number }) {
  const form = Form.useFormInstance<FormValues>();
  const enabled = Form.useWatch(["skus", fieldName, "enabled"], form) ?? false;
  const requiredRules = enabled ? [{ required: true, whitespace: true, max: 100 }] : undefined;
  return (
    <div className="catalog-specification-row">
      <Flex gap={8} wrap align="center">
        <Form.Item name={[fieldName, "enabled"]} valuePropName="checked" className="mb-0"><Checkbox>创建此组合</Checkbox></Form.Item>
        <Tag>组合 {index + 1}</Tag>
        <Form.Item name={[fieldName, "code"]} rules={requiredRules} className="mb-0"><Input aria-label={`组合 ${index + 1} SKU 编码`} style={{ width: 180 }} maxLength={100} /></Form.Item>
        <Form.Item name={[fieldName, "price"]} rules={enabled ? [{ required: true, message: "请填写售价" }] : undefined} className="mb-0"><InputNumber aria-label={`组合 ${index + 1} 售价`} min={0} precision={2} stringMode placeholder="售价" /></Form.Item>
        <Form.Item name={[fieldName, "market_price"]} className="mb-0"><InputNumber aria-label={`组合 ${index + 1} 划线价`} min={0} precision={2} stringMode placeholder="划线价" /></Form.Item>
        <Form.Item name={[fieldName, "initial_quantity"]} rules={enabled ? [{ required: true, message: "请填写初始库存" }] : undefined} className="mb-0"><InputNumber aria-label={`组合 ${index + 1} 初始库存`} min={0} max={1000000000} precision={0} placeholder="初始库存" /></Form.Item>
      </Flex>
    </div>
  );
}

function CustomDescriptionRow({ fieldName, onRemove }: { fieldName: number; onRemove: () => void }) {
  const form = Form.useFormInstance<FormValues>();
  const type = Form.useWatch(["custom", fieldName, "value_type"], form) ?? "text";
  return (
    <div className="catalog-specification-row">
      <Flex gap={8} wrap align="start">
        <Form.Item name={[fieldName, "name"]} rules={[{ required: true, whitespace: true, max: 100 }]} label="属性名称" className="mb-0"><Input style={{ width: 160 }} maxLength={100} /></Form.Item>
        <Form.Item name={[fieldName, "value_type"]} label="类型" initialValue="text" className="mb-0"><Select style={{ width: 120 }} options={[{ value: "text", label: "文本" }, { value: "number", label: "数值" }]} /></Form.Item>
        <Form.Item name={[fieldName, "is_required"]} valuePropName="checked" initialValue={false} label="必填" className="mb-0"><Checkbox>必填</Checkbox></Form.Item>
        <Button type="text" danger icon={<MinusCircleOutlined />} aria-label="移除自定义属性" onClick={onRemove} />
      </Flex>
      {type === "text" ? (
        <Flex gap={8} wrap className="mt-8">
          <Form.Item name={[fieldName, "max_length"]} label="最大长度" initialValue={200} rules={[{ required: true }]} className="mb-0"><InputNumber min={1} max={20000} precision={0} /></Form.Item>
          <Form.Item name={[fieldName, "value"]} label="属性值" className="mb-0" style={{ minWidth: 260 }}><Input maxLength={20000} /></Form.Item>
        </Flex>
      ) : (
        <Flex gap={8} wrap className="mt-8">
          <Form.Item name={[fieldName, "unit"]} label="单位" className="mb-0"><Input maxLength={32} style={{ width: 100 }} /></Form.Item>
          <Form.Item name={[fieldName, "decimal_places"]} label="小数位" initialValue={0} rules={[{ required: true }]} className="mb-0"><InputNumber min={0} max={6} precision={0} /></Form.Item>
          <Form.Item name={[fieldName, "min"]} label="最小值" rules={[{ required: true }]} className="mb-0"><InputNumber stringMode /></Form.Item>
          <Form.Item name={[fieldName, "max"]} label="最大值" rules={[{ required: true }]} className="mb-0"><InputNumber stringMode /></Form.Item>
          <Form.Item name={[fieldName, "value"]} label="属性值" className="mb-0"><InputNumber stringMode /></Form.Item>
        </Flex>
      )}
    </div>
  );
}

function DescriptionField({ attribute, item, values }: { attribute: AttributeRead; item: TemplateItem; values: Array<{ id: string; is_active?: boolean; name: string }> }) {
  const fieldName = ["descriptions", attribute.id];
  const required = item.is_required;
  if (attribute.value_type === "text") {
    return <Form.Item name={fieldName} label="属性值" rules={required ? [{ required: true, whitespace: true, message: "请填写属性值" }] : undefined} className="mt-8 mb-0"><Input maxLength={Number(attribute.validation.max_length ?? 20000)} /></Form.Item>;
  }
  if (attribute.value_type === "number") {
    return <Form.Item name={fieldName} label={`属性值${attribute.unit ? `（${attribute.unit}）` : ""}`} rules={required ? [{ required: true, message: "请填写属性值" }] : undefined} className="mt-8 mb-0"><InputNumber stringMode min={attribute.validation.min ? String(attribute.validation.min) : undefined} max={attribute.validation.max ? String(attribute.validation.max) : undefined} precision={Number(attribute.validation.decimal_places ?? 0)} /></Form.Item>;
  }
  const options = values.filter((value) => value.is_active).map((value) => ({ value: value.id, label: value.name }));
  return <Form.Item name={fieldName} label="属性值" rules={required ? [{ required: true, message: "请选择属性值" }] : undefined} className="mt-8 mb-0"><Select mode={attribute.value_type === "multi_select" ? "multiple" : undefined} options={options} /></Form.Item>;
}

export default ProductSpecificationForm;
