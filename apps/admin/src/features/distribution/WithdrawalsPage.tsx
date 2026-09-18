import { PageFrame } from "@/components/PageFrame";
import { CommerceReview } from "@/components/CommerceReview";

export function WithdrawalsPage() {
  return <PageFrame title="提现审核" description="查询全部提现状态并审核待审申请，审核通过不代表渠道已打款。"><CommerceReview resource="withdrawals" /></PageFrame>;
}

export default WithdrawalsPage;
