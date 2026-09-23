import { Tag, Typography } from "antd";
import type { RefundAttemptRead } from "@pinjie/api-client";
import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function RefundExecutionsPage() {
  return (
    <PageFrame
      title="退款执行记录"
      description="独立查询渠道真实退款执行意图与资金确认结果，包括售后退款及无申请的重复支付/迟到支付异常退款；脱敏展示资金事实。"
    >
      <CommerceList<RefundAttemptRead>
        resource="refund-executions"
        title="退款执行"
        rowKey="id"
        load={commerceApi.refundExecutions}
        fields={[
          { name: "order_id", label: "关联订单号" },
          {
            name: "channel",
            label: "退款渠道",
            options: [
              { label: "微信支付 (wechat)", value: "wechat" },
              { label: "支付宝 (alipay)", value: "alipay" },
            ],
          },
          {
            name: "status",
            label: "执行状态",
            options: [
              { label: "已退款到账 (succeeded)", value: "succeeded" },
              { label: "渠道处理中 (processing)", value: "processing" },
              { label: "异常退款 (abnormal)", value: "abnormal" },
              { label: "已关闭 (closed)", value: "closed" },
            ],
          },
        ]}
        columns={[
          { title: "退款执行号", dataIndex: "id", ellipsis: true },
          { title: "商户退款参考号", dataIndex: "merchant_refund_reference", ellipsis: true },
          {
            title: "退款用途",
            dataIndex: "purpose",
            render: (p) => {
              const map: Record<string, { color: string; label: string }> = {
                after_sale: { color: "blue", label: "整单售后退款" },
                duplicate_payment: { color: "orange", label: "重复支付退款" },
                late_payment: { color: "volcano", label: "超期迟到退款" },
              };
              const item = map[String(p ?? "")] ?? { color: "default", label: String(p ?? "售后") };
              return <Tag color={item.color}>{item.label}</Tag>;
            },
          },
          {
            title: "退款渠道",
            dataIndex: "channel",
            render: (c) => (
              <Tag color={c === "wechat" ? "green" : "geekblue"}>
                {c === "wechat" ? "微信支付" : "支付宝"}
              </Tag>
            ),
          },
          {
            title: "退款金额",
            dataIndex: "amount",
            render: (v) => (
              <Typography.Text strong type="danger">
                ¥{v}
              </Typography.Text>
            ),
          },
          {
            title: "执行状态",
            dataIndex: "status",
            render: (s) => {
              const map: Record<string, { color: string; label: string }> = {
                succeeded: { color: "success", label: "退款成功" },
                processing: { color: "processing", label: "处理中" },
                abnormal: { color: "error", label: "退款异常" },
                closed: { color: "default", label: "已关闭" },
                created: { color: "warning", label: "已创建" },
              };
              const item = map[String(s ?? "")] ?? { color: "default", label: String(s ?? "") };
              return <Tag color={item.color}>{item.label}</Tag>;
            },
          },
          { title: "渠道流水号", dataIndex: "channel_refund_id", ellipsis: true, render: (v) => v || "-" },
          { title: "关联售后单", dataIndex: "refund_request_id", ellipsis: true, render: (v) => v || <Tag>无 (异常退款)</Tag> },
          { title: "资金确认时间", dataIndex: "confirmed_at", render: (v) => v || "-" },
          { title: "执行发起时间", dataIndex: "created_at" },
        ]}
      />
    </PageFrame>
  );
}
