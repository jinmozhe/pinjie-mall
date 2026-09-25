import type {
  AdoptionInput,
  AdoptionRead,
  AttributeRead,
  AttributeValidationInput,
  CandidateAppend,
  CandidateInput,
  DescriptionSet,
  ProductRead,
  SkuRead,
  SkuUpdate,
  SpecificationConversion,
  StandardValueRead,
} from "@pinjie/api-client";
import {
  EditOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  RetweetOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Divider,
  Drawer,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { QueryState } from "@/components/PageFrame";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";
import {
  ProductSpecificationForm,
  type ProductSpecificationFormHandle,
} from "./ProductSpecificationForm";

type ValueType = AttributeRead["value_type"];

type DescriptionDraft = {
  attribute_id?: string | null;
  adoption_id?: string;
  draft_id: string;
  is_required: boolean;
  kind: "custom" | "existing" | "public";
  name: string;
  source_attribute_revision?: number | null;
  unit?: string | null;
  validation: AttributeValidationInput;
  value?: string | string[] | null;
  value_type: ValueType;
};

type DescriptionFormValues = {
  rows?: DescriptionDraft[];
};

type CandidateFormValues = {
  values?: string[];
};

type SkuFormValues = {
  code?: string;
  cost_price?: number | string | null;
  is_active?: boolean;
  market_price?: number | string | null;
  price?: number | string;
  selections?: Record<string, string | undefined>;
  weight_grams?: number | null;
};

type VariantDimension = {
  adoption: AdoptionRead;
  allowCustomValue: boolean;
  candidates: NonNullable<AdoptionRead["candidates"]>;
};

const valueTypeLabels: Record<ValueType, string> = {
  text: "文本",
  number: "数值",
  select: "单选",
  multi_select: "多选",
};

const noWrapCell = () => ({ style: { whiteSpace: "nowrap" } });

function isValueType(value: string): value is ValueType {
  return value === "text" || value === "number" || value === "select" || value === "multi_select";
}

function asValidation(snapshot: Record<string, unknown>): AttributeValidationInput {
  const maxLength = typeof snapshot.max_length === "number" ? snapshot.max_length : undefined;
  const decimalPlaces = typeof snapshot.decimal_places === "number" ? snapshot.decimal_places : undefined;
  const maxSelected = typeof snapshot.max_selected === "number" ? snapshot.max_selected : undefined;
  const min = typeof snapshot.min === "string" || typeof snapshot.min === "number" ? snapshot.min : undefined;
  const max = typeof snapshot.max === "string" || typeof snapshot.max === "number" ? snapshot.max : undefined;
  return {
    schema_version: 1,
    max_length: maxLength,
    decimal_places: decimalPlaces,
    min,
    max,
    max_selected: maxSelected,
  };
}

function descriptionDrafts(product: ProductRead): DescriptionDraft[] {
  return product.attributes
    .filter((adoption) => adoption.is_current && !adoption.is_variant)
    .map((adoption) => ({
      draft_id: `existing-${adoption.id}`,
      adoption_id: adoption.id,
      attribute_id: adoption.attribute_id,
      source_attribute_revision: adoption.source_attribute_revision,
      kind: "existing",
      name: adoption.name_snapshot,
      value_type: isValueType(adoption.value_type_snapshot) ? adoption.value_type_snapshot : "text",
      unit: adoption.unit_snapshot,
      validation: asValidation(adoption.validation_snapshot),
      is_required: adoption.is_required,
      value: Array.isArray(adoption.value) ? [...adoption.value] : adoption.value ?? null,
    }));
}

function textValue(value: unknown): string | null {
  if (typeof value === "number") return String(value);
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

function descriptionValue(row: DescriptionDraft): string | string[] | null {
  if (row.value_type === "multi_select") {
    const values = Array.isArray(row.value)
      ? row.value.map((value) => value.trim()).filter(Boolean)
      : [];
    return values.length ? values : null;
  }
  return textValue(row.value);
}

function customValidation(row: DescriptionDraft): AttributeValidationInput {
  if (row.value_type === "text") {
    const maxLength = Number(row.validation.max_length);
    if (!Number.isInteger(maxLength) || maxLength < 1 || maxLength > 20000) {
      throw new Error("文本自定义属性需要填写 1 至 20000 的最大长度");
    }
    return { schema_version: 1, max_length: maxLength };
  }
  const decimalPlaces = Number(row.validation.decimal_places);
  const min = textValue(row.validation.min);
  const max = textValue(row.validation.max);
  if (
    !Number.isInteger(decimalPlaces)
    || decimalPlaces < 0
    || decimalPlaces > 6
    || min === null
    || max === null
    || Number(min) > Number(max)
  ) {
    throw new Error("数值自定义属性需要填写有效的小数位、最小值和最大值");
  }
  return {
    schema_version: 1,
    decimal_places: decimalPlaces,
    min,
    max,
  };
}

function newCustomDescription(): DescriptionDraft {
  return {
    draft_id: `custom-${globalThis.crypto.randomUUID()}`,
    kind: "custom",
    name: "",
    value_type: "text",
    unit: null,
    validation: { schema_version: 1, max_length: 200 },
    is_required: false,
    value: null,
  };
}

function candidateInputs(
  values: string[],
  adoption: AdoptionRead,
  allowCustomValue: boolean,
  standardValues: StandardValueRead[],
): CandidateInput[] {
  const valuesById = new Map(standardValues.filter((value) => value.is_active).map((value) => [value.id, value]));
  const existingTexts = new Set(
    (adoption.candidates ?? [])
      .filter((candidate) => candidate.is_current)
      .map((candidate) => candidate.display_value.trim().toLocaleLowerCase()),
  );
  const seen = new Set<string>();
  const result: CandidateInput[] = [];

  for (const [index, raw] of values.entries()) {
    const value = raw.trim();
    if (!value) continue;
    if (value.startsWith("std:")) {
      const valueId = value.slice(4);
      const standard = valuesById.get(valueId);
      if (!standard) throw new Error("所选标准候选值已停用或不存在，请重新选择");
      const normalized = standard.name.trim().toLocaleLowerCase();
      if (seen.has(normalized) || existingTexts.has(normalized)) {
        throw new Error(`销售候选值重复：${standard.name}`);
      }
      seen.add(normalized);
      result.push({ key: `append-standard-${valueId}`, value_id: valueId });
      continue;
    }
    if (!allowCustomValue) throw new Error("当前销售规格不允许局部候选值");
    const normalized = value.toLocaleLowerCase();
    if (seen.has(normalized) || existingTexts.has(normalized)) {
      throw new Error(`销售候选值重复：${value}`);
    }
    seen.add(normalized);
    result.push({ key: `append-custom-${index + 1}`, display_value: value });
  }
  if (!result.length) throw new Error("至少选择或输入一个候选值");
  if ((adoption.candidates ?? []).filter((candidate) => candidate.is_current).length + result.length > 100) {
    throw new Error("每个销售维度最多保留一百个候选值");
  }
  return result;
}

function SkuEditorModal({
  product,
  sku,
  dimensions,
  open,
  close,
  onBusyChange,
  onSaved,
}: {
  close: () => void;
  dimensions: VariantDimension[];
  onBusyChange: (busy: boolean) => void;
  onSaved: (product: ProductRead) => Promise<void>;
  open: boolean;
  product: ProductRead;
  sku?: SkuRead;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<SkuFormValues>();
  const signature = dimensions.map((dimension) => `${dimension.adoption.id}:${dimension.candidates.map((candidate) => candidate.id).join(",")}`).join("|");
  const write = useLockedMutation({
    mutationFn: ({ input, skuId }: { input: SkuUpdate; skuId?: string }) => commerceApi.writeSku(product.id, input, skuId),
    onSuccess: async (next) => {
      await onSaved(next);
      message.success(sku ? "SKU 已更新" : "SKU 已新增，可售库存初始为 0");
      close();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  useEffect(() => {
    onBusyChange(write.isPending);
    return () => onBusyChange(false);
  }, [onBusyChange, write.isPending]);

  useEffect(() => {
    if (!open) return;
    const selections = Object.fromEntries(dimensions.map((dimension) => [
      dimension.adoption.id,
      (sku?.spec_value_ids ?? []).find((candidateId) => dimension.candidates.some((candidate) => candidate.id === candidateId)),
    ]));
    form.resetFields();
    form.setFieldsValue({
      code: sku?.code,
      price: sku?.price ?? "0",
      cost_price: sku?.cost_price ?? null,
      market_price: sku?.market_price ?? null,
      weight_grams: sku?.weight_grams ?? null,
      is_active: sku?.is_active ?? true,
      selections,
    });
  }, [dimensions, form, open, signature, sku]);

  const save = async () => {
    const values = await form.validateFields();
    const code = values.code?.trim();
    if (!code) throw new Error("请填写 SKU 编码");
    const specValueIds = dimensions.map((dimension) => values.selections?.[dimension.adoption.id]).filter((id): id is string => Boolean(id));
    if (specValueIds.length !== dimensions.length) throw new Error("请为每个当前销售维度选择一个候选值");
    const input: SkuUpdate = {
      code,
      price: textValue(values.price) ?? "0",
      cost_price: textValue(values.cost_price),
      market_price: textValue(values.market_price),
      weight_grams: values.weight_grams ?? null,
      is_active: values.is_active ?? true,
      spec_value_ids: specValueIds,
      revision: product.revision,
    };
    await write.mutateAsync({ input, skuId: sku?.id });
  };

  return (
    <Modal
      cancelButtonProps={{ disabled: write.isPending }}
      cancelText="取消"
      closable={!write.isPending}
      confirmLoading={write.isPending}
      keyboard={!write.isPending}
      mask={{ closable: !write.isPending }}
      okText={sku ? "保存 SKU" : "新增 SKU"}
      open={open}
      title={sku ? `编辑 SKU：${sku.code}` : "新增实际 SKU 组合"}
      onCancel={() => { if (!write.isPending) close(); }}
      onOk={() => void save().catch((error: unknown) => message.error(errorMessage(error)))}
    >
      {!sku && <Alert showIcon type="info" title="新增 SKU 的可售库存初始为 0，保存后请通过库存盘点调整。" className="mb-16" />}
      {sku && dimensions.length > 0 && <Alert showIcon type="warning" title="已存在 SKU 的规格组合不可原位修改。需要变更货品身份时，请使用规格转换。" className="mb-16" />}
      <Form form={form} layout="vertical" disabled={write.isPending}>
        <Flex gap={12} wrap>
          <Form.Item name="code" label="SKU 编码" rules={[{ required: true, whitespace: true, max: 100 }]} style={{ minWidth: 220, flex: "1 1 220px" }}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="price" label="售价" rules={[{ required: true, message: "请填写售价" }]}>
            <InputNumber min={0} precision={2} stringMode style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="market_price" label="划线价">
            <InputNumber min={0} precision={2} stringMode style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="cost_price" label="成本价">
            <InputNumber min={0} precision={2} stringMode style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="weight_grams" label="重量（克）">
            <InputNumber min={0} max={1000000000} precision={0} style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用销售" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Flex>
        {dimensions.length > 0 && <Divider orientation="horizontal" titlePlacement="start" plain>规格组合</Divider>}
        <Flex vertical gap={12}>
          {dimensions.map((dimension) => (
            <Form.Item
              key={dimension.adoption.id}
              name={["selections", dimension.adoption.id]}
              label={dimension.adoption.name_snapshot}
              rules={[{ required: true, message: `请选择${dimension.adoption.name_snapshot}` }]}
            >
              <Select
                disabled={Boolean(sku)}
                placeholder={dimension.candidates.length ? `选择${dimension.adoption.name_snapshot}` : "当前没有可用候选值"}
                options={dimension.candidates.map((candidate) => ({ value: candidate.id, label: candidate.display_value }))}
              />
            </Form.Item>
          ))}
        </Flex>
      </Form>
    </Modal>
  );
}

function CandidateAppendModal({
  adoption,
  allowCustomValue,
  attribute,
  product,
  standardValues,
  open,
  close,
  onBusyChange,
  onSaved,
}: {
  adoption?: AdoptionRead;
  allowCustomValue: boolean;
  attribute?: AttributeRead;
  close: () => void;
  onBusyChange: (busy: boolean) => void;
  onSaved: (product: ProductRead) => Promise<void>;
  open: boolean;
  product: ProductRead;
  standardValues: StandardValueRead[];
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<CandidateFormValues>();
  const append = useLockedMutation({
    mutationFn: ({ adoptionId, input }: { adoptionId: string; input: CandidateAppend }) => commerceApi.appendCandidates(product.id, adoptionId, input),
    onSuccess: async (next) => {
      await onSaved(next);
      message.success("销售候选已追加，请在 SKU 区新增实际组合");
      close();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  useEffect(() => {
    onBusyChange(append.isPending);
    return () => onBusyChange(false);
  }, [append.isPending, onBusyChange]);

  useEffect(() => {
    if (open) form.resetFields();
  }, [form, open, adoption?.id]);

  const save = async () => {
    if (!adoption) throw new Error("请先选择销售规格");
    if (adoption.attribute_id && !attribute) throw new Error("公共属性尚未加载完成，请稍后重试");
    const values = await form.validateFields();
    const candidates = candidateInputs(values.values ?? [], adoption, allowCustomValue, standardValues);
    await append.mutateAsync({
      adoptionId: adoption.id,
      input: {
        revision: product.revision,
        source_attribute_revision: attribute?.revision,
        candidates,
      },
    });
  };

  const usedStandardIds = new Set((adoption?.candidates ?? []).filter((candidate) => candidate.is_current && candidate.value_id).map((candidate) => candidate.value_id));
  const options = standardValues
    .filter((value) => value.is_active && !usedStandardIds.has(value.id))
    .map((value) => ({ value: `std:${value.id}`, label: value.name }));

  return (
    <Modal
      cancelButtonProps={{ disabled: append.isPending }}
      cancelText="取消"
      closable={!append.isPending}
      confirmLoading={append.isPending}
      keyboard={!append.isPending}
      mask={{ closable: !append.isPending }}
      okText="追加候选"
      open={open}
      title={`追加销售候选：${adoption?.name_snapshot ?? ""}`}
      onCancel={() => { if (!append.isPending) close(); }}
      onOk={() => void save().catch((error: unknown) => message.error(errorMessage(error)))}
    >
      <Alert
        showIcon
        type="info"
        title="追加候选不会创建 SKU 或改变库存"
        description="保存后请在实际 SKU 组合中选择新候选并新增货品。"
        className="mb-16"
      />
      {!allowCustomValue && !options.length ? (
        <Empty description="没有可追加的启用标准候选值" />
      ) : (
        <Form form={form} layout="vertical" disabled={append.isPending}>
          <Form.Item name="values" label="候选值" rules={[{ required: true, type: "array", min: 1, message: "至少选择一个候选值" }]}>
            <Select
              mode={allowCustomValue ? "tags" : "multiple"}
              options={options}
              placeholder={allowCustomValue ? "选择标准候选值，或输入允许的局部值" : "选择标准候选值"}
            />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

function DescriptionValueField({
  fieldName,
  row,
  standardValues,
}: {
  fieldName: number;
  row: DescriptionDraft;
  standardValues: StandardValueRead[];
}) {
  const label = `属性值${row.unit ? `（${row.unit}）` : ""}`;
  const requiredRule = row.is_required ? [{ required: true, message: `请填写${row.name}` }] : undefined;
  if (row.value_type === "text") {
    return (
      <Form.Item name={[fieldName, "value"]} rules={row.is_required ? [{ required: true, whitespace: true, message: `请填写${row.name}` }] : undefined} className="mb-0">
        <Input aria-label={label} maxLength={Number(row.validation.max_length ?? 20000)} placeholder={label} />
      </Form.Item>
    );
  }
  if (row.value_type === "number") {
    return (
      <Form.Item name={[fieldName, "value"]} rules={requiredRule} className="mb-0">
        <InputNumber
          aria-label={label}
          min={row.validation.min === null || row.validation.min === undefined ? undefined : String(row.validation.min)}
          max={row.validation.max === null || row.validation.max === undefined ? undefined : String(row.validation.max)}
          precision={Number(row.validation.decimal_places ?? 0)}
          stringMode
          placeholder={label}
          style={{ width: "100%" }}
        />
      </Form.Item>
    );
  }
  const options = standardValues.filter((value) => value.is_active).map((value) => ({ value: value.id, label: value.name }));
  return (
    <Form.Item name={[fieldName, "value"]} rules={requiredRule} className="mb-0">
      <Select
        aria-label={label}
        mode={row.value_type === "multi_select" ? "multiple" : undefined}
        maxCount={row.value_type === "multi_select" ? Number(row.validation.max_selected ?? undefined) : undefined}
        options={options}
        placeholder={options.length ? label : "没有可用标准候选值"}
      />
    </Form.Item>
  );
}

function CustomDescriptionConfiguration({ fieldName, row }: { fieldName: number; row: DescriptionDraft }) {
  return (
    <Flex gap={8} wrap align="center">
      <Form.Item name={[fieldName, "name"]} rules={[{ required: true, whitespace: true, max: 100, message: "请填写属性名称" }]} className="mb-0" style={{ width: 160 }}>
        <Input aria-label="属性名称" maxLength={100} placeholder="属性名称" />
      </Form.Item>
      <Form.Item name={[fieldName, "value_type"]} className="mb-0" style={{ width: 112 }}>
        <Select aria-label="属性类型" options={[{ value: "text", label: "文本" }, { value: "number", label: "数值" }]} />
      </Form.Item>
      <Form.Item name={[fieldName, "is_required"]} valuePropName="checked" className="mb-0">
        <Switch checkedChildren="必填" unCheckedChildren="选填" aria-label="是否必填" />
      </Form.Item>
      {row.value_type === "text" ? (
        <Form.Item name={[fieldName, "validation", "max_length"]} rules={[{ required: true, message: "请填写最大长度" }]} className="mb-0" style={{ width: 132 }}>
          <InputNumber aria-label="最大长度" min={1} max={20000} precision={0} placeholder="最大长度" style={{ width: "100%" }} />
        </Form.Item>
      ) : (
        <>
          <Form.Item name={[fieldName, "unit"]} className="mb-0" style={{ width: 96 }}>
            <Input aria-label="单位" maxLength={32} placeholder="单位" />
          </Form.Item>
          <Form.Item name={[fieldName, "validation", "decimal_places"]} rules={[{ required: true, message: "请填写小数位" }]} className="mb-0" style={{ width: 104 }}>
            <InputNumber aria-label="小数位" min={0} max={6} precision={0} placeholder="小数位" style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name={[fieldName, "validation", "min"]} rules={[{ required: true, message: "请填写最小值" }]} className="mb-0" style={{ width: 128 }}>
            <InputNumber aria-label="最小值" stringMode placeholder="最小值" style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name={[fieldName, "validation", "max"]} rules={[{ required: true, message: "请填写最大值" }]} className="mb-0" style={{ width: 128 }}>
            <InputNumber aria-label="最大值" stringMode placeholder="最大值" style={{ width: "100%" }} />
          </Form.Item>
        </>
      )}
    </Flex>
  );
}

export function ProductSpecificationsPanel({
  productId,
  canUpdate,
  close,
  done,
}: {
  canUpdate: boolean;
  close: () => void;
  done: () => Promise<void>;
  productId: string;
}) {
  const { message } = App.useApp();
  const client = useQueryClient();
  const [descriptionForm] = Form.useForm<DescriptionFormValues>();
  const [conversionForm] = Form.useForm();
  const conversionRef = useRef<ProductSpecificationFormHandle>(null);
  const initializedProductRef = useRef<string | undefined>(undefined);
  const [descriptionDirty, setDescriptionDirty] = useState(false);
  const [descriptionBaseRevision, setDescriptionBaseRevision] = useState<number>();
  const [discardDescriptionDraft, setDiscardDescriptionDraft] = useState(false);
  const [publicDescriptionId, setPublicDescriptionId] = useState<string>();
  const [descriptionRemoval, setDescriptionRemoval] = useState<{ index: number; row: DescriptionDraft }>();
  const [candidateTarget, setCandidateTarget] = useState<AdoptionRead>();
  const [skuEditor, setSkuEditor] = useState<SkuRead | null | undefined>(undefined);
  const [skuSaving, setSkuSaving] = useState(false);
  const [candidateSaving, setCandidateSaving] = useState(false);
  const [conversionEditorOpen, setConversionEditorOpen] = useState(false);
  const [conversionConfirmOpen, setConversionConfirmOpen] = useState(false);
  const [preparedConversion, setPreparedConversion] = useState<SpecificationConversion>();

  const productQuery = useQuery({
    queryKey: ["commerce-product", productId],
    queryFn: () => commerceApi.product(productId),
  });
  const product = productQuery.data;
  const templateQuery = useQuery({
    queryKey: ["commerce-category-template", product?.category_id],
    queryFn: () => commerceApi.categoryTemplate(product!.category_id),
    enabled: Boolean(product),
  });
  const template = templateQuery.data;
  const currentAdoptions = useMemo(
    () => (product?.attributes ?? []).filter((adoption) => adoption.is_current),
    [product?.attributes],
  );
  const attributeIds = useMemo(() => {
    const ids = new Set<string>(template?.attributes.map((item) => item.attribute_id) ?? []);
    for (const adoption of currentAdoptions) if (adoption.attribute_id) ids.add(adoption.attribute_id);
    return [...ids].sort();
  }, [currentAdoptions, template?.attributes]);
  const attributeQueries = useQueries({
    queries: attributeIds.map((attributeId) => ({
      queryKey: ["commerce-spec-attribute", attributeId],
      queryFn: () => commerceApi.attribute(attributeId),
      enabled: Boolean(product),
    })),
  });
  const attributesById = useMemo(
    () => new Map(attributeQueries.flatMap((query) => query.data ? [query.data] : []).map((attribute) => [attribute.id, attribute])),
    [attributeQueries],
  );
  const enumAttributeIds = useMemo(
    () => [...attributesById.values()]
      .filter((attribute) => attribute.value_type === "select" || attribute.value_type === "multi_select")
      .map((attribute) => attribute.id)
      .sort(),
    [attributesById],
  );
  const valueQueries = useQueries({
    queries: enumAttributeIds.map((attributeId) => ({
      queryKey: ["commerce-spec-attribute-values", attributeId],
      queryFn: () => commerceApi.attributeValues(attributeId),
      enabled: Boolean(product),
    })),
  });
  const standardValuesByAttribute = useMemo(
    () => new Map(enumAttributeIds.map((attributeId, index) => [attributeId, valueQueries[index]?.data ?? []])),
    [enumAttributeIds, valueQueries],
  );
  const templateRows = useMemo(
    () => (template?.attributes ?? [])
      .flatMap((item) => {
        const attribute = attributesById.get(item.attribute_id);
        return attribute ? [{ item, attribute }] : [];
      })
      .sort((left, right) => (left.item.sort_order ?? 0) - (right.item.sort_order ?? 0)),
    [attributesById, template?.attributes],
  );
  const templateVariantsByAttributeId = useMemo(
    () => new Map(templateRows.filter(({ item }) => item.is_variant).map(({ attribute, item }) => [attribute.id, item])),
    [templateRows],
  );
  const variants = useMemo<VariantDimension[]>(
    () => currentAdoptions
      .filter((adoption) => adoption.is_variant)
      .map((adoption) => {
        const templateItem = adoption.attribute_id ? templateVariantsByAttributeId.get(adoption.attribute_id) : undefined;
        const followsCurrentTemplate = Boolean(
          templateItem
          && adoption.source_category_id === product?.category_id
          && adoption.is_required === templateItem.is_required,
        );
        return {
          adoption,
          allowCustomValue: adoption.source_category_id === null
            ? Boolean(adoption.allow_custom_value)
            : Boolean(followsCurrentTemplate && templateItem?.allow_custom_value),
          candidates: (adoption.candidates ?? []).filter((candidate) => candidate.is_current),
        };
      }),
    [currentAdoptions, product?.category_id, templateVariantsByAttributeId],
  );
  const templateVariantIds = useMemo(
    () => new Set(templateRows.filter(({ item }) => item.is_variant).map(({ attribute }) => attribute.id)),
    [templateRows],
  );
  const legacyVariants = useMemo(
    () => currentAdoptions.filter((adoption) => adoption.is_variant && (!adoption.attribute_id || !templateVariantIds.has(adoption.attribute_id))),
    [currentAdoptions, templateVariantIds],
  );
  const descriptionRows = Form.useWatch("rows", descriptionForm) ?? [];
  const dependenciesLoading = templateQuery.isLoading || attributeQueries.some((query) => query.isLoading) || valueQueries.some((query) => query.isLoading);
  const dependenciesError = templateQuery.error ?? attributeQueries.find((query) => query.error)?.error ?? valueQueries.find((query) => query.error)?.error;
  const currentSkuRows = (product?.skus ?? []).filter((sku) => sku.archived_at === null);
  const activeAttributeCount = currentAdoptions.filter((adoption) => adoption.is_variant).length + descriptionRows.length;
  const availableDescriptionAttributes = templateRows.filter(({ item, attribute }) => (
    !item.is_variant
    && attribute.is_active
    && !descriptionRows.some((row) => row.attribute_id === attribute.id)
  ));

  const resetDescriptionDraft = useCallback((next: ProductRead) => {
    descriptionForm.resetFields();
    descriptionForm.setFieldsValue({ rows: descriptionDrafts(next) });
    initializedProductRef.current = `${next.id}:${next.revision}`;
    setDescriptionBaseRevision(next.revision);
    setDescriptionDirty(false);
  }, [descriptionForm]);

  useEffect(() => {
    if (!product) return;
    const currentKey = `${product.id}:${product.revision}`;
    if (initializedProductRef.current !== currentKey && !descriptionDirty) resetDescriptionDraft(product);
  }, [descriptionDirty, product, resetDescriptionDraft]);

  const updateProduct = async (next: ProductRead, resetDescriptions: boolean = false) => {
    client.setQueryData(["commerce-product", productId], next);
    if (resetDescriptions) resetDescriptionDraft(next);
    await done();
  };

  const saveDescriptions = useLockedMutation({
    mutationFn: (input: DescriptionSet) => commerceApi.saveDescriptions(productId, input),
    onSuccess: async (next) => {
      await updateProduct(next, true);
      message.success("描述属性已保存，原采用和值已保留为历史记录");
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const convert = useLockedMutation({
    mutationFn: (input: SpecificationConversion) => commerceApi.convertSpecifications(productId, input),
    onSuccess: async (next) => {
      await updateProduct(next, true);
      conversionForm.resetFields();
      setConversionConfirmOpen(false);
      setConversionEditorOpen(false);
      setPreparedConversion(undefined);
      message.success("规格转换已完成，旧 SKU 已归档，请盘点新 SKU 库存");
    },
  });
  const busy = saveDescriptions.isPending || candidateSaving || skuSaving || convert.isPending;

  const refreshDetail = async () => {
    await Promise.all([
      productQuery.refetch(),
      templateQuery.refetch(),
      ...attributeQueries.map((query) => query.refetch()),
      ...valueQueries.map((query) => query.refetch()),
    ]);
  };

  const saveDescriptionRows = async () => {
    if (!product || !template) throw new Error("商品或分类模板尚未加载完成");
    if (descriptionBaseRevision !== product.revision) {
      throw new Error("商品已变更，当前描述草稿不能覆盖最新数据。请明确放弃草稿后重新读取。");
    }
    const values = await descriptionForm.validateFields();
    const rows = values.rows ?? [];
    if (variants.length + rows.length > 50) throw new Error("商品属性最多五十项");
    const currentNames = new Set<string>();
    const existing = [];
    const added: AdoptionInput[] = [];
    for (const [index, row] of rows.entries()) {
      const value = descriptionValue(row);
      const name = row.name.trim();
      if (!name) throw new Error(`第 ${index + 1} 项描述属性缺少名称`);
      if (currentNames.has(name)) throw new Error(`描述属性名称重复：${name}`);
      currentNames.add(name);
      if (row.is_required && value === null) throw new Error(`${name}为必填项`);
      if (row.kind === "existing") {
        if (!row.adoption_id) throw new Error("描述属性缺少采用标识，请重新读取");
        existing.push({ adoption_id: row.adoption_id, value });
        continue;
      }
      if (row.kind === "public") {
        if (!row.attribute_id) throw new Error("公共描述属性缺少标识");
        const attribute = attributesById.get(row.attribute_id);
        if (!attribute?.is_active) throw new Error("公共描述属性已停用或尚未加载完成，请重新读取");
        added.push({
          key: `description-public-${attribute.id}`,
          attribute_id: attribute.id,
          source_attribute_revision: attribute.revision,
          is_variant: false,
          is_required: row.is_required,
          value,
        });
        continue;
      }
      added.push({
        key: row.draft_id,
        name,
        value_type: row.value_type,
        unit: row.value_type === "number" ? row.unit?.trim() || null : null,
        validation: customValidation(row),
        is_variant: false,
        is_required: row.is_required,
        value,
      });
    }
    await saveDescriptions.mutateAsync({
      revision: product.revision,
      category_revision: template.revision,
      existing,
      added,
    });
  };

  const prepareConversion = async () => {
    if (!product || !conversionRef.current) throw new Error("规格转换表单尚未加载完成");
    if (legacyVariants.length) throw new Error("当前存在分类模板外的销售规格，请先由专门迁移流程处理后再转换");
    const payload = await conversionRef.current.validate();
    setPreparedConversion({
      attributes: payload.attributes,
      skus: payload.skus,
      category_revision: payload.categoryRevision,
      revision: product.revision,
    });
    setConversionEditorOpen(false);
    setConversionConfirmOpen(true);
  };

  const confirmConversion = async () => {
    if (!product || !preparedConversion) throw new Error("请先完成规格转换配置");
    if (preparedConversion.revision !== product.revision) {
      throw new Error("商品已变更，请重新配置规格转换后再确认。");
    }
    await convert.mutateAsync(preparedConversion);
  };

  if (!canUpdate) {
    return (
      <Drawer open title="规格与 SKU 维护" size={960} onClose={close}>
        <Alert showIcon type="warning" title="当前账号没有商品修改权限，不能维护规格、候选值或 SKU。" />
      </Drawer>
    );
  }

  return (
    <>
      <Drawer
        open
        title={`规格与 SKU 维护：${product?.name ?? "加载中"}`}
        size={1080}
        closable={!busy}
        keyboard={!busy}
        mask={{ closable: !busy }}
        onClose={() => { if (!busy) close(); }}
        extra={<Button disabled={busy || productQuery.isFetching} onClick={() => void refreshDetail()}>重新读取</Button>}
      >
        <QueryState loading={productQuery.isLoading} error={productQuery.error ? errorMessage(productQuery.error) : undefined} onRetry={() => void productQuery.refetch()} />
        {product && (
          <Flex vertical gap={16}>
            {descriptionDirty && descriptionBaseRevision !== product.revision && (
              <Alert
                showIcon
                type="warning"
                title="商品版本已变化，当前描述草稿仍保留"
                description="为防止覆盖最新描述，当前草稿已被锁定。明确放弃草稿并重新读取后才能继续保存。"
                action={<Button onClick={() => setDiscardDescriptionDraft(true)}>放弃草稿并重新读取</Button>}
              />
            )}
            {dependenciesError && <Alert showIcon type="error" title="分类模板或公共属性加载失败" description={errorMessage(dependenciesError)} action={<Button onClick={() => void refreshDetail()}>重试</Button>} />}
            <section>
              <Flex justify="space-between" align="center" wrap gap={8}>
                <Typography.Title level={5} style={{ margin: 0 }}>描述属性</Typography.Title>
                <Button type="primary" disabled={busy || dependenciesLoading || Boolean(dependenciesError)} onClick={() => void saveDescriptionRows().catch((error: unknown) => message.error(errorMessage(error)))}>
                  保存描述属性
                </Button>
              </Flex>
              <Typography.Paragraph type="secondary" className="mt-8 mb-12">
                保存会原子更新当前描述采用，移除的采用和值会保留为历史记录，不影响 SKU 或库存。
              </Typography.Paragraph>
              <Form form={descriptionForm} layout="vertical" disabled={busy} onValuesChange={() => setDescriptionDirty(true)}>
                <Form.List name="rows">
                  {(fields, actions) => (
                    <>
                      <Flex gap={8} wrap className="mb-12">
                        <Select
                          showSearch
                          allowClear
                          value={publicDescriptionId}
                          placeholder="按分类模板选择公共描述属性"
                          optionFilterProp="label"
                          style={{ minWidth: 280, flex: "1 1 360px" }}
                          options={availableDescriptionAttributes.map(({ attribute }) => ({
                            value: attribute.id,
                            label: `${attribute.name}（${attribute.code}，${valueTypeLabels[attribute.value_type]}）`,
                          }))}
                          disabled={busy || activeAttributeCount >= 50 || availableDescriptionAttributes.length === 0}
                          onChange={setPublicDescriptionId}
                        />
                        <Button
                          icon={<PlusOutlined />}
                          disabled={!publicDescriptionId || busy || activeAttributeCount >= 50}
                          onClick={() => {
                            const match = templateRows.find(({ attribute }) => attribute.id === publicDescriptionId);
                            if (!match) return;
                            actions.add({
                              draft_id: `public-${match.attribute.id}`,
                              attribute_id: match.attribute.id,
                              source_attribute_revision: match.attribute.revision,
                              kind: "public",
                              name: match.attribute.name,
                              value_type: match.attribute.value_type,
                              unit: match.attribute.unit,
                              validation: match.attribute.validation,
                              is_required: Boolean(match.item.is_required),
                              value: null,
                            });
                            setPublicDescriptionId(undefined);
                          }}
                        >
                          添加公共描述
                        </Button>
                        <Button
                          icon={<PlusOutlined />}
                          disabled={busy || activeAttributeCount >= 50}
                          onClick={() => actions.add(newCustomDescription())}
                        >
                          添加商品独有描述
                        </Button>
                        <Typography.Text type="secondary">属性 {activeAttributeCount}/50</Typography.Text>
                      </Flex>
                      {fields.length === 0 ? (
                        <Empty description="当前商品尚未采用描述属性" />
                      ) : (
                        <Table
                          rowKey={(item) => item.row.draft_id}
                          size="small"
                          pagination={false}
                          scroll={{ x: "max-content" }}
                          dataSource={fields.map((field) => ({ field, row: descriptionRows[field.name] })).filter((item): item is { field: typeof fields[number]; row: DescriptionDraft } => Boolean(item.row))}
                          columns={[
                            {
                              title: "属性",
                              width: 240,
                              onHeaderCell: noWrapCell,
                              onCell: noWrapCell,
                              render: (_, item: { field: typeof fields[number]; row: DescriptionDraft }) => (
                                <Flex vertical gap={4}>
                                  {item.row.kind === "custom" ? (
                                    <CustomDescriptionConfiguration fieldName={item.field.name} row={item.row} />
                                  ) : (
                                    <Space size={4} wrap={false}>
                                      <Typography.Text ellipsis={{ tooltip: item.row.name }} style={{ maxWidth: 140 }}>{item.row.name}</Typography.Text>
                                      <Tag>{valueTypeLabels[item.row.value_type]}</Tag>
                                      {item.row.is_required && <Tag color="error">必填</Tag>}
                                    </Space>
                                  )}
                                </Flex>
                              ),
                            },
                            {
                              title: "属性值",
                              width: 320,
                              onHeaderCell: noWrapCell,
                              onCell: noWrapCell,
                              render: (_, item: { field: typeof fields[number]; row: DescriptionDraft }) => (
                                <DescriptionValueField
                                  fieldName={item.field.name}
                                  row={item.row}
                                  standardValues={item.row.attribute_id ? standardValuesByAttribute.get(item.row.attribute_id) ?? [] : []}
                                />
                              ),
                            },
                            {
                              title: "来源",
                              width: 140,
                              onHeaderCell: noWrapCell,
                              onCell: noWrapCell,
                              render: (_, item: { row: DescriptionDraft }) => (
                                item.row.kind === "existing" ? "当前采用" : item.row.kind === "public" ? "分类公共属性" : "商品独有属性"
                              ),
                            },
                            {
                              title: "操作",
                              width: "1%",
                              onHeaderCell: noWrapCell,
                              onCell: noWrapCell,
                              render: (_, item: { field: typeof fields[number]; row: DescriptionDraft }) => (
                                <Tooltip title="移除描述属性">
                                  <Button
                                    danger
                                    type="text"
                                    icon={<MinusCircleOutlined />}
                                    aria-label={`移除${item.row.name || "描述属性"}`}
                                    disabled={busy}
                                    onClick={() => setDescriptionRemoval({ index: item.field.name, row: item.row })}
                                  />
                                </Tooltip>
                              ),
                            },
                          ] as ColumnsType<{ field: typeof fields[number]; row: DescriptionDraft }>}
                        />
                      )}
                      <StandardConfirmModal
                        open={Boolean(descriptionRemoval)}
                        title="移除描述属性"
                        description={descriptionRemoval?.row.kind === "existing"
                          ? `移除“${descriptionRemoval.row.name}”的当前描述采用。保存后该采用和值会转为历史记录，SKU 和库存不会变化；取消不会改变草稿。`
                          : `移除“${descriptionRemoval?.row.name || "该描述属性"}”草稿。取消不会改变草稿。`}
                        loading={busy}
                        onCancel={() => setDescriptionRemoval(undefined)}
                        onConfirm={async () => {
                          if (!descriptionRemoval) return;
                          actions.remove(descriptionRemoval.index);
                          setDescriptionRemoval(undefined);
                        }}
                      />
                    </>
                  )}
                </Form.List>
              </Form>
              {saveDescriptions.error && <Alert showIcon type="error" title={errorMessage(saveDescriptions.error)} className="mt-12" />}
            </section>

            <Divider className="my-0" />

            <section>
              <Flex justify="space-between" align="center" wrap gap={8}>
                <Typography.Title level={5} style={{ margin: 0 }}>销售规格候选</Typography.Title>
                <Typography.Text type="secondary">追加候选不会自动创建 SKU。</Typography.Text>
              </Flex>
              {!variants.length ? (
                <Empty description="当前商品没有销售规格维度" />
              ) : (
                <Table<VariantDimension>
                  rowKey={(row) => row.adoption.id}
                  size="small"
                  pagination={false}
                  scroll={{ x: "max-content" }}
                  dataSource={variants}
                  columns={[
                    {
                      title: "销售维度",
                      width: 220,
                      onHeaderCell: noWrapCell,
                      onCell: noWrapCell,
                      render: (_, row) => <Space size={4}><Typography.Text>{row.adoption.name_snapshot}</Typography.Text>{row.allowCustomValue && <Tag color="blue">允许局部候选</Tag>}</Space>,
                    },
                    {
                      title: "当前候选",
                      onHeaderCell: noWrapCell,
                      onCell: noWrapCell,
                      render: (_, row) => row.candidates.length ? <Space size={4} wrap>{row.candidates.map((candidate) => <Tag key={candidate.id}>{candidate.display_value}</Tag>)}</Space> : "暂无候选",
                    },
                    {
                      title: "操作",
                      width: "1%",
                      onHeaderCell: noWrapCell,
                      onCell: noWrapCell,
                      render: (_, row) => (
                        <Button icon={<TagsOutlined />} disabled={busy} onClick={() => setCandidateTarget(row.adoption)}>
                          追加候选
                        </Button>
                      ),
                    },
                  ]}
                />
              )}
            </section>

            <Divider className="my-0" />

            <section>
              <Flex justify="space-between" align="center" wrap gap={8}>
                <Typography.Title level={5} style={{ margin: 0 }}>实际 SKU 组合</Typography.Title>
                <Space wrap>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    disabled={busy || currentSkuRows.length >= 100 || (variants.length === 0 && currentSkuRows.length > 0)}
                    onClick={() => setSkuEditor(null)}
                  >
                    新增 SKU
                  </Button>
                  <Tooltip title={legacyVariants.length ? `当前存在分类模板外的销售规格：${legacyVariants.map((adoption) => adoption.name_snapshot).join("、")}` : "转换销售维度或货品身份"}>
                    <span>
                      <Button icon={<RetweetOutlined />} disabled={busy || dependenciesLoading || Boolean(dependenciesError) || legacyVariants.length > 0} onClick={() => setConversionEditorOpen(true)}>
                        规格转换
                      </Button>
                    </span>
                  </Tooltip>
                </Space>
              </Flex>
              <Typography.Paragraph type="secondary" className="mt-8 mb-12">
                新增 SKU 必须为每个当前销售维度选择一个候选值。已有 SKU 的规格组合属于货品身份，变更时使用规格转换。
              </Typography.Paragraph>
              {legacyVariants.length > 0 && <Alert showIcon type="warning" title="当前存在分类模板外的销售规格，不能用此转换表单静默保留或移除它们。请先按专门迁移流程处理后再转换。" className="mb-12" />}
              {currentSkuRows.length === 0 ? (
                <Empty description="当前没有可用 SKU，请先新增实际组合或进行规格转换" />
              ) : (
                <Table<SkuRead>
                  rowKey="id"
                  size="small"
                  pagination={false}
                  scroll={{ x: "max-content" }}
                  dataSource={currentSkuRows}
                  columns={[
                    { title: "SKU 编码", dataIndex: "code", onHeaderCell: noWrapCell, onCell: noWrapCell },
                    {
                      title: "规格组合",
                      onHeaderCell: noWrapCell,
                      onCell: noWrapCell,
                      render: (_, row) => Object.keys(row.specifications).length
                        ? <Space size={4} wrap>{Object.entries(row.specifications).map(([name, value]) => <Tag key={name}>{`${name}：${value}`}</Tag>)}</Space>
                        : "默认 SKU",
                    },
                    { title: "售价", dataIndex: "price", width: 120, onHeaderCell: noWrapCell, onCell: noWrapCell, render: (value) => `￥${value}` },
                    { title: "状态", width: 100, onHeaderCell: noWrapCell, onCell: noWrapCell, render: (_, row) => <Tag color={row.is_active ? "success" : "default"}>{row.is_active ? "启用" : "停用"}</Tag> },
                    {
                      title: "操作",
                      width: "1%",
                      onHeaderCell: noWrapCell,
                      onCell: noWrapCell,
                      render: (_, row) => (
                        <Button icon={<EditOutlined />} disabled={busy} onClick={() => setSkuEditor(row)}>
                          编辑 SKU
                        </Button>
                      ),
                    },
                  ]}
                />
              )}
            </section>
          </Flex>
        )}
      </Drawer>

      {product && (
        <CandidateAppendModal
          adoption={candidateTarget}
          allowCustomValue={variants.find(({ adoption }) => adoption.id === candidateTarget?.id)?.allowCustomValue ?? false}
          attribute={candidateTarget?.attribute_id ? attributesById.get(candidateTarget.attribute_id) : undefined}
          product={product}
          standardValues={candidateTarget?.attribute_id ? standardValuesByAttribute.get(candidateTarget.attribute_id) ?? [] : []}
          open={Boolean(candidateTarget)}
          close={() => setCandidateTarget(undefined)}
          onBusyChange={setCandidateSaving}
          onSaved={(next) => updateProduct(next)}
        />
      )}
      {product && skuEditor !== undefined && (
        <SkuEditorModal
          product={product}
          sku={skuEditor ?? undefined}
          dimensions={variants}
          open
          close={() => setSkuEditor(undefined)}
          onBusyChange={setSkuSaving}
          onSaved={(next) => updateProduct(next)}
        />
      )}
      {product && (
        <Drawer
          open={conversionEditorOpen}
          title={`配置规格转换：${product.name}`}
          size={980}
          closable={!convert.isPending}
          keyboard={!convert.isPending}
          mask={{ closable: !convert.isPending }}
          onClose={() => { if (!convert.isPending) setConversionEditorOpen(false); }}
          extra={<Button type="primary" disabled={convert.isPending || legacyVariants.length > 0} onClick={() => void prepareConversion().catch((error: unknown) => message.error(errorMessage(error)))}>进入风险确认</Button>}
        >
          <Alert
            showIcon
            type="warning"
            title="规格转换会创建新的货品集合"
            description="请配置完整的新属性与 SKU 组合。每个新 SKU 都要明确初始库存，建议先填 0，再完成实际盘点。"
            className="mb-16"
          />
          <Form form={conversionForm} layout="vertical">
            <ProductSpecificationForm ref={conversionRef} categoryId={product.category_id} existingProduct={product} mode="conversion" />
          </Form>
        </Drawer>
      )}
      <StandardConfirmModal
        open={discardDescriptionDraft}
        title="放弃描述属性草稿"
        description="将丢弃当前未保存的描述属性编辑，并重新读取商品与分类模板。取消会保留草稿。"
        loading={false}
        onCancel={() => setDiscardDescriptionDraft(false)}
        onConfirm={async () => {
          const next = await commerceApi.product(productId);
          client.setQueryData(["commerce-product", productId], next);
          resetDescriptionDraft(next);
          await Promise.all([
            templateQuery.refetch(),
            ...attributeQueries.map((query) => query.refetch()),
            ...valueQueries.map((query) => query.refetch()),
          ]);
          setDiscardDescriptionDraft(false);
          message.success("已重新读取商品规格与描述属性");
        }}
      />
      <StandardConfirmModal
        open={conversionConfirmOpen}
        title="确认转换商品规格与货品"
        description="确认后将归档当前全部 SKU 与销售规格，清退旧 SKU 的可售库存；旧库存不会复制到新 SKU，必须重新盘点。已有订单继续保留原货品和规格快照。"
        loading={convert.isPending}
        onCancel={() => {
          setConversionConfirmOpen(false);
          setConversionEditorOpen(true);
        }}
        onConfirm={confirmConversion}
      >
        {preparedConversion && <Alert showIcon type="info" title={`本次将建立 ${(preparedConversion.attributes ?? []).length} 项属性与 ${preparedConversion.skus.length} 个新 SKU`} />}
      </StandardConfirmModal>
    </>
  );
}

export default ProductSpecificationsPanel;
