import type {
  AttributeInput,
  AttributeRead,
  AttributeUpdate,
  StandardValueInput,
  StandardValueRead,
  StandardValueUpdate,
} from "@pinjie/api-client";
import { EditOutlined, PlusOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Drawer, Form, Input, InputNumber, Radio, Space, Switch, Tag, message } from "antd";
import { useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { useLockedMutation } from "@/lib/useLockedMutation";

function AttributeEditor({
  target,
  done,
  close,
}: {
  target: AttributeRead | null;
  done: () => Promise<void>;
  close: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <EditorModal
      title={target ? "编辑公共属性" : "新建公共属性"}
      onClose={close}
      onSave={async () => {
        const values = await form.validateFields();
        const basePayload = {
          name: values.name.trim(),
          code: values.code.trim(),
          value_type: values.value_type,
          validation: target?.validation ?? { schema_version: 1 as const },
          unit: target?.unit ?? null,
          sort_order: target?.sort_order ?? null,
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
          target ?? {
            name: "",
            code: "",
            value_type: "select",
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
          rules={[{ required: true, whitespace: true, max: 50 }]}
        >
          <Input maxLength={50} placeholder="唯一英文编码，例如：color、size" disabled={Boolean(target)} />
        </Form.Item>
        <Form.Item name="value_type" label="属性类型" rules={[{ required: true }]}>
          <Radio.Group disabled={Boolean(target)}>
            <Radio value="select">下拉单选 (select)</Radio>
            <Radio value="multi_select">下拉多选 (multi_select)</Radio>
            <Radio value="text">自由文本 (text)</Radio>
            <Radio value="number">数值 (number)</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item name="is_active" label="启用状态" valuePropName="checked">
          <Switch />
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
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const canUpdate = canAccess(admin, "spec-attributes:update");
  const [form] = Form.useForm();
  const [editingValue, setEditingValue] = useState<StandardValueRead | null>(null);
  const [attributeRevision, setAttributeRevision] = useState(attribute.revision);

  const query = useQuery({
    queryKey: ["attribute-values", attribute.id],
    queryFn: () => commerceApi.attributeValues(attribute.id),
  });

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["attribute-values", attribute.id] });
    await client.invalidateQueries({ queryKey: ["commerce-spec-attributes"] });
  };

  const onSave = async () => {
    const values = await form.validateFields();
    if (editingValue) {
      const updatePayload: StandardValueUpdate = {
        attribute_revision: attributeRevision,
        code: values.code.trim(),
        name: values.name.trim(),
        sort_order: values.sort_order ?? null,
        is_active: values.is_active ?? true,
        revision: editingValue.revision,
      };
      await commerceApi.updateAttributeValue(attribute.id, editingValue.id, updatePayload);
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
    setAttributeRevision((revision) => revision + 1);
    form.resetFields();
    setEditingValue(null);
    await refresh();
  };
  const save = useLockedMutation({ mutationFn: onSave });

  return (
    <Drawer
      title={`【${attribute.name}】候选值管理`}
      open
      width={720}
      closable={!save.isPending}
      keyboard={!save.isPending}
      maskClosable={false}
      onClose={() => { if (!save.isPending) close(); }}
    >
      <Alert
        type="info"
        title="标准候选值供商品在建档时快速选择采用，避免不同商品书写歧义。"
        className="mb-16"
      />
      {canUpdate && (
        <Form
          disabled={save.isPending}
          form={form}
          layout="inline"
          className="mb-16"
          initialValues={{ sort_order: null, is_active: true }}
        >
          <Form.Item
            name="code"
            rules={[{ required: true, whitespace: true, max: 64 }]}
          >
            <Input placeholder="编码 (如: BLK)" style={{ width: 140 }} disabled={Boolean(editingValue)} />
          </Form.Item>
          <Form.Item
            name="name"
            rules={[{ required: true, whitespace: true, max: 100 }]}
          >
            <Input placeholder="候选值名称 (如: 曜石黑)" style={{ width: 180 }} />
          </Form.Item>
          <Form.Item name="sort_order">
            <InputNumber placeholder="排序" min={0} precision={0} style={{ width: 80 }} />
          </Form.Item>
          <Form.Item name="is_active" valuePropName="checked">
            <Switch checkedChildren="启" unCheckedChildren="停" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" loading={save.isPending} onClick={() => save.mutate(undefined)}>
                {editingValue ? "保存修改" : "添加候选值"}
              </Button>
              {editingValue && (
                <Button
                  onClick={() => {
                    setEditingValue(null);
                    form.resetFields();
                  }}
                >
                  取消
                </Button>
              )}
            </Space>
          </Form.Item>
        </Form>
      )}
      {save.error && <Alert type="error" showIcon title={save.error.message || "请检查表单字段"} className="mb-16" />}
      <ResourceTable
        title="标准候选值列表"
        rows={query.data ?? []}
        loading={query.isLoading}
        fetching={query.isFetching}
        error={query.error}
        retry={query.refetch}
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
              <Tag color={row.is_active ? "success" : "default"}>
                {row.is_active ? "启用" : "停用"}
              </Tag>
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
                <Button
                  size="small"
                  disabled={save.isPending}
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditingValue(row);
                    form.setFieldsValue({
                      code: row.code,
                      name: row.name,
                      sort_order: row.sort_order,
                      is_active: row.is_active,
                    });
                  }}
                >
                  编辑
                </Button>
              ) : null,
          },
        ]}
      />
    </Drawer>
  );
}

