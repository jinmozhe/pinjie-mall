import type { AttributeRead, TemplateItem } from "@pinjie/api-client";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Divider, Drawer, Empty, Flex, InputNumber, Select, Space, Switch, Table, Tag, Tooltip, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { QueryState } from "@/components/PageFrame";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";

const valueTypeLabels: Record<AttributeRead["value_type"], string> = {
  text: "文本",
  number: "数值",
  select: "单选",
  multi_select: "多选",
};

type TemplateDraftItem = Required<Pick<TemplateItem, "attribute_id" | "is_variant" | "is_required" | "allow_custom_value">> & {
  sort_order: number | null;
};

type Props = {
  category: { id: string; name: string };
  canUpdate: boolean;
  close: () => void;
  done: () => Promise<void>;
};

function normalizeTemplateItem(item: TemplateItem): TemplateDraftItem {
  return {
    attribute_id: item.attribute_id,
    is_variant: item.is_variant ?? false,
    is_required: item.is_required ?? false,
    sort_order: item.sort_order ?? null,
    allow_custom_value: item.allow_custom_value ?? false,
  };
}

async function loadAttributes(): Promise<AttributeRead[]> {
  const first = await commerceApi.attributes(1, 100);
  const remaining = await Promise.all(
    Array.from({ length: Math.max(0, first.total_pages - 1) }, (_, index) => commerceApi.attributes(index + 2, 100)),
  );
  return [first, ...remaining].flatMap((page) => page.items);
}

type TemplateTableProps = {
  attributesById: Map<string, AttributeRead>;
  busy: boolean;
  canUpdate: boolean;
  items: TemplateDraftItem[];
  variantCount: number;
  updateItem: (attributeId: string, patch: Partial<TemplateDraftItem>) => void;
  removeItem: (item: TemplateDraftItem) => void;
};

const noWrapCell = () => ({ style: { whiteSpace: "nowrap" } });

function TemplateTable({ attributesById, busy, canUpdate, items, variantCount, updateItem, removeItem }: TemplateTableProps) {
  return (
    <Table<TemplateDraftItem>
      rowKey="attribute_id"
      size="small"
      pagination={false}
      scroll={{ x: "max-content" }}
      dataSource={items}
      columns={[
        {
          title: "公共属性",
          width: 260,
          onHeaderCell: noWrapCell,
          onCell: noWrapCell,
          render: (_, item) => {
            const attribute = attributesById.get(item.attribute_id);
            if (!attribute) return <Tag color="error">公共属性已不存在</Tag>;
            return (
              <Flex gap={6} align="center" wrap={false}>
                <Typography.Text ellipsis={{ tooltip: attribute.name }} style={{ maxWidth: 120 }}>{attribute.name}</Typography.Text>
                <Typography.Text type="secondary">{attribute.code}</Typography.Text>
                <Tag color={attribute.value_type === "select" ? "blue" : "default"}>{valueTypeLabels[attribute.value_type]}</Tag>
                {!attribute.is_active && <Tag color="warning">已停用</Tag>}
              </Flex>
            );
          },
        },
        {
          title: "用途",
          width: 150,
          onHeaderCell: noWrapCell,
          onCell: noWrapCell,
          render: (_, item) => {
            const attribute = attributesById.get(item.attribute_id);
            const supportsVariant = attribute?.is_active && attribute.value_type === "select";
            return (
              <Select
                value={item.is_variant ? "variant" : "description"}
                style={{ width: 132 }}
                disabled={!canUpdate || busy}
                options={[
                  { value: "description", label: "描述属性" },
                  {
                    value: "variant",
                    label: "销售规格",
                    disabled: !supportsVariant || (!item.is_variant && variantCount >= 10),
                  },
                ]}
                onChange={(value) => updateItem(item.attribute_id, {
                  is_variant: value === "variant",
                  allow_custom_value: value === "variant" ? item.allow_custom_value : false,
                })}
              />
            );
          },
        },
        {
          title: "必填",
          width: 90,
          onHeaderCell: noWrapCell,
          onCell: noWrapCell,
          render: (_, item) => (
            <Switch
              checked={item.is_required}
              checkedChildren="是"
              unCheckedChildren="否"
              aria-label={`${attributesById.get(item.attribute_id)?.name ?? "属性"}必填`}
              disabled={!canUpdate || busy}
              onChange={(is_required) => updateItem(item.attribute_id, { is_required })}
            />
          ),
        },
        {
          title: "销售自定义值",
          width: 132,
          onHeaderCell: noWrapCell,
          onCell: noWrapCell,
          render: (_, item) => (
            <Switch
              checked={item.allow_custom_value}
              checkedChildren="允许"
              unCheckedChildren="禁止"
              aria-label={`${attributesById.get(item.attribute_id)?.name ?? "属性"}销售自定义值`}
              disabled={!canUpdate || busy || !item.is_variant}
              onChange={(allow_custom_value) => updateItem(item.attribute_id, { allow_custom_value })}
            />
          ),
        },
        {
          title: "排序",
          width: 104,
          onHeaderCell: noWrapCell,
          onCell: noWrapCell,
          render: (_, item) => (
            <InputNumber
              min={0}
              precision={0}
              value={item.sort_order}
              placeholder="自动"
              style={{ width: 88 }}
              disabled={!canUpdate || busy}
              onChange={(sort_order) => updateItem(item.attribute_id, { sort_order })}
            />
          ),
        },
        {
          title: "操作",
          width: "1%",
          onHeaderCell: noWrapCell,
          onCell: noWrapCell,
          render: (_, item) => {
            const attribute = attributesById.get(item.attribute_id);
            return canUpdate ? (
              <Tooltip title="移除属性">
                <Button
                  danger
                  type="text"
                  icon={<DeleteOutlined />}
                  aria-label={`移除${attribute?.name ?? "公共属性"}`}
                  disabled={busy}
                  onClick={() => removeItem(item)}
                />
              </Tooltip>
            ) : null;
          },
        },
      ]}
    />
  );
}

