import { Tag, Typography } from "antd";
import type { CommissionRead } from "@pinjie/api-client";
import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function CommissionsPage() {
  return (
    <PageFrame
      title="佣金记录"
      description="查询平台多级分佣冻结、结算、退款追回与欠款来源依据。历史计提金额与受益归属保持不可变事实与完全可审计性。"
    >
      <CommerceList<CommissionRead>
        resource="commissions"
        title="佣金"
        rowKey="id"
        load={commerceApi.commissions}
        fields={[
          { name: "record_id", label: "佣金记录号" },
          { name: "order_id", label: "关联订单号" },
          { name: "user_id", label: "受益会员用户号" },
          {
            name: "status",
            label: "佣金状态",
            options: [
              { label: "冻结冷静期 (frozen)", value: "frozen" },
              { label: "已结算 (settled)", value: "settled" },
              { label: "已追回 (recovered)", value: "recovered" },
            ],
          },
        ]}
        columns={[
          { title: "佣金流水号", dataIndex: "id", ellipsis: true },
          { title: "关联订单号", dataIndex: "order_id", ellipsis: true },
          { title: "下单付款会员", dataIndex: "source_user_id", ellipsis: true },
          { title: "受益会员", dataIndex: "beneficiary_user_id", ellipsis: true },
          {
            title: "分销层级",
            dataIndex: "level",
            render: (lvl) => <Tag color={lvl === 1 ? "cyan" : "purple"}>{lvl} 级上线</Tag>,
          },
          {
            title: "计提基数",
            dataIndex: "base_amount",
            render: (v) => `¥${v}`,
          },
          {
            title: "提成比例",
            dataIndex: "rate",
            render: (v) => (v ? `${(Number(v) * 100).toFixed(1)}%` : "-"),
          },
          {
            title: "应发佣金",
            dataIndex: "amount",
            render: (v) => (
              <Typography.Text strong style={{ color: "#389e0d" }}>
                ¥{v}
              </Typography.Text>
            ),
          },
          {
            title: "已追回额",
            dataIndex: "recovered_amount",
            render: (v) => (v && Number(v) > 0 ? <Typography.Text type="danger">¥{v}</Typography.Text> : "-"),
          },
          {
            title: "状态",
            dataIndex: "status",
            render: (s) => {
              const statusKey = String(s ?? "");
              const map: Record<string, { color: string; label: string }> = {
                frozen: { color: "processing", label: "冷静冻结中" },
                settled: { color: "success", label: "已结算入钱包" },
                recovered: { color: "warning", label: "售后已追回" },
              };
              const item = map[statusKey] ?? { color: "default", label: statusKey };
              return <Tag color={item.color}>{item.label}</Tag>;
            },
          },
          { title: "最早结算时间", dataIndex: "settle_after", render: (v) => v || "-" },
          { title: "实际结算时间", dataIndex: "settled_at", render: (v) => v || "-" },
          { title: "追回时间", dataIndex: "recovered_at", render: (v) => v || "-" },
        ]}
      />
    </PageFrame>
  );
}
