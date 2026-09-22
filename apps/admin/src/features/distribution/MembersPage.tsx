import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function MembersPage() {
  return <PageFrame title="会员与推荐关系" description="查询会员档案和首次绑定的直接推荐人。按推荐人筛选可逐层查看，不提供关系重绑。">
    <CommerceList resource="members" title="会员" rowKey="user_id" load={commerceApi.members}
      fields={[{ name: "user_id", label: "会员用户号" }, { name: "inviter_id", label: "直接推荐人" }]}
      columns={[{ title: "会员用户号", dataIndex: "user_id", ellipsis: true }, { title: "邀请码", dataIndex: "invitation_code" },
        { title: "等级", render: (_, row) => row.level_id ?? "普通会员" },
        { title: "直接推荐人", dataIndex: "inviter_id", ellipsis: true }, { title: "绑定时间", dataIndex: "bound_at" }, { title: "开通时间", dataIndex: "created_at" }]} />
  </PageFrame>;
}