export function SpecAttributesPage() {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<{ target: AttributeRead | null }>();
  const [manageValues, setManageValues] = useState<AttributeRead | null>(null);

  const allowed = canAccess(admin, "spec-attributes:read");
  const canCreate = canAccess(admin, "spec-attributes:create");
  const canUpdate = canAccess(admin, "spec-attributes:update");

  const query = useQuery({
    queryKey: ["commerce-spec-attributes", page],
    queryFn: () => commerceApi.attributes(page),
    enabled: allowed,
  });

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["commerce-spec-attributes"] });
  };

  return (
    <PageFrame
      title="规格属性"
      description="维护系统公共销售规格与描述属性库，以及标准候选值集合。"
    >
      {!allowed ? (
        <Alert type="warning" title="无权查看规格属性库" />
      ) : (
        <ResourceTable
          title="属性库列表"
          rows={query.data?.items ?? []}
          loading={query.isLoading}
          fetching={query.isFetching}
          error={query.error}
          retry={query.refetch}
          page={page}
          total={query.data?.total}
          onPage={setPage}
          toolbar={[
            canCreate && (
              <Button
                key="new"
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setEdit({ target: null })}
              >
                新建属性
              </Button>
            ),
          ]}
          columns={[
            { title: "属性名称", dataIndex: "name", ellipsis: true },
            { title: "属性编码", dataIndex: "code", ellipsis: true },
            {
              title: "值类型",
              dataIndex: "value_type",
              render: (v) => {
                if (v === "select") return <Tag color="blue">下拉选择</Tag>;
                if (v === "multi_select") return <Tag color="blue">下拉多选</Tag>;
                if (v === "number") return <Tag color="purple">数值</Tag>;
                return <Tag color="cyan">文本</Tag>;
              },
            },
            {
              title: "状态",
              render: (_, row) => (
                <Tag color={row.is_active ? "success" : "default"}>
                  {row.is_active ? "启用" : "停用"}
                </Tag>
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
              render: (_, row) => (
                <Space>
                  {(row.value_type === "select" || row.value_type === "multi_select") && (
                    <Button
                      icon={<UnorderedListOutlined />}
                      onClick={() => setManageValues(row)}
                    >
                      候选值
                    </Button>
                  )}
                  {canUpdate && (
                    <Button
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
