import { useState } from "react";
import { Drawer, Button, Space, Table, Tag, Typography } from "antd";
import { HistoryOutlined, TrophyOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import type {
  MemberProfileRead,
  MembershipQualificationEventRead,
  MemberLevelEventRead,
} from "@pinjie/api-client";
import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function MembersPage() {
  const [selectedUserForQualification, setSelectedUserForQualification] = useState<string | null>(null);
  const [selectedUserForLevels, setSelectedUserForLevels] = useState<string | null>(null);
  const [qualPage, setQualPage] = useState(1);
  const [levelPage, setLevelPage] = useState(1);

  const { data: qualData, isLoading: qualLoading } = useQuery({
    queryKey: ["qualification-events", selectedUserForQualification, qualPage],
    queryFn: () => commerceApi.qualificationEvents(selectedUserForQualification!, qualPage),
    enabled: Boolean(selectedUserForQualification),
  });

  const { data: levelData, isLoading: levelLoading } = useQuery({
    queryKey: ["level-events", selectedUserForLevels, levelPage],
    queryFn: () => commerceApi.levelEvents(selectedUserForLevels!, levelPage),
    enabled: Boolean(selectedUserForLevels),
  });

  const qualColumns: ColumnsType<MembershipQualificationEventRead> = [
    {
      title: "指标类型",
      dataIndex: "metric",
      key: "metric",
      render: (m: string) => {
        const map: Record<string, { color: string; label: string }> = {
          consumption: { color: "blue", label: "消费金额" },
          invite_count: { color: "purple", label: "邀请人数" },
          points: { color: "orange", label: "积分" },
        };
        const item = map[m] ?? { color: "default", label: m };
        return <Tag color={item.color}>{item.label}</Tag>;
      },
    },
    {
      title: "变动额/次数",
      key: "delta",
      render: (_, r) => (
        <span>
          {r.amount_delta ? `¥${r.amount_delta} ` : ""}
          {r.count_delta !== null && r.count_delta !== undefined ? `${r.count_delta} 次` : ""}
        </span>
      ),
    },
    { title: "来源类型", dataIndex: "source_type", key: "source_type" },
    { title: "来源/订单号", dataIndex: "order_id", key: "order_id", ellipsis: true, render: (v, r) => v ?? r.source_id },
    { title: "记录时间", dataIndex: "created_at", key: "created_at" },
  ];

  const levelColumns: ColumnsType<MemberLevelEventRead> = [
    {
      title: "原等级",
      dataIndex: "from_level_id",
      key: "from_level_id",
      render: (v) => v || "初始默认",
    },
    {
      title: "变更为",
      dataIndex: "to_level_id",
      key: "to_level_id",
      render: (v) => <Tag color="gold">{v || "普通"}</Tag>,
    },
    { title: "触发类型", dataIndex: "trigger_type", key: "trigger_type" },
    { title: "操作人", dataIndex: "operator_id", key: "operator_id", ellipsis: true, render: (v) => v || "-" },
    { title: "更新时间", dataIndex: "created_at", key: "created_at" },
  ];

  return (
    <PageFrame
      title="会员档案"
      description="查询会员档案和首次绑定的直接推荐人。按推荐人筛选可逐层查看，并可穿透审计会员资格贡献与等级升降历史。"
    >
      <CommerceList<MemberProfileRead>
        resource="members"
        title="会员"
        rowKey="user_id"
        load={commerceApi.members}
        fields={[
          { name: "user_id", label: "会员用户号" },
          { name: "inviter_id", label: "直接推荐人" },
        ]}
        columns={[
          { title: "会员用户号", dataIndex: "user_id", ellipsis: true },
          { title: "邀请码", dataIndex: "invitation_code" },
          {
            title: "等级",
            render: (_, row) => (
              <Tag color="cyan">{row.level_id ?? "普通会员"}</Tag>
            ),
          },
          { title: "直接推荐人", dataIndex: "inviter_id", ellipsis: true, render: (v) => v || "-" },
          { title: "绑定时间", dataIndex: "bound_at", render: (v) => v || "-" },
          { title: "开通时间", dataIndex: "created_at" },
          {
            title: "资格与升降级历史",
            key: "actions",
            width: "1%",
            render: (_, row) => (
              <Space size="small">
                <Button
                  size="small"
                  icon={<TrophyOutlined />}
                  onClick={() => {
                    setSelectedUserForQualification(row.user_id);
                    setQualPage(1);
                  }}
                >
                  资格贡献
                </Button>
                <Button
                  size="small"
                  icon={<HistoryOutlined />}
                  onClick={() => {
                    setSelectedUserForLevels(row.user_id);
                    setLevelPage(1);
                  }}
                >
                  等级历史
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        title={<Typography.Text strong>会员资格贡献流水 - {selectedUserForQualification}</Typography.Text>}
        open={Boolean(selectedUserForQualification)}
        onClose={() => setSelectedUserForQualification(null)}
        size={720}
      >
        <Table<MembershipQualificationEventRead>
          rowKey="id"
          loading={qualLoading}
          dataSource={qualData?.items ?? []}
          columns={qualColumns.map((col) => ({
            ...col,
            onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
            onCell: () => ({ style: { whiteSpace: "nowrap" } }),
          }))}
          scroll={{ x: "max-content" }}
          pagination={{
            current: qualPage,
            pageSize: 20,
            total: qualData?.total ?? 0,
            onChange: (p) => setQualPage(p),
            showTotal: (total) => `共 ${total} 条资格贡献`,
          }}
        />
      </Drawer>

      <Drawer
        title={<Typography.Text strong>会员等级变更记录 - {selectedUserForLevels}</Typography.Text>}
        open={Boolean(selectedUserForLevels)}
        onClose={() => setSelectedUserForLevels(null)}
        size={720}
      >
        <Table<MemberLevelEventRead>
          rowKey="id"
          loading={levelLoading}
          dataSource={levelData?.items ?? []}
          columns={levelColumns.map((col) => ({
            ...col,
            onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
            onCell: () => ({ style: { whiteSpace: "nowrap" } }),
          }))}
          scroll={{ x: "max-content" }}
          pagination={{
            current: levelPage,
            pageSize: 20,
            total: levelData?.total ?? 0,
            onChange: (p) => setLevelPage(p),
            showTotal: (total) => `共 ${total} 条等级变更`,
          }}
        />
      </Drawer>
    </PageFrame>
  );
}
