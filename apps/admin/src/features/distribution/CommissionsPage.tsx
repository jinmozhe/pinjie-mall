import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function CommissionsPage() {
  return <PageFrame title="佣金记录" description="查询两级佣金冻结、结算及退款追回；历史金额与归属保持可追溯。">
    <CommerceList resource="commissions" title="佣金" load={commerceApi.commissions} fields={[
      { name: "record_id", label: "佣金记录号" }, { name: "order_id", label: "订单号" }, { name: "user_id", label: "受益会员" },
      { name: "status", label: "状态", options: [{ label: "冻结", value: "frozen" }, { label: "已结算", value: "settled" }, { label: "已追回", value: "recovered" }] },
    ]} columns={[
      { title: "佣金记录号", dataIndex: "id", ellipsis: true }, { title: "订单号", dataIndex: "order_id", ellipsis: true },
      { title: "付款用户", dataIndex: "source_user_id", ellipsis: true }, { title: "受益会员", dataIndex: "beneficiary_user_id", ellipsis: true },
      { title: "级数", dataIndex: "level" }, { title: "计佣基数", dataIndex: "base_amount" }, { title: "比例", dataIndex: "rate" },
      { title: "佣金", dataIndex: "amount" }, { title: "已追回", dataIndex: "recovered_amount" }, { title: "状态", dataIndex: "status" },
      { title: "可结算时间", dataIndex: "settle_after" }, { title: "结算时间", dataIndex: "settled_at" },
    ]} />
  </PageFrame>;
}
