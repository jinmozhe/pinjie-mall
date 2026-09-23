import type { CategoryInput, CategoryRead } from "@pinjie/api-client";
import { EditOutlined, PlusOutlined, PoweroffOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, InputNumber, Select, Space, Switch, Tag, message } from "antd";
import { useState } from "react";

import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { EditorModal } from "@/components/EditorModal";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";

function CategoryEditor({ target, rows, done, close }: { target: CategoryRead | null; rows: CategoryRead[]; done: () => Promise<void>; close: () => void }) {
  const [form] = Form.useForm<CategoryInput>();
  return <EditorModal title={target ? "编辑商品分类" : "新建商品分类"} onClose={close} onSave={async () => {
    const values = await form.validateFields();
    const input = { ...values, parent_id: values.parent_id ?? null };
    if (target) await commerceApi.updateCategory(target.id, { ...input, revision: target.revision });
    else await commerceApi.createCategory(input);
    message.success("分类已保存"); await done(); close();
  }}>
    <Form form={form} layout="vertical" initialValues={target ?? { sort_order: null, is_active: true, parent_id: null }}>
      <Form.Item name="name" label="分类名称" rules={[{ required: true, whitespace: true, max: 100 }]}><Input maxLength={100} /></Form.Item>
      <Form.Item name="parent_id" label="上级分类"><Select allowClear placeholder="顶级分类" options={rows.filter((row) => row.id !== target?.id).map((row) => ({ value: row.id, label: row.name }))} /></Form.Item>
      <Form.Item name="sort_order" label="排序权重" extra="值越小越靠前，不填则自动排最后"><InputNumber min={0} precision={0} style={{ width: "100%" }} /></Form.Item>
      <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
      <Alert type="info" title="分类最多三级；停用上级分类会使其下商品不可售。" />
    </Form>
  </EditorModal>;
}

export function CategoriesPage() {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const allowed = canAccess(admin, "product-categories:read");
  const write = canAccess(admin, "product-categories:update");
  const query = useQuery({ queryKey: ["commerce-categories"], queryFn: commerceApi.categories, enabled: allowed });
  const [edit, setEdit] = useState<{ target: CategoryRead | null }>();
  const [selected, setSelected] = useState<CategoryRead[]>([]);
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["commerce-categories"] }); };
  const batch = useLockedMutation({ mutationFn: (active: boolean) => commerceApi.categoriesStatus({ targets: selected.map(({ id, revision }) => ({ id, revision })), is_active: active }),
    onSuccess: async () => { message.success("分类状态已更新"); setSelected([]); await refresh(); }, onError: (error) => message.error(errorMessage(error)) });
  return <PageFrame title="商品分类" description="维护分类层级、排序与可售状态。">
    {!allowed ? <Alert type="warning" title="无权查看商品分类" /> : <ResourceTable title="商品分类" rows={query.data ?? []} loading={query.isLoading} fetching={query.isFetching} error={query.error} retry={query.refetch}
      selection={write ? { keys: selected.map((row) => row.id), onChange: (_, rows) => setSelected(rows), disabled: batch.isPending } : undefined}
      toolbar={[
        write && <Space key="batch"><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending} onClick={() => batch.mutate(true)}>批量启用</Button><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending} onClick={() => batch.mutate(false)}>批量停用</Button></Space>,
        canAccess(admin, "product-categories:create") && <Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => setEdit({ target: null })}>新建分类</Button>,
      ]} columns={[
        { title: "名称", dataIndex: "name", ellipsis: true },
        { title: "上级分类", render: (_, row) => query.data?.find((item) => item.id === row.parent_id)?.name ?? "顶级分类" },
        { title: "排序", render: (_: unknown, row: CategoryRead) => row.sort_order ?? "-" },
        { title: "状态", render: (_, row) => <Tag color={row.is_active ? "success" : "default"}>{row.is_active ? "启用" : "停用"}</Tag> },
        { title: "操作", width: "1%", render: (_, row) => (write ? <Button icon={<EditOutlined />} disabled={batch.isPending} onClick={() => setEdit({ target: row })}>编辑</Button> : null) },
      ]} />}
    {edit && <CategoryEditor target={edit.target} rows={query.data ?? []} close={() => setEdit(undefined)} done={refresh} />}
  </PageFrame>;
}

export default CategoriesPage;
