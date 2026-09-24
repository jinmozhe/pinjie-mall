import { useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined, EditOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import type {
  MemberLevelRead,
  MemberLevelCreate,
  MemberLevelUpdate,
  MemberLevelConditionRead,
  MemberLevelConditionCreate,
  MemberLevelConditionUpdate,
} from "@pinjie/api-client";
import { PageFrame, QueryState } from "@/components/PageFrame";
import { useLockedMutation } from "@/lib/useLockedMutation";
import { canAccess, useCurrentAdmin } from "@/lib/auth-context";
import { commerceApi } from "@/lib/api/commerce";

export default function MemberLevelsPage() {
  const admin = useCurrentAdmin();
  const queryClient = useQueryClient();
  const canLevelsRead = canAccess(admin, "member-levels:read");
  const canLevelsCreate = canAccess(admin, "member-levels:create");
  const canLevelsUpdate = canAccess(admin, "member-levels:update");
  const canCondsRead = canAccess(admin, "member-level-conditions:read");
  const canCondsCreate = canAccess(admin, "member-level-conditions:create");
  const canCondsUpdate = canAccess(admin, "member-level-conditions:update");

  const [levelPage, setLevelPage] = useState(1);
  const [condPage, setCondPage] = useState(1);

  // Level Modal state
  const [levelModalOpen, setLevelModalOpen] = useState(false);
  const [editingLevel, setEditingLevel] = useState<MemberLevelRead | null>(null);
  const [levelForm] = Form.useForm();

  // Condition Modal state
  const [condModalOpen, setCondModalOpen] = useState(false);
  const [editingCond, setEditingCond] = useState<MemberLevelConditionRead | null>(null);
  const [condForm] = Form.useForm();
  const metric = Form.useWatch("metric", condForm);
  const levelOptions = useQuery({ queryKey: ["admin-member-levels-all"], queryFn: commerceApi.memberLevelOptions, enabled: canLevelsRead && condModalOpen });

  // Queries
  const { data: levelsData, isLoading: levelsLoading, error: levelsError, refetch: reloadLevels } = useQuery({
    queryKey: ["admin-member-levels", levelPage],
    queryFn: () => commerceApi.memberLevels(levelPage),
    enabled: canLevelsRead,
  });

  const { data: conditionsData, isLoading: condsLoading, error: condsError, refetch: reloadConds } = useQuery({
    queryKey: ["admin-member-level-conditions", condPage],
    queryFn: () => commerceApi.memberLevelConditions(condPage),
    enabled: canCondsRead,
  });

  // Mutations
  const saveLevelMutation = useLockedMutation({
    mutationFn: async (values: MemberLevelCreate) => {
      if (editingLevel) {
        const updatePayload: MemberLevelUpdate = {
          code: values.code,
          name: values.name,
          level_rank: values.level_rank,
          discount_factor: String(values.discount_factor),
          sort_order: values.sort_order,
          is_active: values.is_active,
          revision: editingLevel.revision,
        };
        return commerceApi.updateMemberLevel(editingLevel.id, updatePayload);
      }
      return commerceApi.createMemberLevel(values);
    },
    onSuccess: () => {
      message.success(editingLevel ? "会员等级更新成功" : "会员等级创建成功");
      setLevelModalOpen(false);
      setEditingLevel(null);
      levelForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["admin-member-levels"] });
      queryClient.invalidateQueries({ queryKey: ["admin-member-levels-all"] });
    },
    onError: (err: Error) => {
      message.error(err.message || "保存等级失败");
    },
  });

  const saveCondMutation = useLockedMutation({
    mutationFn: async (values: MemberLevelConditionCreate) => {
      const payload: MemberLevelConditionCreate = {
        ...values,
        amount_threshold: values.metric === "consumption" && values.amount_threshold != null ? String(values.amount_threshold) : null,
        count_threshold: values.metric !== "consumption" ? values.count_threshold : null,
      };
      if (editingCond) {
        const updatePayload: MemberLevelConditionUpdate = {
          ...payload,
          revision: editingCond.revision,
        };
        return commerceApi.updateMemberLevelCondition(editingCond.id, updatePayload);
      }
      return commerceApi.createMemberLevelCondition(payload);
    },
    onSuccess: () => {
      message.success(editingCond ? "资格条件更新成功" : "资格条件创建成功");
      setCondModalOpen(false);
      setEditingCond(null);
      condForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["admin-member-level-conditions"] });
    },
    onError: (err: Error) => {
      message.error(err.message || "保存资格条件失败");
    },
  });

  const levelColumns: ColumnsType<MemberLevelRead> = [
    { title: "等级代码", dataIndex: "code", key: "code" },
    { title: "等级名称", dataIndex: "name", key: "name", render: (text) => <Typography.Text strong>{text}</Typography.Text> },
    { title: "层级排序 (Rank)", dataIndex: "level_rank", key: "level_rank", sorter: (a, b) => a.level_rank - b.level_rank },
    {
      title: "默认折扣率",
      dataIndex: "discount_factor",
      key: "discount_factor",
      render: (v) => (v ? `${(Number(v) * 10).toFixed(1)} 折 (${v})` : "无额外折扣"),
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      render: (active) => <Tag color={active ? "success" : "default"}>{active ? "启用中" : "已停用"}</Tag>,
    },
    { title: "版本", dataIndex: "revision", key: "revision", width: 80 },
    { title: "创建时间", dataIndex: "created_at", key: "created_at" },
    {
      title: "操作",
      key: "actions",
      width: "1%",
      render: (_, row) =>
        canLevelsUpdate ? (
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingLevel(row);
              levelForm.setFieldsValue({
                code: row.code,
                name: row.name,
                level_rank: row.level_rank,
                discount_factor: row.discount_factor,
                sort_order: row.sort_order,
                is_active: row.is_active ?? true,
              });
              setLevelModalOpen(true);
            }}
          >
            编辑
          </Button>
        ) : null,
    },
  ];

  const condColumns: ColumnsType<MemberLevelConditionRead> = [
    {
      title: "目标等级 ID",
      dataIndex: "level_id",
      key: "level_id",
      ellipsis: true,
      render: (id) => {
        const found = levelsData?.items?.find((l) => l.id === id);
        return found ? `${found.name} (${id.slice(0, 8)})` : id;
      },
    },
    {
      title: "达标指标",
      dataIndex: "metric",
      key: "metric",
      render: (m) => {
        const map: Record<string, string> = {
          consumption: "消费金额",
          invite_count: "直邀人数",
          points: "积分门槛",
        };
        return <Tag color="blue">{map[m] ?? m}</Tag>;
      },
    },
    {
      title: "统计模式",
      dataIndex: "aggregation",
      key: "aggregation",
      render: (a) => (a === "single" ? "单笔达标" : "累计达标"),
    },
    {
      title: "门槛要求",
      key: "threshold",
      render: (_, r) => (
        <span>
          {r.amount_threshold ? `金额: ¥${r.amount_threshold} ` : ""}
          {r.count_threshold !== null && r.count_threshold !== undefined ? `数量: ${r.count_threshold} ` : ""}
        </span>
      ),
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      render: (active) => <Tag color={active ? "success" : "default"}>{active ? "有效" : "失效"}</Tag>,
    },
    { title: "生效时间", dataIndex: "effective_at", key: "effective_at" },
    {
      title: "操作",
      key: "actions",
      width: "1%",
      render: (_, row) =>
        canCondsUpdate ? (
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingCond(row);
              condForm.setFieldsValue({
                level_id: row.level_id,
                metric: row.metric,
                aggregation: row.aggregation,
                amount_threshold: row.amount_threshold,
                count_threshold: row.count_threshold ?? undefined,
                effective_at: row.effective_at,
                is_active: row.is_active ?? true,
              });
              setCondModalOpen(true);
            }}
          >
            编辑
          </Button>
        ) : null,
    },
  ];

  return (
    <PageFrame
      title="会员等级"
      description="维护商城会员等级阶梯、等级默认折扣系数以及自动晋升达标资格规则。"
    >
      <Tabs
        defaultActiveKey="levels"
        items={[
          {
            key: "levels",
            label: "会员等级体系",
            children: (
              <div>
                {canLevelsCreate && (
                  <div style={{ marginBottom: 16 }}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        setEditingLevel(null);
                        levelForm.resetFields();
                        levelForm.setFieldsValue({ is_active: true, level_rank: 1, discount_factor: "1" });
                        setLevelModalOpen(true);
                      }}
                    >
                      新建会员等级
                    </Button>
                  </div>
                )}
                {!canLevelsRead ? (
                  <Alert type="warning" title="无权查看会员等级列表" />
                ) : levelsError ? (
                  <QueryState loading={false} error={levelsError.message} onRetry={() => void reloadLevels()} />
                ) : (
                  <Table<MemberLevelRead>
                    rowKey="id"
                    loading={levelsLoading}
                    dataSource={levelsData?.items ?? []}
                    columns={levelColumns.map((col) => ({
                      ...col,
                      onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
                      onCell: () => ({ style: { whiteSpace: "nowrap" } }),
                    }))}
                    scroll={{ x: "max-content" }}
                    pagination={{
                      current: levelPage,
                      pageSize: 20,
                      showSizeChanger: false,
                      total: levelsData?.total ?? 0,
                      onChange: (p) => setLevelPage(p),
                      showTotal: (total) => `共 ${total} 个等级`,
                    }}
                  />
                )}
              </div>
            ),
          },
          {
            key: "conditions",
            label: "晋升资格条件",
            children: (
              <div>
                {canCondsCreate && (
                  <div style={{ marginBottom: 16 }}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        setEditingCond(null);
                        condForm.resetFields();
                        condForm.setFieldsValue({
                          is_active: true,
                          metric: "consumption",
                          aggregation: "cumulative",
                          effective_at: new Date().toISOString(),
                        });
                        setCondModalOpen(true);
                      }}
                    >
                      新建资格条件
                    </Button>
                  </div>
                )}
                {!canCondsRead ? (
                  <Alert type="warning" title="无权查看会员资格条件列表" />
                ) : condsError ? (
                  <QueryState loading={false} error={condsError.message} onRetry={() => void reloadConds()} />
                ) : (
                  <Table<MemberLevelConditionRead>
                    rowKey="id"
                    loading={condsLoading}
                    dataSource={conditionsData?.items ?? []}
                    columns={condColumns.map((col) => ({
                      ...col,
                      onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
                      onCell: () => ({ style: { whiteSpace: "nowrap" } }),
                    }))}
                    scroll={{ x: "max-content" }}
                    pagination={{
                      current: condPage,
                      pageSize: 20,
                      showSizeChanger: false,
                      total: conditionsData?.total ?? 0,
                      onChange: (p) => setCondPage(p),
                      showTotal: (total) => `共 ${total} 条资格条件`,
                    }}
                  />
                )}
              </div>
            ),
          },
        ]}
      />

      {/* Level Modal */}
      <Modal
        title={editingLevel ? "编辑会员等级" : "新建会员等级"}
        open={levelModalOpen}
        maskClosable={false} closable={!saveLevelMutation.isPending} keyboard={!saveLevelMutation.isPending}
        cancelButtonProps={{ disabled: saveLevelMutation.isPending }}
        onCancel={() => {
          if (saveLevelMutation.isPending) return;
          setLevelModalOpen(false);
          setEditingLevel(null);
        }}
        onOk={() => levelForm.submit()}
        confirmLoading={saveLevelMutation.isPending}
      >
        <Form form={levelForm} layout="vertical" disabled={saveLevelMutation.isPending} onFinish={saveLevelMutation.mutate}>
          <Form.Item
            name="code"
            label="等级代码 (Code)"
            rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/, max: 32, message: "使用小写字母开头的字母、数字或下划线，最长 32 位" }]}
          >
            <Input maxLength={32} disabled={Boolean(editingLevel)} placeholder="例如：vip1" />
          </Form.Item>
          <Form.Item name="name" label="等级名称" rules={[{ required: true, message: "请输入等级名称" }]}>
            <Input placeholder="例如：黄金会员" />
          </Form.Item>
          <Form.Item
            name="level_rank"
            label="等级位次 (Rank)"
            tooltip="数字越大代表等级越高"
            rules={[{ required: true, message: "请输入等级位次" }]}
          >
            <InputNumber min={1} max={100} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="discount_factor"
            label="默认折扣系数"
            tooltip="例如 0.95 代表 9.5 折；1 代表不打折"
            rules={[{ required: true, message: "请输入默认折扣系数" }]}
          >
            <InputNumber stringMode min="0" max="1" precision={6} step="0.01" style={{ width: "100%" }} placeholder="0.95" />
          </Form.Item>
          <Form.Item name="sort_order" label="展示顺序">
            <InputNumber min={0} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="is_active" label="是否启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Condition Modal */}
      <Modal
        title={editingCond ? "编辑资格条件" : "新建晋升资格条件"}
        open={condModalOpen}
        maskClosable={false} closable={!saveCondMutation.isPending} keyboard={!saveCondMutation.isPending}
        cancelButtonProps={{ disabled: saveCondMutation.isPending }}
        onCancel={() => {
          if (saveCondMutation.isPending) return;
          setCondModalOpen(false);
          setEditingCond(null);
        }}
        onOk={() => condForm.submit()}
        confirmLoading={saveCondMutation.isPending}
      >
        <QueryState loading={levelOptions.isLoading} error={levelOptions.error?.message} onRetry={() => void levelOptions.refetch()} />
        <Form form={condForm} layout="vertical" disabled={saveCondMutation.isPending} onFinish={saveCondMutation.mutate}>
          <Form.Item name="level_id" label="目标晋升等级" rules={[{ required: true, message: "请选择目标等级" }]}>
            {!canLevelsRead ? <Input placeholder="输入会员等级 UUID" /> : <Select
              placeholder="选择会员等级"
              options={
                levelOptions.data?.map((l: MemberLevelRead) => ({
                  value: l.id,
                  label: `${l.name} (${l.code})`,
                })) ?? []
              }
            />}
          </Form.Item>
          <Form.Item name="metric" label="指标类型" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "consumption", label: "消费金额 (消费总额或单笔订单)" },
                { value: "invite_count", label: "直邀人数" },
                { value: "points", label: "积分积累" },
              ]}
            />
          </Form.Item>
          <Form.Item name="aggregation" label="聚合方式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "cumulative", label: "累计达标 (cumulative)" },
                { value: "single", label: "单笔达标 (single)" },
              ]}
            />
          </Form.Item>
          {metric === "consumption" ? <Form.Item name="amount_threshold" label="金额门槛 (元)" rules={[{ required: true }]}>
            <InputNumber stringMode min="0" precision={2} step="0.01" style={{ width: "100%" }} placeholder="如 1000.00" />
          </Form.Item> : <Form.Item name="count_threshold" label="次数/人数/积分门槛" rules={[{ required: true }]}>
            <InputNumber min={0} precision={0} step={1} style={{ width: "100%" }} placeholder="如 10" />
          </Form.Item>}
          <Form.Item name="effective_at" label="生效时间 (ISO 8601)" rules={[{ required: true }]}>
            <Input placeholder="例如：2026-01-01T00:00:00Z" />
          </Form.Item>
          <Form.Item name="is_active" label="是否启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </PageFrame>
  );
}
