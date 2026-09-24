import { useState } from "react";
import { Button, Tag, Typography } from "antd";
import { ApartmentOutlined } from "@ant-design/icons";
import type { MemberProfileRead } from "@pinjie/api-client";
import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function ReferralNetworkPage() {
  const [currentInviterFilter, setCurrentInviterFilter] = useState<string | undefined>(undefined);

  return (
    <PageFrame
      title="推荐关系网络"
      description="查询平台会员的直接推荐人与推荐拓扑。支持按直接推荐人进行逐层下钻分析，核对真实层级，不提供后台关系改绑。"
    >
      {currentInviterFilter && (
        <div style={{ marginBottom: 16, padding: "8px 16px", background: "#f5f5f5", borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span>
            当前下钻推荐人：<Typography.Text copyable strong>{currentInviterFilter}</Typography.Text>
          </span>
          <Button size="small" onClick={() => setCurrentInviterFilter(undefined)}>
            重置回全部
          </Button>
        </div>
      )}

      <CommerceList<MemberProfileRead>
        key={currentInviterFilter ?? "all"}
        resource="members"
        title="推荐关系"
        rowKey="user_id"
        load={commerceApi.members}
        fixedFilters={currentInviterFilter ? { inviter_id: currentInviterFilter } : {}}
        fields={[
          { name: "user_id", label: "会员用户号" },
          ...(!currentInviterFilter ? [{ name: "inviter_id" as const, label: "直接推荐人用户号" }] : []),
        ]}
        columns={[
          { title: "会员用户号", dataIndex: "user_id", ellipsis: true },
          { title: "邀请码", dataIndex: "invitation_code" },
          {
            title: "当前等级",
            dataIndex: "level_id",
            render: (v) => <Tag color="gold">{v ?? "普通会员"}</Tag>,
          },
          {
            title: "直接推荐人 (上级)",
            dataIndex: "inviter_id",
            ellipsis: true,
            render: (v) => v || <Tag>无 (首层)</Tag>,
          },
          { title: "绑定时间", dataIndex: "bound_at", render: (v) => v || "-" },
          { title: "开通时间", dataIndex: "created_at" },
          {
            title: "拓扑下钻",
            key: "network_drill",
            width: "1%",
            render: (_, row) => (
              <Button
                size="small"
                icon={<ApartmentOutlined />}
                onClick={() => setCurrentInviterFilter(row.user_id)}
              >
                查看其下线团队
              </Button>
            ),
          },
        ]}
      />
    </PageFrame>
  );
}
