import type {
  AttributeInput,
  AttributeRead,
  AttributeUpdate,
  StandardValueInput,
  StandardValueRead,
  StandardValueUpdate,
} from "@pinjie/api-client";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  PoweroffOutlined,
  SearchOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Radio,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
} from "antd";
import { useEffect, useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";

type AttributeValueType = AttributeRead["value_type"];

type AttributeEditorValues = {
  name: string;
  code: string;
  value_type: AttributeValueType;
  unit?: string | null;
  validation?: {
    max_length?: number | null;
    decimal_places?: number | null;
    min?: string | number | null;
    max?: string | number | null;
    max_selected?: number | null;
  };
  sort_order?: number | null;
  is_active?: boolean;
};

type AttributeFilterValues = {
  search?: string;
  value_type?: AttributeValueType | "";
  active?: "all" | "active" | "inactive";
};

const valueTypeOptions: Array<{ label: string; value: AttributeValueType }> = [
  { label: "下拉单选 (select)", value: "select" },
  { label: "下拉多选 (multi_select)", value: "multi_select" },
  { label: "自由文本 (text)", value: "text" },
  { label: "数值 (number)", value: "number" },
];

function defaultValidation(valueType: AttributeValueType): NonNullable<AttributeEditorValues["validation"]> {
  if (valueType === "text") return { max_length: 2000 };
  if (valueType === "number") return { decimal_places: 3, min: "0", max: "1000000" };
  if (valueType === "multi_select") return { max_selected: 20 };
  return {};
}

function validationPayload(
  valueType: AttributeValueType,
  values: NonNullable<AttributeEditorValues["validation"]>,
): AttributeInput["validation"] {
  if (valueType === "text") return { schema_version: 1, max_length: values.max_length ?? null };
  if (valueType === "number") {
    return {
      schema_version: 1,
      decimal_places: values.decimal_places ?? null,
      min: values.min ?? null,
      max: values.max ?? null,
    };
  }
  if (valueType === "multi_select") return { schema_version: 1, max_selected: values.max_selected ?? null };
  return { schema_version: 1 };
}

function ValueTypeValidationFields({ valueType }: { valueType: AttributeValueType }) {
  if (valueType === "text") {
    return (
      <Form.Item
        name={["validation", "max_length"]}
        label="最大字符数"
        rules={[{ required: true, message: "请输入最大字符数" }]}
      >
        <InputNumber min={1} max={20000} precision={0} style={{ width: "100%" }} />
      </Form.Item>
    );
  }
  if (valueType === "number") {
    return (
      <>
        <Form.Item
          name="unit"
          label="单位"
          rules={[{ whitespace: true, max: 32, message: "单位最长 32 个字符" }]}
          extra="没有统一量纲时可留空。"
        >
          <Input maxLength={32} placeholder="例如：V、W、cm、kg" />
        </Form.Item>
        <Form.Item
          name={["validation", "decimal_places"]}
          label="小数位数"
          rules={[{ required: true, message: "请输入小数位数" }]}
        >
          <InputNumber min={0} max={6} precision={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          name={["validation", "min"]}
          label="最小值"
          rules={[{ required: true, message: "请输入最小值" }]}
        >
          <InputNumber<string> stringMode precision={6} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          name={["validation", "max"]}
          label="最大值"
          rules={[{ required: true, message: "请输入最大值" }]}
        >
          <InputNumber<string> stringMode precision={6} style={{ width: "100%" }} />
        </Form.Item>
      </>
    );
  }
  if (valueType === "multi_select") {
    return (
      <Form.Item
        name={["validation", "max_selected"]}
        label="最多选择数"
        rules={[{ required: true, message: "请输入最多选择数" }]}
      >
        <InputNumber min={1} max={100} precision={0} style={{ width: "100%" }} />
      </Form.Item>
    );
  }
  return <Alert type="info" showIcon title="单选属性使用标准候选值集合，不需要额外验证规则。" />;
}

function AttributeEditor({
  target,
  done,
  close,
}: {
  target: AttributeRead | null;
  done: () => Promise<void>;
  close: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<AttributeEditorValues>();
  const valueType =
    (Form.useWatch("value_type", form) as AttributeValueType | undefined) ?? target?.value_type ?? "select";
  return (
    <EditorModal
      title={target ? "编辑公共属性" : "新建公共属性"}
      onClose={close}
      onSave={async () => {
        const values = await form.validateFields();
        const basePayload: AttributeInput = {
          name: values.name.trim(),
          code: values.code.trim(),
          value_type: values.value_type,
          validation: validationPayload(values.value_type, values.validation ?? {}),
          unit: values.value_type === "number" ? values.unit?.trim() || null : null,
          sort_order: values.sort_order ?? null,
          is_active: values.is_active ?? true,
        };
        if (target) {
          const updatePayload: AttributeUpdate = {
            ...basePayload,
            revision: target.revision,
          };
          await commerceApi.updateAttribute(target.id, updatePayload);
        } else {
          const createPayload: AttributeInput = basePayload;
          await commerceApi.createAttribute(createPayload);
        }
        message.success("公共属性已保存");
        await done();
        close();
      }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={
          target
            ? {
                name: target.name,
                code: target.code,
                value_type: target.value_type,
                unit: target.unit ?? null,
                validation: target.validation,
                sort_order: target.sort_order ?? null,
                is_active: target.is_active,
              }
            : {
                name: "",
                code: "",
                value_type: "select",
                unit: null,
                validation: defaultValidation("select"),
                sort_order: null,
                is_active: true,
              }
        }
      >
        <Form.Item
          name="name"
          label="属性名称"
          rules={[{ required: true, whitespace: true, max: 100 }]}
        >
          <Input maxLength={100} placeholder="例如：颜色、尺寸、材质" />
        </Form.Item>
        <Form.Item
          name="code"
          label="属性编码"
          rules={[
            { required: true, whitespace: true, max: 64 },
            { pattern: /^[A-Za-z0-9_-]+$/, message: "只能使用字母、数字、下划线或连字符" },
          ]}
        >
          <Input maxLength={64} placeholder="唯一英文编码，例如：color、size" disabled={Boolean(target)} />
        </Form.Item>
        <Form.Item name="value_type" label="属性类型" rules={[{ required: true }]}>
          <Radio.Group
            disabled={Boolean(target)}
            onChange={(event) => {
              const nextValueType = event.target.value as AttributeValueType;
              form.setFieldsValue({
                value_type: nextValueType,
                unit: nextValueType === "number" ? form.getFieldValue("unit") ?? null : null,
                validation: defaultValidation(nextValueType),
              });
            }}
          >
            {valueTypeOptions.map((option) => (
              <Radio key={option.value} value={option.value}>{option.label}</Radio>
            ))}
          </Radio.Group>
        </Form.Item>
        <ValueTypeValidationFields valueType={valueType} />
        <Form.Item name="sort_order" label="排序">
          <InputNumber min={0} precision={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="is_active" label="启用状态" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </EditorModal>
  );
}

function ValueEditorModal({
  attribute,
  attributeRevision,
  target,
  done,
  close,
}: {
  attribute: AttributeRead;
  attributeRevision: number;
  target: StandardValueRead | null;
  done: () => Promise<void>;
  close: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<{
    code: string;
    name: string;
    sort_order?: number | null;
    is_active?: boolean;
  }>();

  return (
    <EditorModal
      title={target ? "编辑候选值" : "添加候选值"}
      onClose={close}
      onSave={async () => {
        const values = await form.validateFields();
        if (target) {
          const updatePayload: StandardValueUpdate = {
            attribute_revision: attributeRevision,
            code: values.code.trim(),
            name: values.name.trim(),
            sort_order: values.sort_order ?? null,
            is_active: values.is_active ?? true,
            revision: target.revision,
          };
          await commerceApi.updateAttributeValue(attribute.id, target.id, updatePayload);
          message.success("候选值已更新");
        } else {
          const createPayload: StandardValueInput = {
            attribute_revision: attributeRevision,
            code: values.code.trim(),
            name: values.name.trim(),
            sort_order: values.sort_order ?? null,
            is_active: values.is_active ?? true,
          };
          await commerceApi.createAttributeValue(attribute.id, createPayload);
          message.success("候选值已添加");
        }
        await done();
        close();
      }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={
          target
            ? {
                code: target.code,
                name: target.name,
                sort_order: target.sort_order ?? null,
                is_active: target.is_active,
              }
            : {
                code: "",
                name: "",
                sort_order: null,
                is_active: true,
              }
        }
      >
        <Form.Item
          name="name"
          label="候选值名称"
          rules={[{ required: true, whitespace: true, max: 100, message: "请输入候选值名称" }]}
        >
          <Input maxLength={100} placeholder="例如：曜石黑、XL、休闲娱乐" />
        </Form.Item>
        <Form.Item
          name="code"
          label="候选值编码"
          rules={[
            { required: true, whitespace: true, max: 64, message: "请输入候选值编码" },
            { pattern: /^[A-Za-z0-9_-]+$/, message: "只能使用字母、数字、下划线或连字符" },
          ]}
        >
          <Input
            maxLength={64}
            placeholder="唯一英文编码，例如：color_obsidian_black、size_xl"
            disabled={Boolean(target)}
          />
        </Form.Item>
        <Form.Item name="sort_order" label="排序">
          <InputNumber min={0} precision={0} style={{ width: "100%" }} placeholder="数值越小越靠前，默认置空" />
        </Form.Item>
        <Form.Item name="is_active" label="启用状态" valuePropName="checked">
          <Switch checkedChildren="启用" unCheckedChildren="停用" />
        </Form.Item>
      </Form>
    </EditorModal>
  );
}

function ValuesDrawer({
  attribute,
  close,
}: {
  attribute: AttributeRead;
  close: () => void;
}) {
  const { message } = App.useApp();
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const canUpdate = canAccess(admin, "spec-attributes:update");
  const [valueModal, setValueModal] = useState<{ target: StandardValueRead | null } | null>(null);
  const [attributeRevision, setAttributeRevision] = useState(attribute.revision);
  const [valueSearch, setValueSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<boolean | undefined>(undefined);
  const [selectedValues, setSelectedValues] = useState<StandardValueRead[]>([]);

  const query = useQuery({
    queryKey: ["attribute-values", attribute.id],
    queryFn: () => commerceApi.attributeValues(attribute.id),
  });

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["attribute-values", attribute.id] });
    await client.invalidateQueries({ queryKey: ["commerce-spec-attributes"] });
  };

  useEffect(() => {
    setSelectedValues([]);
  }, [valueSearch, statusFilter]);

  const normalizedValueSearch = valueSearch.trim().toLocaleLowerCase();
  const filteredValues = (query.data ?? []).filter((row) => {
    const matchesSearch =
      !normalizedValueSearch
      || row.code.toLocaleLowerCase().includes(normalizedValueSearch)
      || row.name.toLocaleLowerCase().includes(normalizedValueSearch);
    const matchesStatus = statusFilter === undefined || row.is_active === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const onValueSaved = async () => {
    setAttributeRevision((revision) => revision + 1);
    setSelectedValues([]);
    await refresh();
  };

  const batchStatus = useLockedMutation({
    mutationFn: (isActive: boolean) =>
      commerceApi.attributeValuesStatus(attribute.id, {
        targets: selectedValues.map(({ id, revision }) => ({ id, revision })),
        is_active: isActive,
      }),
    onSuccess: async ({ completed_count }, isActive) => {
      message.success(`已批量${isActive ? "启用" : "停用"} ${completed_count} 个标准候选值`);
      setAttributeRevision((revision) => revision + 1);
      setSelectedValues([]);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const toggleSingleStatus = async (row: StandardValueRead) => {
    try {
      const nextActive = !row.is_active;
      await commerceApi.attributeValuesStatus(attribute.id, {
        targets: [{ id: row.id, revision: row.revision }],
        is_active: nextActive,
      });
      message.success(`候选值已${nextActive ? "启用" : "停用"}`);
      await onValueSaved();
    } catch (error) {
      message.error(errorMessage(error));
    }
  };

  const deleteSingleValue = async (row: StandardValueRead) => {
    try {
      await commerceApi.deleteAttributeValue(attribute.id, row.id);
      message.success("候选值已删除");
      await onValueSaved();
    } catch (error) {
      message.error(errorMessage(error));
    }
  };

  const busy = batchStatus.isPending;

  return (
    <Drawer
      title={`【${attribute.name}】候选值管理`}
      open
      width={860}
      closable={!busy}
      keyboard={!busy}
      mask={{ closable: false }}
      onClose={() => { if (!busy) close(); }}
    >
      <Alert
        type="info"
        title="标准候选值供商品建档时快速采用；停用已引用的候选值会影响关联 SKU 的可售性；已被商品采用的候选值不可物理删除。"
        className="mb-16"
      />
      <Space className="mb-16" wrap>
        <Input
          allowClear
          disabled={busy}
          placeholder="按候选值名称或编码筛选"
          prefix={<SearchOutlined />}
          style={{ width: 260 }}
          value={valueSearch}
          onChange={(event) => setValueSearch(event.target.value)}
        />
        <Select
          disabled={busy}
          style={{ width: 130 }}
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: "全部状态", value: undefined },
            { label: "仅显示启用", value: true },
            { label: "仅显示停用", value: false },
          ]}
        />
      </Space>
      <ResourceTable
        title="标准候选值列表"
        rows={filteredValues}
        loading={query.isLoading}
        fetching={query.isFetching}
        error={query.error}
        retry={query.refetch}
        selection={
          canUpdate
            ? {
                keys: selectedValues.map((row) => row.id),
                onChange: (_, rows) => setSelectedValues(rows),
                disabled: busy,
              }
            : undefined
        }
        toolbar={
          canUpdate
            ? [
                <Button
                  key="create"
                  type="primary"
                  icon={<PlusOutlined />}
                  disabled={busy}
                  onClick={() => setValueModal({ target: null })}
                >
                  添加候选值
                </Button>,
                <Space key="batch">
                  <Button
                    icon={<PoweroffOutlined />}
                    disabled={!selectedValues.length || busy}
                    onClick={() => batchStatus.mutate(true)}
                  >
                    批量启用
                  </Button>
                  <Button
                    icon={<PoweroffOutlined />}
                    disabled={!selectedValues.length || busy}
                    onClick={() => batchStatus.mutate(false)}
                  >
                    批量停用
                  </Button>
                </Space>,
              ]
            : undefined
        }
        columns={[
          { title: "编码", dataIndex: "code", ellipsis: true },
          { title: "候选值名称", dataIndex: "name", ellipsis: true },
          {
            title: "排序",
            dataIndex: "sort_order",
            render: (v) => v ?? "-",
          },
          {
            title: "状态",
            render: (_, row) => (
              <Tooltip title={row.is_active ? "当前候选值可供商品采用" : "停用会影响引用该值的 SKU 可售性"}>
                <Tag color={row.is_active ? "success" : "default"}>
                  {row.is_active ? "启用" : "停用"}
                </Tag>
              </Tooltip>
            ),
          },
          {
            title: "版本",
            dataIndex: "revision",
            render: (v) => `v${v}`,
          },
          {
            title: "操作",
            width: "1%",
            render: (_, row) =>
              canUpdate ? (
                <Space size="small">
                  <Button
                    size="small"
                    disabled={busy}
                    icon={<EditOutlined />}
                    onClick={() => setValueModal({ target: row })}
                  >
                    编辑
                  </Button>
                  {row.is_active ? (
                    <Popconfirm
                      title="确认停用候选值？"
                      description="停用后新商品建档将无法选用，存量关联商品不受影响。"
                      okText="确认停用"
                      cancelText="取消"
                      onConfirm={() => toggleSingleStatus(row)}
                    >
                      <Button size="small" disabled={busy}>
                        停用
                      </Button>
                    </Popconfirm>
                  ) : (
                    <Button
                      size="small"
                      type="primary"
                      ghost
                      disabled={busy}
                      onClick={() => toggleSingleStatus(row)}
                    >
                      启用
                    </Button>
                  )}
                  <Popconfirm
                    title="确认删除候选值？"
                    description="仅未被任何商品采用的候选值允许物理删除；已采用的会被系统拦截并建议停用。"
                    okText="确认删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => deleteSingleValue(row)}
                  >
                    <Button size="small" danger disabled={busy} icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ) : null,
          },
        ]}
      />
      {valueModal && (
        <ValueEditorModal
          attribute={attribute}
          attributeRevision={attributeRevision}
          target={valueModal.target}
          done={onValueSaved}
          close={() => setValueModal(null)}
        />
      )}
    </Drawer>
  );
}

export function SpecAttributesPage() {
  const { message } = App.useApp();
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const [filtersForm] = Form.useForm<AttributeFilterValues>();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [valueTypeFilter, setValueTypeFilter] = useState<AttributeValueType>();
  const [activeFilter, setActiveFilter] = useState<boolean>();
  const [selected, setSelected] = useState<AttributeRead[]>([]);
  const [edit, setEdit] = useState<{ target: AttributeRead | null }>();
  const [manageValues, setManageValues] = useState<AttributeRead | null>(null);

  const allowed = canAccess(admin, "spec-attributes:read");
  const canCreate = canAccess(admin, "spec-attributes:create");
  const canUpdate = canAccess(admin, "spec-attributes:update");

  const query = useQuery({
    queryKey: ["commerce-spec-attributes", page, search, valueTypeFilter, activeFilter],
    queryFn: () => commerceApi.attributes(page, 20, {
      search: search || undefined,
      value_type: valueTypeFilter,
      is_active: activeFilter,
    }),
    enabled: allowed,
  });

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["commerce-spec-attributes"] });
  };
  const batchStatus = useLockedMutation({
    mutationFn: (isActive: boolean) =>
      commerceApi.attributesStatus({
        targets: selected.map(({ id, revision }) => ({ id, revision })),
        is_active: isActive,
      }),
    onSuccess: async ({ completed_count }, isActive) => {
      message.success(`已批量${isActive ? "启用" : "停用"} ${completed_count} 个公共属性`);
      setSelected([]);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const resetFilters = () => {
    filtersForm.resetFields();
    setSearch("");
    setValueTypeFilter(undefined);
    setActiveFilter(undefined);
    setSelected([]);
    setPage(1);
  };

  return (
    <PageFrame
      title="规格属性"
      description="维护系统公共销售规格与描述属性库，以及标准候选值集合。"
    >
      {!allowed ? (
        <Alert type="warning" title="无权查看规格属性库" />
      ) : (
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            title="公共属性可作为销售规格或描述属性采用；停用已引用属性会影响关联商品的可售性。"
          />
          <Form
            disabled={batchStatus.isPending}
            form={filtersForm}
            initialValues={{ value_type: "", active: "all" }}
            layout="inline"
            onFinish={(values: AttributeFilterValues) => {
              setSearch(values.search?.trim() || "");
              setValueTypeFilter(values.value_type || undefined);
              setActiveFilter(values.active === "active" ? true : values.active === "inactive" ? false : undefined);
              setSelected([]);
              setPage(1);
            }}
          >
            <Form.Item name="search">
              <Input
                allowClear
                placeholder="搜索属性名称或编码"
                prefix={<SearchOutlined />}
                style={{ width: 240 }}
              />
            </Form.Item>
            <Form.Item name="value_type">
              <Select
                options={[{ label: "全部类型", value: "" }, ...valueTypeOptions]}
                style={{ width: 160 }}
              />
            </Form.Item>
            <Form.Item name="active">
              <Select
                options={[
                  { label: "全部状态", value: "all" },
                  { label: "已启用", value: "active" },
                  { label: "已停用", value: "inactive" },
                ]}
                style={{ width: 130 }}
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">查询</Button>
                <Button disabled={batchStatus.isPending} onClick={resetFilters}>重置</Button>
              </Space>
            </Form.Item>
          </Form>
          <ResourceTable
            title="属性库列表"
            rows={query.data?.items ?? []}
            loading={query.isLoading}
            fetching={query.isFetching}
            error={query.error}
            retry={query.refetch}
            page={page}
            total={query.data?.total}
            onPage={(next) => {
              if (!batchStatus.isPending) {
                setSelected([]);
                setPage(next);
              }
            }}
            selection={
              canUpdate
                ? {
                    keys: selected.map((row) => row.id),
                    onChange: (_, rows) => setSelected(rows),
                    disabled: batchStatus.isPending,
                  }
                : undefined
            }
            toolbar={[
              ...(canUpdate
                ? [
                    <Space key="batch">
                      <Button
                        icon={<PoweroffOutlined />}
                        disabled={!selected.length || batchStatus.isPending}
                        onClick={() => batchStatus.mutate(true)}
                      >
                        批量启用
                      </Button>
                      <Button
                        icon={<PoweroffOutlined />}
                        disabled={!selected.length || batchStatus.isPending}
                        onClick={() => batchStatus.mutate(false)}
                      >
                        批量停用
                      </Button>
                    </Space>,
                  ]
                : []),
              ...(canCreate
                ? [
                    <Button
                      key="new"
                      type="primary"
                      icon={<PlusOutlined />}
                      disabled={batchStatus.isPending}
                      onClick={() => setEdit({ target: null })}
                    >
                      新建属性
                    </Button>,
                  ]
                : []),
            ]}
            columns={[
              { title: "属性名称", dataIndex: "name", ellipsis: true },
              { title: "属性编码", dataIndex: "code", ellipsis: true },
              {
                title: "值类型",
                dataIndex: "value_type",
                render: (value) => {
                  if (value === "select") return <Tag color="blue">下拉选择</Tag>;
                  if (value === "multi_select") return <Tag color="blue">下拉多选</Tag>;
                  if (value === "number") return <Tag color="purple">数值</Tag>;
                  return <Tag color="cyan">文本</Tag>;
                },
              },
              {
                title: "状态",
                render: (_, row) => (
                  <Tooltip title={row.is_active ? "当前属性可供分类和商品采用" : "停用会影响已引用商品的可售性"}>
                    <Tag color={row.is_active ? "success" : "default"}>
                      {row.is_active ? "启用" : "停用"}
                    </Tag>
                  </Tooltip>
                ),
              },
              {
                title: "版本",
                dataIndex: "revision",
                render: (value) => `v${value}`,
              },
              {
                title: "操作",
                width: "1%",
                render: (_, row) => (
                  <Space wrap={false}>
                    {(row.value_type === "select" || row.value_type === "multi_select") && (
                      <Button
                        disabled={batchStatus.isPending}
                        icon={<UnorderedListOutlined />}
                        onClick={() => setManageValues(row)}
                      >
                        候选值
                      </Button>
                    )}
                    {canUpdate && (
                      <Button
                        disabled={batchStatus.isPending}
                        icon={<EditOutlined />}
                        onClick={() => setEdit({ target: row })}
                      >
                        编辑
                      </Button>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      )}
      {edit && (
        <AttributeEditor
          target={edit.target}
          close={() => setEdit(undefined)}
          done={refresh}
        />
      )}
      {manageValues && (
        <ValuesDrawer
          attribute={manageValues}
          close={() => setManageValues(null)}
        />
      )}
    </PageFrame>
  );
}

export default SpecAttributesPage;
