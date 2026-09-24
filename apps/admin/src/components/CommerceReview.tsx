import type { RefundRequestRead, WithdrawalRead } from "@pinjie/api-client";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Space, App } from "antd";
import { useState } from "react";

import { CommerceList } from "./CommerceList";
import { EditorModal } from "./EditorModal";
import { canAccess, useCurrentAdmin } from "@/lib/auth-context";
import { commerceApi, type CommerceFilters } from "@/lib/api/commerce";

type ReviewRow = RefundRequestRead | WithdrawalRead;

function ReviewEditor({ resource, target, close }: {
  resource: "refunds" | "withdrawals"; target: { row: ReviewRow; approve: boolean }; close: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<{ note: string }>();
  const client = useQueryClient();
  const label = resource === "refunds" ? "退款" : "提现";
  return <EditorModal title={`${target.approve ? "通过" : "驳回"}${label}申请`} onClose={close} onSave={async () => {
    const { note } = await form.validateFields();
    const executeMap = {
      refunds: { approve: commerceApi.approveRefund, reject: commerceApi.rejectRefund },
      withdrawals: { approve: commerceApi.approveWithdrawal, reject: commerceApi.rejectWithdrawal },
    };
    const execute = executeMap[resource][target.approve ? "approve" : "reject"];
    await execute(target.row.id, { note, revision: target.row.revision });
    message.success("审核结果已提交"); await client.invalidateQueries({ queryKey: [`commerce-${resource}`] }); close();
  }}>
    <Alert type="warning" title={`申请 ${target.row.id}，金额 ¥${target.row.amount}。审核通过只改变内部状态，最终资金结果由可信渠道确认。`} />
    <Form form={form} layout="vertical"><Form.Item name="note" label="审核说明" rules={[{ required: true, whitespace: true, max: 300 }]}><Input.TextArea rows={4} maxLength={300} /></Form.Item></Form>
  </EditorModal>;
}

export function CommerceReview({ resource }: { resource: "refunds" | "withdrawals" }) {
  const admin = useCurrentAdmin();
  const canReview = canAccess(admin, `${resource}:review`);
  const [target, setTarget] = useState<{ row: ReviewRow; approve: boolean }>();
  const label = resource === "refunds" ? "退款申请" : "提现申请";
  const load = async (filters: CommerceFilters): Promise<{ items: ReviewRow[]; total: number }> => resource === "refunds" ? commerceApi.refunds(filters) : commerceApi.withdrawals(filters);
  return <>
    <CommerceList<ReviewRow> resource={resource} title={label} load={load} fields={[
      { name: "record_id", label: "申请号" }, { name: "user_id", label: "用户" },
      ...(resource === "refunds" ? [{ name: "order_id" as const, label: "订单号" }] : []),
      { name: "status", label: "状态", options: [{ label: "待审核", value: "requested" }, { label: "审核通过", value: "approved" }, { label: "已驳回", value: "rejected" }, { label: "处理中", value: "processing" }, { label: "结果未知", value: "unknown" }, { label: "成功", value: "succeeded" }] },
    ]} columns={[
      { title: "申请号", dataIndex: "id", ellipsis: true },
      { title: resource === "refunds" ? "订单号" : "用户", render: (_, row) => "order_id" in row ? row.order_id : row.user_id, ellipsis: true },
      { title: "金额", dataIndex: "amount" }, { title: "状态", dataIndex: "status" },
      { title: resource === "refunds" ? "退款原因" : "收款引用", render: (_, row) => "reason" in row ? row.reason : row.destination_reference, ellipsis: true },
      { title: "审核说明", dataIndex: "review_note", ellipsis: true }, { title: "申请时间", dataIndex: "created_at" },
      { title: "操作", width: "1%", render: (_, row) => canReview && row.status === "requested" && <Space wrap={false}>
        <Button icon={<CheckOutlined />} onClick={() => setTarget({ row, approve: true })}>通过</Button>
        <Button danger icon={<CloseOutlined />} onClick={() => setTarget({ row, approve: false })}>驳回</Button>
      </Space> },
    ]} />
    {target && <ReviewEditor key={target.row.id} resource={resource} target={target} close={() => setTarget(undefined)} />}
  </>;
}