export function CategoryTemplateDrawer({ category, canUpdate, close, done }: Props) {
  const { message } = App.useApp();
  const client = useQueryClient();
  const [items, setItems] = useState<TemplateDraftItem[]>([]);
  const [revision, setRevision] = useState<number>();
  const [attributeToAdd, setAttributeToAdd] = useState<string>();
  const [removeItem, setRemoveItem] = useState<TemplateDraftItem>();
  const [initialized, setInitialized] = useState(false);
  const templateQuery = useQuery({
    queryKey: ["commerce-category-template", category.id],
    queryFn: () => commerceApi.categoryTemplate(category.id),
  });
  const attributesQuery = useQuery({
    queryKey: ["commerce-template-attributes"],
    queryFn: loadAttributes,
  });

  useEffect(() => {
    if (!templateQuery.data || initialized) return;
    setItems(templateQuery.data.attributes.map(normalizeTemplateItem));
    setRevision(templateQuery.data.revision);
    setInitialized(true);
  }, [initialized, templateQuery.data]);

  const attributesById = useMemo(
    () => new Map((attributesQuery.data ?? []).map((attribute) => [attribute.id, attribute])),
    [attributesQuery.data],
  );
  const variantCount = items.filter((item) => item.is_variant).length;
  const invalidItems = items.filter((item) => !attributesById.get(item.attribute_id)?.is_active);
  const availableAttributes = (attributesQuery.data ?? []).filter(
    (attribute) => attribute.is_active && !items.some((item) => item.attribute_id === attribute.id),
  );
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["commerce-category-template", category.id] }),
      done(),
    ]);
  };
  const save = useLockedMutation({
    mutationFn: async () => {
      if (revision === undefined) throw new Error("分类模板尚未加载完成");
      if (invalidItems.length) throw new Error("模板包含已停用或不存在的公共属性，请移除后再保存");
      return commerceApi.updateCategoryTemplate(category.id, { revision, attributes: items });
    },
    onSuccess: async (template) => {
      setItems(template.attributes.map(normalizeTemplateItem));
      setRevision(template.revision);
      message.success("分类属性模板已保存");
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const updateItem = (attributeId: string, patch: Partial<TemplateDraftItem>) => {
    setItems((current) => {
      const currentItem = current.find((item) => item.attribute_id === attributeId);
      if (!currentItem) return current;
      const nextItem = { ...currentItem, ...patch };
      if (nextItem.is_variant && !currentItem.is_variant && current.filter((item) => item.is_variant).length >= 10) return current;
      if (!nextItem.is_variant) nextItem.allow_custom_value = false;
      return current.map((item) => (item.attribute_id === attributeId ? nextItem : item));
    });
  };
  const addAttribute = () => {
    if (!attributeToAdd || items.length >= 50) return;
    setItems((current) => current.length >= 50 || current.some((item) => item.attribute_id === attributeToAdd) ? current : [...current, {
      attribute_id: attributeToAdd,
      is_variant: false,
      is_required: false,
      sort_order: null,
      allow_custom_value: false,
    }]);
    setAttributeToAdd(undefined);
  };
  const retry = () => { void Promise.all([templateQuery.refetch(), attributesQuery.refetch()]); };
  const loading = templateQuery.isLoading || attributesQuery.isLoading;
  const queryError = templateQuery.error ?? attributesQuery.error;
  const busy = save.isPending;

  return (
    <>
      <Drawer
        open
        title={`分类属性模板：${category.name}`}
        size={960}
        closable={!busy}
        keyboard={!busy}
        mask={{ closable: !busy }}
        onClose={() => { if (!busy) close(); }}
        extra={canUpdate ? (
          <Button type="primary" loading={busy} disabled={loading || Boolean(queryError) || Boolean(invalidItems.length)} onClick={() => save.mutate(undefined)}>
            保存模板
          </Button>
        ) : null}
      >
        <Alert
          showIcon
          type="info"
          title="模板只绑定当前分类，不继承上级分类，也不会按 Excel 类目自动匹配。"
          description="销售规格只能引用单选公共属性；描述属性不能允许自定义候选值。"
        />
        <QueryState loading={loading} error={queryError ? errorMessage(queryError) : undefined} onRetry={retry} />
        {!loading && !queryError && (
          <Flex vertical gap={16} className="mt-16">
            {invalidItems.length > 0 && (
              <Alert
                showIcon
                type="error"
                title="模板包含已停用或不存在的公共属性"
                description="请移除这些属性后再保存；停用的公共属性不能继续作为分类模板使用。"
              />
            )}
            {canUpdate && (
              <Flex gap={8} align="center" wrap>
                <Select
                  showSearch
                  allowClear
                  value={attributeToAdd}
                  placeholder="选择要直接绑定的公共属性"
                  optionFilterProp="label"
                  style={{ minWidth: 300, flex: "1 1 360px" }}
                  options={availableAttributes.map((attribute) => ({
                    value: attribute.id,
                    label: `${attribute.name}（${attribute.code}，${valueTypeLabels[attribute.value_type]}）`,
                  }))}
                  disabled={busy || items.length >= 50 || availableAttributes.length === 0}
                  onChange={setAttributeToAdd}
                />
                <Button type="primary" icon={<PlusOutlined />} disabled={!attributeToAdd || busy || items.length >= 50} onClick={addAttribute}>
                  添加属性
                </Button>
                <Typography.Text type="secondary">已绑定 {items.length}/50 项，销售规格 {variantCount}/10 项</Typography.Text>
              </Flex>
            )}
            {items.length === 0 ? (
              <Empty description={canUpdate ? "尚未直接绑定公共属性" : "当前分类未配置直接属性模板"} />
            ) : (
              <TemplateTable
                attributesById={attributesById}
                busy={busy}
                canUpdate={canUpdate}
                items={items}
                variantCount={variantCount}
                updateItem={updateItem}
                removeItem={setRemoveItem}
              />
            )}
            {!canUpdate && <Alert type="info" title="当前账号仅可查看分类模板，不能修改绑定关系。" />}
            {save.error && <Alert showIcon type="error" title={errorMessage(save.error)} />}
          </Flex>
        )}
        <Divider />
        <Space size={4} wrap>
          <Typography.Text type="secondary">当前分类：</Typography.Text>
          <Typography.Text>{category.name}</Typography.Text>
          {revision !== undefined && <Typography.Text type="secondary">版本 v{revision}</Typography.Text>}
        </Space>
      </Drawer>
      <StandardConfirmModal
        open={Boolean(removeItem)}
        title="移除分类模板属性"
        description={`移除“${attributesById.get(removeItem?.attribute_id ?? "")?.name ?? "该公共属性"}”与“${category.name}”的直接模板绑定。保存分类模板后生效；取消不会改变当前草稿。`}
        loading={busy}
        onCancel={() => setRemoveItem(undefined)}
        onConfirm={async () => {
          if (!removeItem) return;
          setItems((current) => current.filter((item) => item.attribute_id !== removeItem.attribute_id));
          setRemoveItem(undefined);
        }}
      />
    </>
  );
}
