import { PlusOutlined } from "@ant-design/icons";
import type { ReconciliationRecordCreate } from "@pinjie/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, InputNumber, Select, message } from "antd";
import { useState } from "react";

import { CommerceList } from "@/components/CommerceList";
import { EditorModal } from "@/components/EditorModal";
import { PageFrame } from "@/components/PageFrame";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";

function ReconciliationEditor({ close }: { close: () => void }) {
  const [form] = Form.useForm<ReconciliationRecordCreate>();
  const client = useQueryClient();
  return <EditorModal title="录入渠道对账记录" onClose={close} onSave={async () => {
    const values = await form.validateFields();
    await commerceApi.reconcile({ ...values, occurred_at: new Date(values.occurred_at).toISOString() });
    message.success("对账记录已保存"); await client.invalidateQueries({ queryKey: ["commerce-reconciliation-records"] }); close();
  }}>
    <Alert type="info" title="请根据可信渠道账单录入。匹配结果仅用于对账，不改变支付或订单状态。" />
    <Form form={form} layout="vertical" initialValues={{ currency: "CNY" }}>
      <Form.Item name="channel" label="渠道" rules={[{ required: true }]}><Select options={[{ label: "微信", value: "wechat" }, { label: "支付宝", value: "alipay" }]} /></Form.Item>
      <Form.Item name="channel_transaction_id" label="渠道交易号" rules={[{ required: true, whitespace: true, max: 160 }]}><Input maxLength={160} /></Form.Item>
      <Form.Item name="source_reference" label="账单来源引用" rules={[{ required: true, whitespace: true, max: 160 }]}><Input maxLength={160} /></Form.Item>
      <Form.Item name="source_hash" label="原始账单 SHA-256" rules={[{ required: true }, { pattern: /^[0-9a-f]{64}$/, message: "请输入 64 位小写十六进制摘要" }]}><Input maxLength={64} /></Form.Item>
      <Form.Item name="amount" label="金额" rules={[{ required: true }]}><InputNumber stringMode min="0.01" max="9999999999999.99" precision={2} /></Form.Item>
      <Form.Item name="currency" label="币种" rules={[{ required: true }]}><Select options={[{ label: "人民币 CNY", value: "CNY" }]} /></Form.Item>
      <Form.Item name="occurred_at" label="渠道发生时间" rules={[{ required: true }]}><Input type="datetime-local" /></Form.Item>
    </Form>
  </EditorModal>;
}

export default function ReconciliationPage() {
  const admin = useCurrentAdmin();
  const [editing, setEditing] = useState(false);
  return <PageFrame title="支付对账" description="核对渠道账单与本地支付事实，保留差异追踪记录。">
    <CommerceList resource="reconciliation-records" title="对账记录" load={commerceApi.reconciliations} fields={[
      { name: "record_id", label: "记录号" }, { name: "channel", label: "渠道", options: [{ label: "微信", value: "wechat" }, { label: "支付宝", value: "alipay" }] },
      { name: "status", label: "状态", options: [{ label: "匹配", value: "matched" }, { label: "存在差异", value: "discrepancy" }] },
    ]} toolbar={canAccess(admin, "reconciliation:import") ? [<Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => setEditing(true)}>录入对账</Button>] : []} columns={[
      { title: "记录号", dataIndex: "id", ellipsis: true }, { title: "渠道", dataIndex: "channel" }, { title: "渠道交易号", dataIndex: "channel_transaction_id", ellipsis: true },
      { title: "账单来源", dataIndex: "source_reference", ellipsis: true }, { title: "金额", dataIndex: "amount" }, { title: "状态", dataIndex: "status" },
      { title: "差异说明", dataIndex: "note", ellipsis: true }, { title: "支付记录号", dataIndex: "payment_attempt_id", ellipsis: true }, { title: "发生时间", dataIndex: "occurred_at" },
    ]} />
    {editing && <ReconciliationEditor close={() => setEditing(false)} />}
  </PageFrame>;
}
