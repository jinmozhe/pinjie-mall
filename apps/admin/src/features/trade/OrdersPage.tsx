import type { FulfillmentRead, OrderRead } from "@pinjie/api-client";
import { EyeOutlined, SendOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Drawer, Form, Input, Tag, message } from "antd";
import { useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { CommerceList } from "@/components/CommerceList";
import { PageFrame, QueryState, formatTime } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";

function FulfillmentEditor({ order, current, close, done }: { order: OrderRead; current: FulfillmentRead; close: () => void; done: () => Promise<void> }) {
  const [form] = Form.useForm<{ carrier?: string; tracking_number?: string; delivery_reference?: string }>();
  const physical = current.product_type === "physical";
  return <EditorModal title={physical ? "管理员发货" : "完成虚拟交付"} onClose={close} onSave={async () => {
    const values = await form.validateFields();
    if (physical) {
      if (!values.carrier?.trim() || !values.tracking_number?.trim()) throw new Error("请填写物流公司和单号");
      await commerceApi.ship(order.id, { carrier: values.carrier.trim(), tracking_number: values.tracking_number.trim(), revision: current.revision });
    } else {
      if (!values.delivery_reference?.trim()) throw new Error("请填写交付凭证引用");
      await commerceApi.deliverVirtual(order.id, { delivery_reference: values.delivery_reference.trim(), revision: current.revision });
    }
    message.success(physical ? "已提交发货" : "已完成虚拟交付"); await done(); close();
  }}>
    <Alert type="info" title="提交时会重新校验订单状态与履约版本，冲突时保留当前输入。" />
    <Form form={form} layout="vertical">
      {physical ? <><Form.Item name="carrier" label="物流公司" rules={[{ required: true, whitespace: true, max: 80 }]}><Input maxLength={80} /></Form.Item><Form.Item name="tracking_number" label="物流单号" rules={[{ required: true, whitespace: true, max: 120 }]}><Input maxLength={120} /></Form.Item></> : <Form.Item name="delivery_reference" label="交付凭证引用" rules={[{ required: true, whitespace: true, max: 200 }]}><Input.TextArea rows={4} maxLength={200} /></Form.Item>}
    </Form>
  </EditorModal>;
}

function OrderDetail({ id, close }: { id: string; close: () => void }) {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const order = useQuery({ queryKey: ["commerce-order", id], queryFn: () => commerceApi.order(id) });
  const fulfillment = useQuery({ queryKey: ["commerce-fulfillment", id], queryFn: () => commerceApi.fulfillment(id), enabled: order.data?.status === "paid" });
  const [edit, setEdit] = useState<{ order: OrderRead; current: FulfillmentRead }>();
  const [accepting, setAccepting] = useState(false);
  const refresh = async () => { await Promise.all([order.refetch(), fulfillment.refetch(), client.invalidateQueries({ queryKey: ["commerce-orders"] })]); };
  return <Drawer open width={900} title="订单详情" onClose={close}>
    <QueryState loading={order.isLoading || fulfillment.isLoading} error={order.error ? errorMessage(order.error) : fulfillment.error ? errorMessage(fulfillment.error) : undefined} onRetry={() => { void order.refetch(); void fulfillment.refetch(); }} />
    {order.data && <>
      <Descriptions column={{ xs: 1, sm: 2 }} items={[{ key: "id", label: "订单号", children: order.data.id }, { key: "status", label: "状态", children: order.data.status }, { key: "type", label: "类型", children: order.data.product_type === "physical" ? "实物" : "虚拟" }, { key: "amount", label: "应付金额", children: `¥${order.data.total_amount}` }, { key: "created", label: "创建时间", children: formatTime(order.data.created_at) }, { key: "address", label: "收货快照", children: order.data.address_snapshot ? JSON.stringify(order.data.address_snapshot) : "虚拟订单无地址" }]} />
      {order.data && order.data.status === "paid" && order.data.acceptance_status === "pending" && canAccess(admin, "orders:accept") && <Button loading={accepting} onClick={async () => { setAccepting(true); try { await commerceApi.acceptOrder(order.data!.id, { revision: order.data!.revision }); message.success("已接单"); await refresh(); } finally { setAccepting(false); } }}>接单</Button>}
      {fulfillment.data && <Alert type="info" showIcon title={`履约状态：${fulfillment.data.status}`} action={canAccess(admin, fulfillment.data.product_type === "physical" ? "fulfillments:ship" : "fulfillments:deliver-virtual") && ["awaiting_shipment", "awaiting_delivery"].includes(fulfillment.data.status) ? <Button icon={<SendOutlined />} onClick={() => { if (order.data && fulfillment.data) setEdit({ order: order.data, current: fulfillment.data }); }}>{fulfillment.data.product_type === "physical" ? "发货" : "完成交付"}</Button> : undefined} />}
      <ResourceTable title="订单明细" rows={order.data.items} loading={false} retry={order.refetch} columns={[{ title: "商品", dataIndex: "product_name" }, { title: "SKU", dataIndex: "sku_code" }, { title: "规格", render: (_, row) => Object.entries(row.specifications ?? {}).map(([k, v]) => `${k}：${v}`).join(" / ") || "默认" }, { title: "数量", dataIndex: "quantity" }, { title: "单价", render: (_, row) => `¥${row.unit_price}` }, { title: "小计", render: (_, row) => `¥${row.line_amount}` }]} />
    </>}
    {edit && <FulfillmentEditor order={edit.order} current={edit.current} close={() => setEdit(undefined)} done={refresh} />}
  </Drawer>;
}

export function OrdersPage() {
  const [detail, setDetail] = useState<string>();
  return <PageFrame title="订单履约" description="查看订单快照、履约状态并执行受权限保护的发货或虚拟交付。">
    <CommerceList resource="orders" title="订单" load={commerceApi.orders} fields={[
      { name: "record_id", label: "订单号" }, { name: "user_id", label: "用户" },
      { name: "status", label: "状态", options: [{ label: "待付款", value: "pending_payment" }, { label: "已付款", value: "paid" }, { label: "已取消", value: "cancelled" }] },
      { name: "product_type", label: "类型", options: [{ label: "实物", value: "physical" }, { label: "虚拟", value: "virtual" }] },
    ]} columns={[{ title: "订单号", dataIndex: "id", ellipsis: true }, { title: "状态", render: (_, row) => <Tag>{row.status}</Tag> }, { title: "类型", render: (_, row) => row.product_type === "physical" ? "实物" : "虚拟" }, { title: "商品金额", render: (_, row) => `¥${row.items_amount}` }, { title: "应付", render: (_, row) => `¥${row.total_amount}` }, { title: "创建时间", render: (_, row) => formatTime(row.created_at) }, { title: "操作", width: "1%", render: (_, row) => <Button icon={<EyeOutlined />} onClick={() => setDetail(row.id)}>查看详情</Button> }]} />
    {detail && <OrderDetail id={detail} close={() => setDetail(undefined)} />}
  </PageFrame>;
}

export default OrdersPage;
