import type { AssetRead, UploaderType, UploadScene } from "@pinjie/api-client";
import {
  CopyOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileOutlined,
  FilterOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { ProTable } from "@ant-design/pro-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Drawer, Image, Input, Select, Space, Tag, Tooltip, Typography, App } from "antd";
import { useState } from "react";

import { PageFrame, QueryState, formatTime } from "@/components/PageFrame";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";

type Confirmation = { description: string; title: string; execute: () => Promise<unknown> };

const sceneLabels: Record<UploadScene, string> = {
  avatar: "头像",
  article: "文章",
  product: "商品",
  document: "文档",
  attachment: "附件",
  temp: "临时文件",
};

const uploaderLabels: Record<UploaderType, string> = {
  admin: "管理员",
  user: "用户",
  system: "系统",
};

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function isImage(asset: AssetRead): boolean {
  return asset.mime_type.startsWith("image/");
}

export function AssetsPage() {
  const { message } = App.useApp();
  const current = useCurrentAdmin();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [scene, setScene] = useState<UploadScene | undefined>();
  const [uploaderType, setUploaderType] = useState<UploaderType | undefined>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [previewAsset, setPreviewAsset] = useState<AssetRead | null>(null);
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false);
  const canDelete = canAccess(current, "assets:delete");
  const activeFilterCount = Number(Boolean(scene)) + Number(Boolean(uploaderType));
  const assets = useQuery({
    queryKey: ["assets", page, search, scene, uploaderType],
    queryFn: () => adminApi.assets({ page, search: search || undefined, scene, uploaderType }),
  });
  const invalidate = async () => queryClient.invalidateQueries({ queryKey: ["assets"] });
  const batchDeleteMutation = useMutation({
    mutationFn: (assetIds: string[]) => adminApi.deleteAssetsBulk({ asset_ids: assetIds }),
    onSuccess: async (result) => {
      message.success(`已永久删除 ${result.completed_count} 个文件资产`);
      setSelectedRowKeys([]);
      await invalidate();
    },
  });
  const deleteAssetMutation = useMutation({
    mutationFn: (assetId: string) => adminApi.deleteAsset(assetId),
    onSuccess: async () => {
      message.success("文件资产已永久删除");
      await invalidate();
    },
  });
  const begin = (title: string, description: string, execute: () => Promise<unknown>) => {
    setConfirmation({ title, description, execute });
  };
  const confirmAction = async () => {
    if (!confirmation) return;
    try {
      await confirmation.execute();
      setConfirmation(null);
    } catch (error) {
      message.error(errorMessage(error));
    }
  };
  const clearSelectionAndResetPage = () => {
    setPage(1);
    setSelectedRowKeys([]);
  };
  const submitSearch = () => {
    clearSelectionAndResetPage();
    setSearch(searchDraft.trim());
  };
  const resetFilters = () => {
    clearSelectionAndResetPage();
    setSearchDraft("");
    setSearch("");
    setScene(undefined);
    setUploaderType(undefined);
  };
  const copyUrl = async (url: string) => {
    try {
      await globalThis.navigator.clipboard.writeText(url);
      message.success("文件地址已复制");
    } catch (error) {
      message.error(errorMessage(error));
    }
  };
  const copyUploaderId = async (uploaderId: string) => {
    try {
      await globalThis.navigator.clipboard.writeText(uploaderId);
      message.success("上传主体 ID 已复制");
    } catch (error) {
      message.error(errorMessage(error));
    }
  };

  return (
    <PageFrame title="文件资产" description="查询统一文件资产并执行受控的永久删除。">
      <QueryState
        loading={assets.isLoading}
        error={assets.isError ? errorMessage(assets.error) : undefined}
        onRetry={() => void assets.refetch()}
      />
      {assets.data && (
        <ProTable<AssetRead>
          className="responsive-data-table"
          rowKey="id"
          headerTitle="资产列表"
          dataSource={assets.data.items}
          search={false}
          options={{
            density: true,
            fullScreen: true,
            reload: () => void assets.refetch(),
            setting: true,
          }}
          cardProps={false}
          rowSelection={canDelete ? {
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys.map(String)),
          } : false}
          tableAlertRender={({ selectedRowKeys: keys }) => <span>已选择 {keys.length} 项</span>}
          tableAlertOptionRender={({ onCleanSelected }) => (
            <Space size={8} wrap={false}>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={batchDeleteMutation.isPending}
                loading={batchDeleteMutation.isPending}
                onClick={() => {
                  const assetIds = [...selectedRowKeys];
                  begin(
                    `确认批量删除 ${assetIds.length} 个文件资产`,
                    "文件资产及其存储文件将被永久删除。删除后无法恢复，请确认选中范围。",
                    () => batchDeleteMutation.mutateAsync(assetIds),
                  );
                }}
              >
                批量删除
              </Button>
              <Button type="link" size="small" onClick={onCleanSelected}>取消选择</Button>
            </Space>
          )}
          toolBarRender={() => [(
            <div className="responsive-table-toolbar assets-table-toolbar" key="asset-toolbar">
              <Input.Search
                className="table-toolbar-search"
                allowClear
                aria-label="搜索文件名"
                placeholder="搜索文件名"
                style={{ width: 220 }}
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                onSearch={submitSearch}
              />
              <div className="table-toolbar-desktop-filters">
                <Select<UploadScene>
                  allowClear
                  aria-label="筛选使用场景"
                  placeholder="使用场景"
                  style={{ width: 140 }}
                  value={scene}
                  options={Object.entries(sceneLabels).map(([value, label]) => ({ value: value as UploadScene, label }))}
                  onChange={(value) => {
                    clearSelectionAndResetPage();
                    setScene(value);
                  }}
                />
                <Select<UploaderType>
                  allowClear
                  aria-label="筛选上传主体"
                  placeholder="上传主体"
                  style={{ width: 130 }}
                  value={uploaderType}
                  options={Object.entries(uploaderLabels).map(([value, label]) => ({ value: value as UploaderType, label }))}
                  onChange={(value) => {
                    clearSelectionAndResetPage();
                    setUploaderType(value);
                  }}
                />
              </div>
              <Button
                className="table-toolbar-mobile-filter"
                icon={<FilterOutlined />}
                onClick={() => setFilterDrawerOpen(true)}
              >
                {activeFilterCount > 0 ? `筛选 (${activeFilterCount})` : "筛选"}
              </Button>
              <Button className="table-toolbar-reset" icon={<ReloadOutlined />} onClick={resetFilters}>重置</Button>
            </div>
          )]}
          scroll={{ x: "max-content" }}
          pagination={{
            current: page,
            pageSize: assets.data.page_size,
            total: assets.data.total,
            showSizeChanger: false,
            onChange: (nextPage) => {
              setPage(nextPage);
              setSelectedRowKeys([]);
            },
          }}
          columns={[
            {
              title: "文件",
              dataIndex: "original_name",
              minWidth: 260,
              render: (_, row) => (
                <div className="asset-file-cell">
                  {isImage(row) ? (
                    <Image className="asset-thumbnail" src={row.url} alt={row.original_name} width={44} height={44} />
                  ) : (
                    <span className="asset-file-icon"><FileOutlined /></span>
                  )}
                  <div className="table-primary-cell">
                    <Typography.Text strong ellipsis={{ tooltip: row.original_name }}>{row.original_name}</Typography.Text>
                    <Typography.Text type="secondary">{formatBytes(row.file_size)} · {row.mime_type}</Typography.Text>
                  </div>
                </div>
              ),
            },
            { title: "场景", dataIndex: "scene", width: 110, render: (_, row) => <Tag>{sceneLabels[row.scene]}</Tag> },
            {
              title: "上传主体",
              dataIndex: "uploader_type",
              width: 180,
              responsive: ["lg"],
              render: (_, row) => {
                const uploaderId = row.uploader_id;
                return uploaderId ? (
                  <Space size={2} wrap={false}>
                    <Typography.Text>{uploaderLabels[row.uploader_type]}</Typography.Text>
                    <Tooltip title="复制上传主体 ID">
                      <Button
                        type="text"
                        size="small"
                        aria-label="复制上传主体 ID"
                        icon={<CopyOutlined />}
                        onClick={() => void copyUploaderId(uploaderId)}
                      />
                    </Tooltip>
                  </Space>
                ) : (
                  <div className="table-primary-cell">
                    <Typography.Text>{uploaderLabels[row.uploader_type]}</Typography.Text>
                    <Typography.Text type="secondary">系统任务</Typography.Text>
                  </div>
                );
              },
            },
            { title: "创建时间", dataIndex: "created_at", width: 170, responsive: ["xl"], render: (_, row) => formatTime(row.created_at) },
            {
              title: "操作",
              key: "actions",
              width: "1%",
              onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
              onCell: () => ({ style: { whiteSpace: "nowrap" } }),
              render: (_, row) => (
                <Space className="table-actions" size={[2, 0]} wrap={false}>
                  {isImage(row) ? (
                    <Button
                      type="link"
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => setPreviewAsset(row)}
                    >
                      打开
                    </Button>
                  ) : (
                    <Button
                      type="link"
                      size="small"
                      icon={<EyeOutlined />}
                      href={row.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打开
                    </Button>
                  )}
                  <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => void copyUrl(row.url)}>复制地址</Button>
                  {canDelete && (
                    <Button
                      type="link"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => begin(
                        `永久删除文件“${row.original_name}”`,
                        "文件资产及其存储文件将被永久删除，删除后无法恢复。",
                        () => deleteAssetMutation.mutateAsync(row.id),
                      )}
                    >
                      删除
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      )}
      <Drawer
        className="asset-filter-drawer"
        destroyOnHidden
        extra={<Button type="primary" onClick={() => setFilterDrawerOpen(false)}>完成</Button>}
        size={360}
        open={filterDrawerOpen}
        placement="bottom"
        title="筛选文件资产"
        onClose={() => setFilterDrawerOpen(false)}
      >
        <div className="mobile-filter-stack">
          <div className="mobile-filter-field">
            <Typography.Text strong>使用场景</Typography.Text>
            <Select<UploadScene>
              allowClear
              aria-label="移动端筛选使用场景"
              placeholder="全部使用场景"
              value={scene}
              options={Object.entries(sceneLabels).map(([value, label]) => ({ value: value as UploadScene, label }))}
              onChange={(value) => {
                clearSelectionAndResetPage();
                setScene(value);
              }}
            />
          </div>
          <div className="mobile-filter-field">
            <Typography.Text strong>上传主体</Typography.Text>
            <Select<UploaderType>
              allowClear
              aria-label="移动端筛选上传主体"
              placeholder="全部上传主体"
              value={uploaderType}
              options={Object.entries(uploaderLabels).map(([value, label]) => ({ value: value as UploaderType, label }))}
              onChange={(value) => {
                clearSelectionAndResetPage();
                setUploaderType(value);
              }}
            />
          </div>
          <Button block icon={<ReloadOutlined />} onClick={resetFilters}>清空筛选</Button>
        </div>
      </Drawer>
      {previewAsset && (
        <Image
          alt={previewAsset.original_name}
          src={previewAsset.url}
          style={{ display: "none" }}
          preview={{
            open: true,
            onOpenChange: (open) => {
              if (!open) setPreviewAsset(null);
            },
          }}
        />
      )}
      <StandardConfirmModal
        description={confirmation?.description ?? ""}
        loading={batchDeleteMutation.isPending || deleteAssetMutation.isPending}
        open={Boolean(confirmation)}
        title={confirmation?.title ?? "确认操作"}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirmAction}
      />
    </PageFrame>
  );
}

export default AssetsPage;
