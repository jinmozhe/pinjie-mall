import { PageFrame } from "@/components/PageFrame";
import { CommerceList } from "@/components/CommerceList";
import { commerceApi } from "@/lib/api/commerce";

export default function PaymentsPage() {
  return <PageFrame title="支付记录" description="只读支付意图与渠道结果；结果未知需等待可信渠道核验。">
    <CommerceList resource="payments" title="支付记录" load={commerceApi.payments} fields={[
      { name: "record_id", label: "支付记录号" }, { name: "order_id", label: "订单号" }, { name: "user_id", label: "用户" },
      { name: "channel", label: "渠道", options: [{ label: "微信", value: "wechat" }, { label: "支付宝", value: "alipay" }] },
      { name: "status", label: "状态", options: [{ label: "已创建", value: "created" }, { label: "渠道未接入", value: "unavailable" }, { label: "处理中", value: "pending" }, { label: "成功", value: "succeeded" }, { label: "已关闭", value: "closed" }, { label: "结果未知", value: "unknown" }] },
    ]} columns={[
      { title: "支付记录号", dataIndex: "id", ellipsis: true }, { title: "订单号", dataIndex: "order_id", ellipsis: true },
      { title: "渠道", dataIndex: "channel" }, { title: "商户支付号", dataIndex: "merchant_reference", ellipsis: true },
      { title: "状态", dataIndex: "status" }, { title: "金额", dataIndex: "amount" }, { title: "币种", dataIndex: "currency" },
      { title: "不可用原因", dataIndex: "unavailable_reason", ellipsis: true }, { title: "创建时间", dataIndex: "created_at" },
    ]} />
  </PageFrame>;
}
