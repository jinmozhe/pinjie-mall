import { PageFrame } from "@/components/PageFrame";
import { CommerceReview } from "@/components/CommerceReview";

export function RefundsPage() {
  return <PageFrame title="退款审核" description="审核退款申请，渠道执行与最终结果独立确认。"><CommerceReview resource="refunds" /></PageFrame>;
}

export default RefundsPage;
