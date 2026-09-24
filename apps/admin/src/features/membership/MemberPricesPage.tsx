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
  Tag,
  Typography,
  App,
} from "antd";
import { PlusOutlined, EditOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import type {
  MemberPriceRuleRead,
  MemberPriceRuleCreate,
  MemberPriceRuleUpdate,
  MemberLevelRead,
} from "@pinjie/api-client";
import { PageFrame, QueryState } from "@/components/PageFrame";
import { useLockedMutation } from "@/lib/useLockedMutation";
import { canAccess, useCurrentAdmin } from "@/lib/auth-context";
import { commerceApi } from "@/lib/api/commerce";

export default function MemberPricesPage() {
  const { message } = App.useApp();
  const admin = useCurrentAdmin();
  const queryClient = useQueryClient();
  const canPricesRead = canAccess(admin, "member-price-rules:read");
  const canPricesCreate = canAccess(admin, "member-price-rules:create");
  const canPricesUpdate = canAccess(admin, "member-price-rules:update");

  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<MemberPriceRuleRead | null>(null);
  const [form] = Form.useForm();
  const scopeType = Form.useWatch("scope_type", form);
  const priceMode = Form.useWatch("price_mode", form);

  const { data: levelsData, error: levelsError, refetch: reloadLevels } = useQuery({
    queryKey: ["admin-member-levels-all"],
    queryFn: commerceApi.memberLevelOptions,
    enabled: canAccess(admin, "member-levels:read"),
  });

  const { data: rulesData, isLoading, error: rulesError, refetch: reloadRules } = useQuery({
    queryKey: ["admin-member-price-rules", page],
    queryFn: () => commerceApi.memberPriceRules(page),
    enabled: canPricesRead,
  });

  const saveMutation = useLockedMutation({
    mutationFn: async (values: MemberPriceRuleCreate) => {
      if (values.scope_type === "category" && values.price_mode === "fixed") throw new Error("分类规则只支持折扣或排除会员价");
      const payload: MemberPriceRuleCreate = {
        ...values,
        sku_id: values.scope_type === "sku" ? values.sku_id : null,
        product_id: values.scope_type === "product" ? values.product_id : null,
        category_id: values.scope_type === "category" ? values.category_id : null,
        fixed_price: values.price_mode === "fixed" && values.fixed_price != null ? String(values.fixed_price) : null,
        discount_factor: values.price_mode === "discount" && values.discount_factor != null ? String(values.discount_factor) : null,
      };
      if (editingRule) {
        const updatePayload: MemberPriceRuleUpdate = {
          ...payload,
          revision: editingRule.revision,
        };
        return commerceApi.updateMemberPriceRule(editingRule.id, updatePayload);
      }
      return commerceApi.createMemberPriceRule(payload);
    },
    onSuccess: () => {
      message.success(editingRule ? "价格规则更新成功" : "价格规则创建成功");
      setModalOpen(false);
      setEditingRule(null);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["admin-member-price-rules"] });
    },
    onError: (err: Error) => {
      message.error(err.message || "保存价格规则失败");
    },
  });

  const columns: ColumnsType<MemberPriceRuleRead> = [
    {
      title: "会员等级",
      dataIndex: "member_level_id",
      key: "member_level_id",
      render: (levelId) => {
        const found = levelsData?.find((l: MemberLevelRead) => l.id === levelId);
        return found ? <Tag color="gold">{found.name}</Tag> : levelId;
      },
    },
    {
      title: "适用范围",
      dataIndex: "scope_type",
      key: "scope_type",
      render: (st) => {
        const map: Record<string, { color: string; label: string }> = {
          sku: { color: "blue", label: "SKU 变体" },
          product: { color: "cyan", label: "SPU 商品" },
          category: { color: "purple", label: "商品分类" },
        };
        const item = map[st] ?? { color: "default", label: st };
        return <Tag color={item.color}>{item.label}</Tag>;
      },
    },
    {
      title: "范围目标 ID",
      key: "target_id",
      ellipsis: true,
      render: (_, r) => r.sku_id || r.product_id || r.category_id || "-",
    },
    {
      title: "价格模式",
      dataIndex: "price_mode",
      key: "price_mode",
      render: (pm) => {
        const map: Record<string, string> = {
          fixed: "会员一口价",
          discount: "等级折扣率",
          exclude: "不参与会员优惠",
        };
        return <Typography.Text>{map[pm] ?? pm}</Typography.Text>;
      },
    },
    {
      title: "规则定价/折扣",
      key: "pricing",
      render: (_, r) => {
        if (r.price_mode === "fixed" && r.fixed_price) {
          return <Typography.Text strong type="danger">¥{r.fixed_price}</Typography.Text>;
        }
        if (r.price_mode === "discount" && r.discount_factor) {
          return <Typography.Text strong type="warning">{(Number(r.discount_factor) * 10).toFixed(1)} 折</Typography.Text>;
        }
        if (r.price_mode === "exclude") {
          return <Tag color="error">排除会员特价</Tag>;
        }
        return "-";
      },
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      render: (active) => <Tag color={active ? "success" : "default"}>{active ? "生效中" : "已停用"}</Tag>,
    },
    { title: "版本", dataIndex: "revision", key: "revision", width: 80 },
    { title: "更新时间", dataIndex: "updated_at", key: "updated_at" },
    {
      title: "操作",
      key: "actions",
      width: "1%",
      render: (_, row) =>
        canPricesUpdate ? (
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingRule(row);
              form.setFieldsValue({
                member_level_id: row.member_level_id,
                scope_type: row.scope_type,
                sku_id: row.sku_id,
                product_id: row.product_id,
                category_id: row.category_id,
                price_mode: row.price_mode,
                fixed_price: row.fixed_price,
                discount_factor: row.discount_factor,
                is_active: row.is_active ?? true,
              });
              setModalOpen(true);
            }}
          >
            编辑
          </Button>
        ) : null,
    },
  ];

  return (
    <PageFrame
      title="会员价格"
      description="配置各会员等级针对指定商品变体 SKU、SPU 商品或全品类的一口价特惠、分层折扣或排除规则。"
    >
      {canPricesCreate && (
        <div style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingRule(null);
              form.resetFields();
              form.setFieldsValue({
                scope_type: "sku",
                price_mode: "fixed",
                is_active: true,
              });
              setModalOpen(true);
            }}
          >
            新建会员价格规则
          </Button>
        </div>
      )}

      {!canPricesRead ? (
        <Alert type="warning" title="无权查看会员价格规则列表" />
      ) : rulesError ? (
        <QueryState loading={false} error={rulesError.message} onRetry={() => void reloadRules()} />
      ) : (
        <Table<MemberPriceRuleRead>
          rowKey="id"
          loading={isLoading}
          dataSource={rulesData?.items ?? []}
          columns={columns.map((col) => ({
            ...col,
            onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
            onCell: () => ({ style: { whiteSpace: "nowrap" } }),
          }))}
          scroll={{ x: "max-content" }}
          pagination={{
            current: page,
            pageSize: 20,
            showSizeChanger: false,
            total: rulesData?.total ?? 0,
            onChange: (p) => setPage(p),
            showTotal: (total) => `共 ${total} 条规则`,
          }}
        />
      )}

      <Modal
        title={editingRule ? "编辑会员价格规则" : "新建会员价格规则"}
        open={modalOpen}
        mask={{ closable: false }} closable={!saveMutation.isPending} keyboard={!saveMutation.isPending}
        cancelButtonProps={{ disabled: saveMutation.isPending }}
        onCancel={() => {
          if (saveMutation.isPending) return;
          setModalOpen(false);
          setEditingRule(null);
        }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
      >
        <QueryState loading={false} error={levelsError?.message} onRetry={() => void reloadLevels()} />
        <Form form={form} layout="vertical" disabled={saveMutation.isPending} onFinish={saveMutation.mutate}>
          <Form.Item
            name="member_level_id"
            label="适用会员等级"
            rules={[{ required: true, message: "请选择会员等级" }]}
          >
            {!canAccess(admin, "member-levels:read") ? <Input placeholder="输入会员等级 UUID" /> : <Select
              placeholder="选择会员等级"
              options={
                levelsData?.map((l: MemberLevelRead) => ({
                  value: l.id,
                  label: `${l.name} (${l.code})`,
                })) ?? []
              }
            />}
          </Form.Item>
          <Form.Item name="scope_type" label="规则适用范围" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "sku", label: "SKU 变体单品" },
                { value: "product", label: "SPU 商品整体" },
                { value: "category", label: "商品分类" },
              ]}
            />
          </Form.Item>

          {scopeType === "sku" && (
            <Form.Item name="sku_id" label="目标 SKU ID" rules={[{ required: true, message: "请输入目标 SKU ID" }]}>
              <Input placeholder="输入商品变体 SKU 标识 UUID" />
            </Form.Item>
          )}

          {scopeType === "product" && (
            <Form.Item name="product_id" label="目标商品 ID" rules={[{ required: true, message: "请输入商品 ID" }]}>
              <Input placeholder="输入 SPU 商品标识 UUID" />
            </Form.Item>
          )}

          {scopeType === "category" && (
            <Form.Item name="category_id" label="目标分类 ID" rules={[{ required: true, message: "请输入分类 ID" }]}>
              <Input placeholder="输入分类标识 UUID" />
            </Form.Item>
          )}

          <Form.Item name="price_mode" label="价格模式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "fixed", label: "一口价 (固定会员专属优惠价)", disabled: scopeType === "category" },
                { value: "discount", label: "特定折扣率 (按标价折算)" },
                { value: "exclude", label: "排除规则 (该目标不参与任何会员特价)" },
              ]}
            />
          </Form.Item>

          {priceMode === "fixed" && (
            <Form.Item
              name="fixed_price"
              label="会员一口价金额 (元)"
              rules={[{ required: true, message: "请输入一口价金额" }]}
            >
              <InputNumber stringMode min="0" precision={2} step="0.01" style={{ width: "100%" }} placeholder="如 88.00" />
            </Form.Item>
          )}

          {priceMode === "discount" && (
            <Form.Item
              name="discount_factor"
              label="特定折扣率"
              tooltip="例如 0.85 代表 8.5 折"
              rules={[{ required: true, message: "请输入折扣率" }]}
            >
              <InputNumber stringMode min="0" max="1" precision={6} step="0.01" style={{ width: "100%" }} placeholder="如 0.85" />
            </Form.Item>
          )}

          <Form.Item name="is_active" label="是否启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </PageFrame>
  );
}
