import { DownloadOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Select, Space, message } from "antd";
import { useRef, useState, type Key, type ReactNode } from "react";

import { ResourceTable } from "./ResourceTable";
import { canAccess, useCurrentAdmin } from "@/lib/auth-context";
import { commerceApi, type CommerceFilters, type CommerceResource } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";

export type CommerceFilterField = {
  name: keyof CommerceFilters; label: string;
  options?: { label: string; value: string }[];
};

export function CommerceList<T extends object>({ resource, title, load, columns, fields, rowKey = "id", toolbar = [] }: {
  resource: CommerceResource; title: string; load: (filters: CommerceFilters) => Promise<{ items: T[]; total: number }>;
  columns: ProColumns<T>[]; fields: CommerceFilterField[]; rowKey?: string; toolbar?: ReactNode[];
}) {
  const admin = useCurrentAdmin();
  const permission =
    resource === "reconciliation-records"
      ? "reconciliation"
      : resource === "refund-executions"
      ? "refunds"
      : resource;
  const allowed = canAccess(admin, `${permission}:read`);
  const canExport = canAccess(admin, `${permission}:export`);
  const [form] = Form.useForm<CommerceFilters>();
  const [filters, setFilters] = useState<CommerceFilters>({ page: 1, page_size: 20 });
  const [keys, setKeys] = useState<Key[]>([]);
  const [busy, setBusy] = useState(false);
  const [exportError, setExportError] = useState<string>();
  const lock = useRef(false);
  const query = useQuery({ queryKey: [`commerce-${resource}`, filters], queryFn: () => load(filters), enabled: allowed });
  const change = (next: CommerceFilters) => { setKeys([]); setExportError(undefined); setFilters(next); };
  const download = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setExportError(undefined);
    try {
      const data = await commerceApi.export(resource, { ids: keys.map(String) });
      // 引号转义及公式前缀防护，金额以服务端字符串原样传递。
      const cell = (value: string) => `"${(/^[\s]*[=+\-@\t\r]/.test(value) ? `'${value}` : value).replaceAll('"', '""')}"`;
      const csv = [data.columns, ...data.rows].map((row) => row.map(cell).join(",")).join("\r\n");
      const url = window.URL.createObjectURL(new window.Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
      try {
        const link = document.createElement("a"); link.href = url; link.download = `${title}.csv`;
        document.body.appendChild(link); link.click(); link.remove();
      } finally { window.URL.revokeObjectURL(url); }
      setKeys([]); message.success(`已导出 ${data.rows.length} 条记录`); await query.refetch();
    } catch (error) { setExportError(errorMessage(error)); }
    finally { lock.current = false; setBusy(false); }
  };
  if (!allowed) return <Alert type="warning" title={`无权查看${title}`} />;
  return <>
    <Form form={form} layout="inline" disabled={busy} style={{ gap: 12, marginBottom: 16 }} onFinish={(values) => change({ ...values, page: 1, page_size: 20 })}>
      {fields.map((field) => <Form.Item key={field.name} name={field.name} label={field.label}
        rules={field.name.endsWith("_id") ? [{ pattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i, message: "请输入完整 UUID" }] : undefined}>
        {field.options ? <Select allowClear style={{ width: 150 }} options={field.options} /> : <Input allowClear style={{ width: 220 }} />}
      </Form.Item>)}
      <Space><Button htmlType="submit" type="primary" icon={<SearchOutlined />}>查询</Button><Button icon={<ReloadOutlined />} onClick={() => { form.resetFields(); change({ page: 1, page_size: 20 }); }}>重置</Button></Space>
    </Form>
    {exportError && <Alert type="error" showIcon title={exportError} style={{ marginBottom: 12 }} />}
    <ResourceTable title={title} rows={query.data?.items ?? []} rowKey={rowKey} columns={columns}
      loading={query.isLoading} fetching={query.isFetching} error={query.error} retry={query.refetch}
      page={filters.page ?? 1} total={query.data?.total} onPage={(page) => { if (!lock.current) change({ ...filters, page }); }}
      selection={canExport ? { keys, onChange: (next) => { if (!lock.current) setKeys(next); }, disabled: busy } : undefined}
      toolbar={[...toolbar, ...(canExport ? [<Button key="export" icon={<DownloadOutlined />} disabled={!keys.length || keys.length > 100} loading={busy} onClick={() => void download()}>导出选中 ({keys.length})</Button>] : [])]} />
  </>;
}
