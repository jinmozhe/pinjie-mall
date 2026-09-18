import type { InventoryAdjustment, InventoryRead, SkuRead } from "@pinjie/api-client";
import { EditOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Drawer, Form, Input, InputNumber, message } from "antd";
import { useRef, useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { QueryState, formatTime } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";

function AdjustmentEditor({ inventory, done, close }: { inventory: InventoryRead; done: () => Promise<void>; close: () => void }) {
  const [form] = Form.useForm<Pick<InventoryAdjustment, "quantity_delta" | "reason">>();
  const request = useRef<InventoryAdjustment | null>(null);
  const [submitted, setSubmitted] = useState(false);
  return <EditorModal title="调整可售库存" onClose={close} onSave={async () => {
    if (!request.current) { const values = await form.validateFields(); request.current = { ...values, request_id: globalThis.crypto.randomUUID(), revision: inventory.revision }; setSubmitted(true); }
    await commerceApi.adjustInventory(inventory.sku_id, request.current);
    message.success("库存调整已完成"); await done(); close();
  }}>
    <Alert type="info" title={`当前可售 ${inventory.available}，占用 ${inventory.reserved}。重试保持相同目标、版本和调整内容。`} />
    <Form form={form} disabled={submitted} layout="vertical">
      <Form.Item name="quantity_delta" label="调整数量，增加为正，减少为负" rules={[{ required: true }, { validator: (_, value: number) => value === 0 ? Promise.reject(new Error("调整数量不能为零")) : Promise.resolve() }]}><InputNumber min={-1000000000} max={1000000000} precision={0} /></Form.Item>
      <Form.Item name="reason" label="调整原因" rules={[{ required: true, whitespace: true, max: 200 }]}><Input.TextArea rows={3} maxLength={200} /></Form.Item>
    </Form>
  </EditorModal>;
}

export function InventoryPanel({ sku, close }: { sku: SkuRead; close: () => void }) {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<InventoryRead>();
  const inventory = useQuery({ queryKey: ["commerce-inventory", sku.id], queryFn: () => commerceApi.inventory(sku.id) });
  const movements = useQuery({ queryKey: ["commerce-movements", sku.id, page], queryFn: () => commerceApi.movements(sku.id, page) });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["commerce-inventory", sku.id] }), client.invalidateQueries({ queryKey: ["commerce-movements", sku.id] })]); };
  return <Drawer open title={`库存：${sku.code}`} width={900} onClose={close}>
    <QueryState loading={inventory.isLoading} error={inventory.error ? errorMessage(inventory.error) : undefined} onRetry={() => void inventory.refetch()} />
    {inventory.data && <Descriptions items={[
      { key: "available", label: "可售库存", children: inventory.data.available }, { key: "reserved", label: "占用库存", children: inventory.data.reserved },
      { key: "action", label: "操作", children: canAccess(admin, "inventory:adjust") && <Button icon={<EditOutlined />} onClick={() => setEdit(inventory.data)}>调整库存</Button> },
    ]} />}
    <ResourceTable title="库存调整流水" rows={movements.data?.items ?? []} loading={movements.isLoading} fetching={movements.isFetching} error={movements.error} retry={movements.refetch}
      page={page} total={movements.data?.total} onPage={setPage} columns={[
        { title: "时间", dataIndex: "created_at", render: (_, row) => formatTime(row.created_at) },
        { title: "调整量", dataIndex: "quantity_delta" }, { title: "调整前", dataIndex: "before_available" }, { title: "调整后", dataIndex: "after_available" },
        { title: "原因", dataIndex: "reason", ellipsis: true }, { title: "操作者", dataIndex: "actor_id", ellipsis: true },
      ]} />
    {edit && <AdjustmentEditor inventory={edit} done={refresh} close={() => setEdit(undefined)} />}
  </Drawer>;
}
