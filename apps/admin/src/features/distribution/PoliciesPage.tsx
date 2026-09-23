import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  CheckCircleOutlined,
  SettingOutlined,
  UnorderedListOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import type {
  CommissionPolicyRead,
  CommissionPolicyCreate,
  CommissionPolicyUpdate,
  CommissionAmountRuleRead,
  CommissionAmountRuleCreate,
  CommissionDistributionRuleRead,
  CommissionDistributionRuleCreate,
} from "@pinjie/api-client";
import { PageFrame } from "@/components/PageFrame";
import { canAccess, useCurrentAdmin } from "@/lib/auth-context";
import { commerceApi } from "@/lib/api/commerce";

export default function PoliciesPage() {
  const admin = useCurrentAdmin();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);

  const canControlRead = canAccess(admin, "settings:commission-control:read");
  const canControlUpdate = canAccess(admin, "settings:commission-control:update");
  const canPoliciesRead = canAccess(admin, "commission-policies:read");
  const canPoliciesCreate = canAccess(admin, "commission-policies:create");
  const canPoliciesUpdate = canAccess(admin, "commission-policies:update");
  const canPoliciesPublish = canAccess(admin, "commission-policies:publish");

  // Policy Modal
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<CommissionPolicyRead | null>(null);
  const [policyForm] = Form.useForm();
  const defaultMode = Form.useWatch("default_mode", policyForm);

  // Detail Drawer for Rules & Matrix
  const [detailPolicy, setDetailPolicy] = useState<CommissionPolicyRead | null>(null);

  // Amount Rule Modal
  const [amountModalOpen, setAmountModalOpen] = useState(false);
  const [amountForm] = Form.useForm();

  // Distribution Rule Modal
  const [distModalOpen, setDistModalOpen] = useState(false);
  const [distForm] = Form.useForm();

  // Queries
  const { data: controlData, isLoading: controlLoading } = useQuery({
    queryKey: ["commission-control"],
    queryFn: () => commerceApi.commissionControl(),
    enabled: canControlRead,
  });

  const { data: policiesData, isLoading: policiesLoading } = useQuery({
    queryKey: ["commission-policies", page],
    queryFn: () => commerceApi.policies(page),
    enabled: canPoliciesRead,
  });

  const { data: amountRulesData, isLoading: amountRulesLoading } = useQuery({
    queryKey: ["amount-rules", detailPolicy?.id],
    queryFn: () => commerceApi.amountRules(detailPolicy!.id),
    enabled: Boolean(detailPolicy) && canPoliciesRead,
  });

  const { data: distRulesData, isLoading: distRulesLoading } = useQuery({
    queryKey: ["distribution-rules", detailPolicy?.id],
    queryFn: () => commerceApi.distributionRules(detailPolicy!.id),
    enabled: Boolean(detailPolicy) && canPoliciesRead,
  });

  // Global switch mutation
  const toggleControlMutation = useMutation({
    mutationFn: (newEnabled: boolean) => {
      if (!controlData) throw new Error("控制配置未加载");
      return commerceApi.updateCommissionControl({
        commissions_enabled: newEnabled,
        revision: controlData.revision,
        schema_version: 1,
      });
    },
    onSuccess: () => {
      message.success("全平台分佣总开关更新成功");
      queryClient.invalidateQueries({ queryKey: ["commission-control"] });
    },
    onError: (err: Error) => {
      message.error(err.message || "更新分佣总开关失败");
    },
  });

  // Policy CRUD mutations
  const savePolicyMutation = useMutation({
    mutationFn: (values: CommissionPolicyCreate) => {
      if (editingPolicy) {
        const updatePayload: CommissionPolicyUpdate = {
          name: values.name,
          default_mode: values.default_mode,
          default_percentage_rate: values.default_percentage_rate ? String(values.default_percentage_rate) : null,
          default_amount_per_unit: values.default_amount_per_unit ? String(values.default_amount_per_unit) : null,
          max_depth: values.max_depth,
          settle_delay_days: values.settle_delay_days,
          revision: editingPolicy.revision,
        };
        return commerceApi.updatePolicy(editingPolicy.id, updatePayload);
      }
      return commerceApi.createPolicy({
        ...values,
        default_percentage_rate: values.default_percentage_rate ? String(values.default_percentage_rate) : null,
        default_amount_per_unit: values.default_amount_per_unit ? String(values.default_amount_per_unit) : null,
      });
    },
    onSuccess: () => {
      message.success(editingPolicy ? "分佣政策草稿更新成功" : "分佣政策草稿创建成功");
      setPolicyModalOpen(false);
      setEditingPolicy(null);
      policyForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["commission-policies"] });
    },
    onError: (err: Error) => {
      message.error(err.message || "保存政策失败");
    },
  });

  const publishMutation = useMutation({
    mutationFn: (row: CommissionPolicyRead) =>
      commerceApi.publishPolicy(row.id, { revision: row.revision }),
    onSuccess: () => {
      message.success("分佣政策发布成功，已切换为全局生效政策");
      queryClient.invalidateQueries({ queryKey: ["commission-policies"] });
      if (detailPolicy) {
        queryClient.invalidateQueries({ queryKey: ["commission-policies", page] });
      }
    },
    onError: (err: Error) => {
      message.error(err.message || "发布政策失败");
    },
  });

  // Amount Rule Mutations
  const addAmountRuleMutation = useMutation({
    mutationFn: (values: CommissionAmountRuleCreate) =>
      commerceApi.addAmountRule(detailPolicy!.id, {
        ...values,
        amount_per_unit: values.amount_per_unit ? String(values.amount_per_unit) : null,
        percentage_rate: values.percentage_rate ? String(values.percentage_rate) : null,
      }),
    onSuccess: () => {
      message.success("来源规则添加成功");
      setAmountModalOpen(false);
      amountForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["amount-rules", detailPolicy?.id] });
    },
    onError: (err: Error) => {
      message.error(err.message || "添加来源规则失败");
    },
  });

  const deleteAmountRuleMutation = useMutation({
    mutationFn: (ruleId: string) => commerceApi.deleteAmountRule(detailPolicy!.id, ruleId),
    onSuccess: () => {
      message.success("来源规则删除成功");
      queryClient.invalidateQueries({ queryKey: ["amount-rules", detailPolicy?.id] });
    },
    onError: (err: Error) => {
      message.error(err.message || "删除来源规则失败");
    },
  });

  // Distribution Rule Mutations
  const addDistRuleMutation = useMutation({
    mutationFn: (values: CommissionDistributionRuleCreate) =>
      commerceApi.addDistributionRule(detailPolicy!.id, {
        ...values,
        rate: values.rate ? String(values.rate) : null,
        amount_per_unit: values.amount_per_unit ? String(values.amount_per_unit) : null,
      }),
    onSuccess: () => {
      message.success("分配矩阵规则添加成功");
      setDistModalOpen(false);
      distForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["distribution-rules", detailPolicy?.id] });
    },
    onError: (err: Error) => {
      message.error(err.message || "添加分配规则失败");
    },
  });

  const deleteDistRuleMutation = useMutation({
    mutationFn: (ruleId: string) => commerceApi.deleteDistributionRule(detailPolicy!.id, ruleId),
    onSuccess: () => {
      message.success("分配矩阵规则删除成功");
      queryClient.invalidateQueries({ queryKey: ["distribution-rules", detailPolicy?.id] });
    },
    onError: (err: Error) => {
      message.error(err.message || "删除分配规则失败");
    },
  });

  const columns: ColumnsType<CommissionPolicyRead> = [
    {
      title: "政策名称",
      dataIndex: "name",
      key: "name",
      render: (text) => <Typography.Text strong>{text}</Typography.Text>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s) => {
        const map: Record<string, { color: string; label: string }> = {
          draft: { color: "processing", label: "草稿编制中" },
          active: { color: "success", label: "生效中" },
          retired: { color: "default", label: "历史归档" },
        };
        const item = map[s] ?? { color: "default", label: s };
        return <Tag color={item.color}>{item.label}</Tag>;
      },
    },
    { title: "内容版本", dataIndex: "content_version", key: "content_version", render: (v) => `v${v}` },
    {
      title: "默认计算模式",
      dataIndex: "default_mode",
      key: "default_mode",
      render: (m) => {
        const map: Record<string, string> = {
          percentage: "比例计算 (percentage)",
          fixed_amount: "固定定额 (fixed_amount)",
          disabled: "不计提 (disabled)",
        };
        return map[m] ?? m ?? "-";
      },
    },
    {
      title: "默认比例/金额",
      key: "default_val",
      render: (_, r) => {
        if (r.default_percentage_rate) return `${(Number(r.default_percentage_rate) * 100).toFixed(1)}%`;
        if (r.default_amount_per_unit) return `¥${r.default_amount_per_unit}/件`;
        return "-";
      },
    },
    { title: "最大层级", dataIndex: "max_depth", key: "max_depth", render: (d) => `${d ?? 2} 级` },
    { title: "结算延迟", dataIndex: "settle_delay_days", key: "settle_delay_days", render: (d) => `${d ?? 7} 天` },
    { title: "生效时间", dataIndex: "activated_at", key: "activated_at", render: (v) => v || "未发布" },
    {
      title: "操作",
      key: "actions",
      width: "1%",
      render: (_, row) => (
        <Space size="small">
          <Button
            size="small"
            icon={<UnorderedListOutlined />}
            onClick={() => setDetailPolicy(row)}
          >
            规则与三级矩阵
          </Button>
          {row.status === "draft" && (
            <>
              {canPoliciesUpdate && (
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditingPolicy(row);
                    policyForm.setFieldsValue({
                      name: row.name,
                      default_mode: row.default_mode,
                      default_percentage_rate: row.default_percentage_rate ? Number(row.default_percentage_rate) : undefined,
                      default_amount_per_unit: row.default_amount_per_unit ? Number(row.default_amount_per_unit) : undefined,
                      max_depth: row.max_depth,
                      settle_delay_days: row.settle_delay_days,
                    });
                    setPolicyModalOpen(true);
                  }}
                >
                  配置
                </Button>
              )}
              {canPoliciesPublish && (
                <Popconfirm
                  title="确认发布此政策？"
                  description="发布后该政策将转为 active 并自动归档当前生效政策，且政策规则将冻结为只读事实。"
                  onConfirm={() => publishMutation.mutate(row)}
                >
                  <Button size="small" type="primary" icon={<CheckCircleOutlined />}>
                    发布政策
                  </Button>
                </Popconfirm>
              )}
            </>
          )}
        </Space>
      ),
    },
  ];

  const isDraft = detailPolicy?.status === "draft";
  const canEditDraft = isDraft && canPoliciesUpdate;

  return (
    <PageFrame
      title="分佣政策"
      description="管理商城多级分佣政策、全局开关、佣金来源规则及三级分配矩阵。已发布政策保持只读不可变。"
    >
      {/* Global switch card */}
      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <SettingOutlined />
            <span>全平台分佣总开关 (独立受控区域)</span>
          </Space>
        }
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <Typography.Text strong>分佣功能当前状态：</Typography.Text>
            <Tag color={controlData?.commissions_enabled ? "success" : "error"} style={{ marginLeft: 8 }}>
              {controlData?.commissions_enabled ? "全平台分佣正常开启" : "全平台分佣已全局关闭"}
            </Tag>
            <span style={{ marginLeft: 16, color: "#8c8c8c" }}>
              版本: v{controlData?.revision} | 最近更新: {controlData?.updated_at ?? "-"}
            </span>
          </div>
          {canControlUpdate ? (
            <Popconfirm
              title={`确认要${controlData?.commissions_enabled ? "关闭" : "开启"}全平台分佣吗？`}
              description="修改全平台分佣总开关立即对所有新下单生效，请谨慎操作。"
              onConfirm={() => toggleControlMutation.mutate(!controlData?.commissions_enabled)}
            >
              <Switch
                loading={controlLoading || toggleControlMutation.isPending}
                checked={controlData?.commissions_enabled}
              />
            </Popconfirm>
          ) : (
            <Switch
              disabled
              checked={controlData?.commissions_enabled}
            />
          )}
        </div>
      </Card>

      {/* Policy list */}
      {canPoliciesCreate && (
        <div style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingPolicy(null);
              policyForm.resetFields();
              policyForm.setFieldsValue({
                default_mode: "percentage",
                default_percentage_rate: 0.1,
                max_depth: 2,
                settle_delay_days: 7,
              });
              setPolicyModalOpen(true);
            }}
          >
            新建分佣政策草稿
          </Button>
        </div>
      )}

      {!canPoliciesRead ? (
        <Alert type="warning" title="无权查看分佣政策列表" />
      ) : (
        <Table<CommissionPolicyRead>
          rowKey="id"
          loading={policiesLoading}
          dataSource={policiesData?.items ?? []}
          columns={columns.map((col) => ({
            ...col,
            onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
            onCell: () => ({ style: { whiteSpace: "nowrap" } }),
          }))}
          scroll={{ x: "max-content" }}
          pagination={{
            current: page,
            pageSize: 20,
            total: policiesData?.total ?? 0,
            onChange: (p) => setPage(p),
            showTotal: (total) => `共 ${total} 条分佣政策`,
          }}
        />
      )}

      {/* Policy Modal */}
      <Modal
        title={editingPolicy ? "编辑分佣政策草稿" : "新建分佣政策草稿"}
        open={policyModalOpen}
        onCancel={() => {
          setPolicyModalOpen(false);
          setEditingPolicy(null);
        }}
        onOk={() => policyForm.submit()}
        confirmLoading={savePolicyMutation.isPending}
      >
        <Form form={policyForm} layout="vertical" onFinish={savePolicyMutation.mutate}>
          <Form.Item name="name" label="政策名称" rules={[{ required: true, message: "请输入政策名称" }]}>
            <Input placeholder="例如：2026年度标准多级分销政策" />
          </Form.Item>
          <Form.Item name="default_mode" label="默认计提模式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "percentage", label: "按订单商品实付比例计提 (percentage)" },
                { value: "fixed_amount", label: "按单品固定金额计提 (fixed_amount)" },
                { value: "disabled", label: "默认不提成 (disabled)" },
              ]}
            />
          </Form.Item>
          {defaultMode === "percentage" && (
            <Form.Item name="default_percentage_rate" label="默认提成比例" tooltip="例如 0.10 代表 10%">
              <InputNumber min={0.001} max={1.0} step={0.01} style={{ width: "100%" }} placeholder="0.10" />
            </Form.Item>
          )}
          {defaultMode === "fixed_amount" && (
            <Form.Item name="default_amount_per_unit" label="单件固定定额 (元)">
              <InputNumber min={0.01} step={0.01} style={{ width: "100%" }} placeholder="如 5.00" />
            </Form.Item>
          )}
          <Form.Item name="max_depth" label="最大分佣代数 (层级)" tooltip="依法合规严格限制三代以内">
            <InputNumber min={1} max={3} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="settle_delay_days" label="结算冻结延迟天数 (天)" tooltip="过售后冷静期后结算到分销钱包">
            <InputNumber min={0} max={90} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Rules & Matrix Drawer */}
      <Drawer
        title={
          <Typography.Text strong>
            政策详情与矩阵：{detailPolicy?.name} ({detailPolicy?.status})
          </Typography.Text>
        }
        open={Boolean(detailPolicy)}
        onClose={() => setDetailPolicy(null)}
        width={860}
      >
        {!isDraft && (
          <Alert
            message="只读不可变政策"
            description="当前政策处于 active 或 retired 状态，所有来源规则与分配矩阵已冻结，不开放修改。"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <Tabs
          defaultActiveKey="amount"
          items={[
            {
              key: "amount",
              label: "特定来源计提规则",
              children: (
                <div>
                  {canEditDraft && (
                    <div style={{ marginBottom: 16 }}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          amountForm.resetFields();
                          amountForm.setFieldsValue({
                            rule_mode: "percentage",
                            buyer_scope: "any",
                          });
                          setAmountModalOpen(true);
                        }}
                      >
                        新增来源规则
                      </Button>
                    </div>
                  )}
                  <Table<CommissionAmountRuleRead>
                    rowKey="id"
                    loading={amountRulesLoading}
                    dataSource={amountRulesData ?? []}
                    scroll={{ x: "max-content" }}
                    columns={([
                      { title: "范围模式", dataIndex: "buyer_scope", key: "buyer_scope" },
                      { title: "商品 ID", dataIndex: "product_id", key: "product_id", ellipsis: true, render: (v: string | null) => v || "全部商品" },
                      { title: "变体 SKU ID", dataIndex: "sku_id", key: "sku_id", ellipsis: true, render: (v: string | null) => v || "全部SKU" },
                      { title: "计提模式", dataIndex: "rule_mode", key: "rule_mode" },
                      {
                        title: "比例/定额",
                        key: "rate_val",
                        render: (_: unknown, r: CommissionAmountRuleRead) => {
                          if (r.percentage_rate) return `${(Number(r.percentage_rate) * 100).toFixed(1)}%`;
                          if (r.amount_per_unit) return `¥${r.amount_per_unit}/件`;
                          return "-";
                        },
                      },
                      ...(canEditDraft
                        ? [
                            {
                              title: "操作",
                              key: "actions",
                              width: "1%",
                              render: (_: unknown, r: CommissionAmountRuleRead) => (
                                <Popconfirm
                                  title="确认删除该规则？"
                                  onConfirm={() => deleteAmountRuleMutation.mutate(r.id)}
                                >
                                  <Button size="small" danger icon={<DeleteOutlined />}>
                                    删除
                                  </Button>
                                </Popconfirm>
                              ),
                            },
                          ]
                        : []),
                    ] as ColumnsType<CommissionAmountRuleRead>).map((col) => ({
                      ...col,
                      onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
                      onCell: () => ({ style: { whiteSpace: "nowrap" } }),
                    }))}
                    pagination={false}
                  />
                </div>
              ),
            },
            {
              key: "distribution",
              label: "三级分配矩阵",
              children: (
                <div>
                  {canEditDraft && (
                    <div style={{ marginBottom: 16 }}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          distForm.resetFields();
                          distForm.setFieldsValue({
                            ancestor_depth: 1,
                            allocation_mode: "percentage",
                          });
                          setDistModalOpen(true);
                        }}
                      >
                        新增矩阵分配规则
                      </Button>
                    </div>
                  )}
                  <Table<CommissionDistributionRuleRead>
                    rowKey="id"
                    loading={distRulesLoading}
                    dataSource={distRulesData ?? []}
                    scroll={{ x: "max-content" }}
                    columns={([
                      { title: "上线层级", dataIndex: "ancestor_depth", key: "ancestor_depth", render: (d: number) => `${d} 级上级 (深度)` },
                      { title: "购买人等级", dataIndex: "buyer_level_id", key: "buyer_level_id", ellipsis: true },
                      { title: "受益人等级", dataIndex: "beneficiary_level_id", key: "beneficiary_level_id", ellipsis: true },
                      { title: "分配方式", dataIndex: "allocation_mode", key: "allocation_mode" },
                      {
                        title: "分配比例/定额",
                        key: "alloc_val",
                        render: (_: unknown, r: CommissionDistributionRuleRead) => {
                          if (r.rate) return `${(Number(r.rate) * 100).toFixed(1)}%`;
                          if (r.amount_per_unit) return `¥${r.amount_per_unit}/件`;
                          return "-";
                        },
                      },
                      ...(canEditDraft
                        ? [
                            {
                              title: "操作",
                              key: "actions",
                              width: "1%",
                              render: (_: unknown, r: CommissionDistributionRuleRead) => (
                                <Popconfirm
                                  title="确认删除该分配规则？"
                                  onConfirm={() => deleteDistRuleMutation.mutate(r.id)}
                                >
                                  <Button size="small" danger icon={<DeleteOutlined />}>
                                    删除
                                  </Button>
                                </Popconfirm>
                              ),
                            },
                          ]
                        : []),
                    ] as ColumnsType<CommissionDistributionRuleRead>).map((col) => ({
                      ...col,
                      onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
                      onCell: () => ({ style: { whiteSpace: "nowrap" } }),
                    }))}
                    pagination={false}
                  />
                </div>
              ),
            },
          ]}
        />
      </Drawer>

      {/* Amount Rule Modal */}
      <Modal
        title="新增佣金来源规则"
        open={amountModalOpen}
        onCancel={() => setAmountModalOpen(false)}
        onOk={() => amountForm.submit()}
        confirmLoading={addAmountRuleMutation.isPending}
      >
        <Form form={amountForm} layout="vertical" onFinish={addAmountRuleMutation.mutate}>
          <Form.Item name="buyer_scope" label="买家范围" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "any", label: "任意买家" },
                { value: "level", label: "指定买家等级" },
              ]}
            />
          </Form.Item>
          <Form.Item name="product_id" label="指定商品 ID (可选)">
            <Input placeholder="商品 UUID，留空代表全商品" />
          </Form.Item>
          <Form.Item name="sku_id" label="指定变体 SKU ID (可选)">
            <Input placeholder="变体 SKU UUID" />
          </Form.Item>
          <Form.Item name="rule_mode" label="计提模式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "percentage", label: "按比例计提" },
                { value: "fixed_amount", label: "按定额计提" },
                { value: "disabled", label: "不计提佣金" },
              ]}
            />
          </Form.Item>
          <Form.Item name="percentage_rate" label="计提比例 (如 0.15)">
            <InputNumber min={0.001} max={1.0} step={0.01} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="amount_per_unit" label="单件定额 (元)">
            <InputNumber min={0.01} step={0.01} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Distribution Rule Modal */}
      <Modal
        title="新增三级分配矩阵规则"
        open={distModalOpen}
        onCancel={() => setDistModalOpen(false)}
        onOk={() => distForm.submit()}
        confirmLoading={addDistRuleMutation.isPending}
      >
        <Form form={distForm} layout="vertical" onFinish={addDistRuleMutation.mutate}>
          <Form.Item name="ancestor_depth" label="推荐人代数深度 (1~3)" rules={[{ required: true }]}>
            <InputNumber min={1} max={3} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="buyer_level_id" label="买家等级 ID" rules={[{ required: true }]}>
            <Input placeholder="输入买家等级 UUID" />
          </Form.Item>
          <Form.Item name="beneficiary_level_id" label="受益人等级 ID" rules={[{ required: true }]}>
            <Input placeholder="输入受益人等级 UUID" />
          </Form.Item>
          <Form.Item name="allocation_mode" label="分配模式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "percentage", label: "按总佣金比例分配" },
                { value: "fixed_amount", label: "固定定额" },
              ]}
            />
          </Form.Item>
          <Form.Item name="rate" label="分配比例 (如 0.60 代表占总佣金 60%)">
            <InputNumber min={0.001} max={1.0} step={0.01} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="amount_per_unit" label="单件分配定额 (元)">
            <InputNumber min={0.01} step={0.01} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </PageFrame>
  );
}
