import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Alert } from "antd";
import type { Key, ReactNode } from "react";

import { QueryState } from "./PageFrame";
import { errorMessage } from "@/lib/api/http";

type Props<T extends object> = {
  title: string; rows: T[]; columns: ProColumns<T>[];
  rowKey?: string; loading: boolean; fetching?: boolean; error?: Error | null;
  retry: () => unknown; toolbar?: ReactNode[];
  page?: number; total?: number; onPage?: (page: number) => void;
  selection?: { keys: Key[]; onChange: (keys: Key[], rows: T[]) => void; disabled?: boolean };
};

export function ResourceTable<T extends object>({ title, rows, columns, rowKey = "id", loading, fetching, error, retry, toolbar, page, total, onPage, selection }: Props<T>) {
  return <>
    <QueryState loading={loading} error={error ? errorMessage(error) : undefined} onRetry={() => { retry(); }} />
    {!loading && !error && <ProTable<T>
      className="responsive-data-table" rowKey={rowKey} headerTitle={`${title}列表`}
      dataSource={rows} search={false} loading={fetching} toolBarRender={() => toolbar ?? []}
      columns={columns.map((column) => ({ ...column,
        onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
        onCell: () => ({ style: { whiteSpace: "nowrap" } }),
      }))}
      scroll={rows.length ? { x: "max-content" } : undefined}
      options={{ reload: () => { retry(); }, density: true, setting: true, fullScreen: true }}
      pagination={onPage ? { current: page, total, pageSize: 20, showSizeChanger: false, onChange: onPage } : false}
      rowSelection={selection ? { selectedRowKeys: selection.keys, onChange: selection.onChange,
        getCheckboxProps: () => ({ disabled: selection.disabled }), preserveSelectedRowKeys: false,
      } : false}
      tableAlertRender={selection ? ({ selectedRowKeys }) => <Alert type="info" title={`已选择 ${selectedRowKeys.length} 项`} /> : false}
      tableAlertOptionRender={false}
    />}
  </>;
}
