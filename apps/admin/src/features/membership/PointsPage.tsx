import { useRef, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import type {
  PointsAccountRead,
  PointsLedgerRead,
  PointsManualAdjustment,
} from "@pinjie/api-client";
import { PageFrame, QueryState } from "@/components/PageFrame";
import { useLockedMutation } from "@/lib/useLockedMutation";
import { canAccess, useCurrentAdmin } from "@/lib/auth-context";
import { commerceApi } from "@/lib/api/commerce";

export default function PointsPage() {
  const admin = useCurrentAdmin();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [ledgerPage, setLedgerPage] = useState(1);

  const canRead = canAccess(admin, "points:read");
  const canAdjust = canAccess(admin, "points:adjust");

  // Selected account for ledger drawer
  const [selectedAccount, setSelectedAccount] = useState<PointsAccountRead | null>(null);

  // Manual Adjustment Modal
  const [adjustModalOpen, setAdjustModalOpen] = useState(false);
  const [adjustForm] = Form.useForm();
  const currentOp = Form.useWatch("operation", adjustForm);
  const submitted = useRef<PointsManualAdjustment | null>(null);

  const { data: accountsData, isLoading, error: accountsError, refetch: reloadAccounts } = useQuery({
    queryKey: ["admin-points-accounts", page],
    queryFn: () => commerceApi.pointsAccounts(page),
    enabled: canRead,
  });

  const { data: ledgersData, isLoading: ledgersLoading, error: ledgersError, refetch: reloadLedgers } = useQuery({
    queryKey: ["admin-points-ledgers", selectedAccount?.id, ledgerPage],
    queryFn: () => commerceApi.pointsLedgers(selectedAccount!.id, ledgerPage),
    enabled: Boolean(selectedAccount) && canRead,
  });

  const adjustMutation = useLockedMutation({
    mutationFn: (values: PointsManualAdjustment) => {
      submitted.current ??= {
        user_id: values.user_id,
        operation: values.operation,
        points: values.points,
        reverses_ledger_id: values.operation === "reverse" ? values.reverses_ledger_id || null : null,
        note: values.note,
        idempotency_key: globalThis.crypto.randomUUID(),
      };
      return commerceApi.adjustPoints(submitted.current);
    },
    onSuccess: () => {
      message.success("积分人工调整成功");
      setAdjustModalOpen(false);
      submitted.current = null;
      adjustForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["admin-points-accounts"] });
      if (selectedAccount) {
        queryClient.invalidateQueries({ queryKey: ["admin-points-ledgers", selectedAccount.id] });
      }
    },
    onError: (err: Error) => {
      message.error(err.message || "积分调整失败");
    },
  });

  const columns: ColumnsType<PointsAccountRead> = [
    { title: "用户标识 (User ID)", dataIndex: "user_id", key: "user_id", ellipsis: true },
    {
      title: "可用积分",
      dataIndex: "available_points",
      key: "available_points",
      render: (v) => <Typography.Text strong style={{ color: "#389e0d" }}>{v}</Typography.Text>,
    },
    {
      title: "冻结积分",
      dataIndex: "frozen_points",
      key: "frozen_points",
      render: (v) => <Typography.Text type={v > 0 ? "warning" : "secondary"}>{v}</Typography.Text>,
    },
    {
      title: "欠积分",
      dataIndex: "debt_points",
      key: "debt_points",
      render: (v) => <Typography.Text type={v > 0 ? "danger" : "secondary"}>{v}</Typography.Text>,
    },
    { title: "版本", dataIndex: "revision", key: "revision", width: 80 },
    { title: "更新时间", dataIndex: "updated_at", key: "updated_at" },
    {
      title: "操作",
      key: "actions",
      width: "1%",
      render: (_, row) => (
        <Space size="small">
          <Button
            size="small"
            icon={<UnorderedListOutlined />}
            onClick={() => {
              setSelectedAccount(row);
              setLedgerPage(1);
            }}
          >
            积分流水
          </Button>
          {canAdjust && (
            <Button
              size="small"
              onClick={() => {
                adjustForm.resetFields();
                adjustForm.setFieldsValue({
                  user_id: row.user_id,
                  operation: "grant",
                  points: 100,
                });
                setAdjustModalOpen(true);
              }}
            >
              人工调整
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const ledgerColumns: ColumnsType<PointsLedgerRead> = [
    {
      title: "条目类型",
      dataIndex: "entry_type",
      key: "entry_type",
      render: (t) => <Tag color="blue">{t}</Tag>,
    },
    {
      title: "可用变动",
      dataIndex: "available_delta",
      key: "available_delta",
      render: (v: number) => {
        if (v > 0) return <Typography.Text type="success">+{v}</Typography.Text>;
        if (v < 0) return <Typography.Text type="danger">{v}</Typography.Text>;
        return <span>0</span>;
      },
    },
    {
      title: "冻结变动",
      dataIndex: "frozen_delta",
      key: "frozen_delta",
      render: (v: number) => {
        if (v === 0) return "-";
        return <Typography.Text type="warning">{v > 0 ? `+${v}` : v}</Typography.Text>;
      },
    },
    {
      title: "欠额变动",
      dataIndex: "debt_delta",
      key: "debt_delta",
      render: (v: number) => {
        if (v === 0) return "-";
        return <Typography.Text type="danger">{v > 0 ? `+${v}` : v}</Typography.Text>;
      },
    },
    {
      title: "来源信息",
      key: "source",
      render: (_, r) => <span>{r.source_type}: {r.source_id.slice(0, 8)}...</span>,
    },
    {
      title: "冲销原流水",
      dataIndex: "reverses_ledger_id",
      key: "reverses_ledger_id",
      ellipsis: true,
      render: (v) => v || "-",
    },
    { title: "说明备注", dataIndex: "note", key: "note", ellipsis: true, render: (v) => v || "-" },
    { title: "发生时间", dataIndex: "created_at", key: "created_at" },
  ];

  return (
    <PageFrame
      title="积分管理"
      description="查看商城用户积分账户资产（可用、冻结、欠积分），审计不可变积分流水并执行受控的人工授予与冲销操作。"
    >
      {canAdjust && (
        <div style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              adjustForm.resetFields();
              adjustForm.setFieldsValue({ operation: "grant", points: 100 });
              setAdjustModalOpen(true);
            }}
          >
            人工授予 / 冲销积分
          </Button>
        </div>
      )}

      {!canRead ? (
        <Alert type="warning" title="无权查看积分账户列表" />
      ) : accountsError ? (
        <QueryState loading={false} error={accountsError.message} onRetry={() => void reloadAccounts()} />
      ) : (
        <Table<PointsAccountRead>
          rowKey="id"
          loading={isLoading}
          dataSource={accountsData?.items ?? []}
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
            total: accountsData?.total ?? 0,
            onChange: (p) => setPage(p),
            showTotal: (total) => `共 ${total} 个积分账户`,
          }}
        />
      )}

      {/* Ledger Drawer */}
      <Drawer
        title={
          <Typography.Text strong>
            积分不可变流水 - 用户 {selectedAccount?.user_id}
          </Typography.Text>
        }
        open={Boolean(selectedAccount)}
        onClose={() => setSelectedAccount(null)}
        width={800}
      >
        <QueryState loading={false} error={ledgersError?.message} onRetry={() => void reloadLedgers()} />
        {!ledgersError && <Table<PointsLedgerRead>
          rowKey="id"
          loading={ledgersLoading}
          dataSource={ledgersData?.items ?? []}
          columns={ledgerColumns.map((col) => ({
            ...col,
            onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
            onCell: () => ({ style: { whiteSpace: "nowrap" } }),
          }))}
          scroll={{ x: "max-content" }}
          pagination={{
            current: ledgerPage,
            pageSize: 20,
            showSizeChanger: false,
            total: ledgersData?.total ?? 0,
            onChange: (p) => setLedgerPage(p),
            showTotal: (total) => `共 ${total} 条积分流水`,
          }}
        />}
      </Drawer>

      {/* Adjust Points Modal */}
      <Modal
        title="人工授予或冲销积分"
        open={adjustModalOpen}
        maskClosable={false}
        closable={!adjustMutation.isPending}
        keyboard={!adjustMutation.isPending}
        cancelButtonProps={{ disabled: adjustMutation.isPending }}
        onCancel={() => {
          if (adjustMutation.isPending) return;
          setAdjustModalOpen(false);
          adjustForm.resetFields();
          submitted.current = null;
          adjustMutation.reset();
        }}
        onOk={() => { if (submitted.current) adjustMutation.mutate(submitted.current); else adjustForm.submit(); }}
        confirmLoading={adjustMutation.isPending}
      >
        {adjustMutation.error && <Alert type="error" showIcon title={adjustMutation.error.message} description="重试将沿用同一请求及幂等键。取消前请核对积分流水，避免重复发起调整。" />}
        <Form form={adjustForm} layout="vertical" disabled={adjustMutation.isPending || Boolean(submitted.current)} onFinish={adjustMutation.mutate}>
          <Form.Item
            name="user_id"
            label="目标用户 ID (UUID)"
            rules={[{ required: true, message: "请输入目标用户 UUID" }]}
          >
            <Input placeholder="输入用户 UUID" />
          </Form.Item>
          <Form.Item name="operation" label="操作类型" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "grant", label: "人工授予积分 (增加可用积分)" },
                { value: "reverse", label: "冲销原授予积分 (回退原授予流水)" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="points"
            label="积分点数"
            rules={[{ required: true, message: "请输入积分数量" }]}
          >
            <InputNumber min={1} step={1} precision={0} style={{ width: "100%" }} placeholder="输入整数积分数量" />
          </Form.Item>
          {currentOp === "reverse" && (
            <Form.Item
              name="reverses_ledger_id"
              label="被冲销的原积分流水 ID"
              rules={[{ required: true, message: "冲销操作必须填写原流水 ID" }]}
            >
              <Input placeholder="输入原 PointsLedger 的 UUID" />
            </Form.Item>
          )}
          <Form.Item
            name="note"
            label="操作原因及核对说明"
            rules={[{ required: true, message: "请输入操作说明以便审计" }]}
          >
            <Input.TextArea rows={3} placeholder="详细记录授予或冲销原因，用于合规审计" />
          </Form.Item>
        </Form>
      </Modal>
    </PageFrame>
  );
}
