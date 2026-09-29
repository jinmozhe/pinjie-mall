import type { AssetRead, UploadScene } from "@pinjie/api-client";
import { CheckCircleFilled, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Empty, Flex, Image, Input, Modal, Pagination, Spin, Typography, theme } from "antd";
import { useState } from "react";

import { canAccess, useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";

export type AssetSelectModalProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (asset: AssetRead) => void;
  scene?: UploadScene;
  title?: string;
  selectedAssetId?: string | null;
};

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function AssetSelectModal({
  open,
  onClose,
  onSelect,
  scene = "product",
  title = "选择图片素材",
  selectedAssetId,
}: AssetSelectModalProps) {
  const { token } = theme.useToken();
  const admin = useCurrentAdmin();
  const allowed = canAccess(admin, "assets:read");

  const [page, setPage] = useState(1);
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AssetRead | null>(null);

  const query = useQuery({
    queryKey: ["asset-select-list", page, search, scene],
    queryFn: () =>
      adminApi.assets({
        page,
        search: search || undefined,
        scene,
      }),
    enabled: open && allowed,
  });

  const handleSearch = () => {
    setPage(1);
    setSearch(searchDraft.trim());
  };

  const handleReset = () => {
    setSearchDraft("");
    setSearch("");
    setPage(1);
  };

  const handleConfirm = () => {
    if (selected) {
      onSelect(selected);
      onClose();
    }
  };

  const items = (query.data?.items ?? []).filter((asset) => asset.mime_type.startsWith("image/"));

  return (
    <Modal
      open={open}
      title={title}
      width={760}
      destroyOnHidden
      onCancel={onClose}
      footer={
        <Flex justify="space-between" align="center" style={{ width: "100%" }}>
          <Pagination
            size="small"
            current={page}
            pageSize={20}
            total={query.data?.total ?? 0}
            showSizeChanger={false}
            onChange={(nextPage) => {
              setPage(nextPage);
            }}
          />
          <Flex gap={8}>
            <Button onClick={onClose}>取消</Button>
            <Button
              type="primary"
              disabled={!selected}
              onClick={handleConfirm}
            >
              确定选择
            </Button>
          </Flex>
        </Flex>
      }
    >
      <Flex vertical gap={12} style={{ marginBlock: 12 }}>
        {!allowed ? (
          <Alert showIcon type="warning" title="无权查看素材库，请联系管理员分配素材查看权限。" />
        ) : (
          <>
            <Flex gap={8} align="center">
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="按文件名搜索已有素材"
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                onPressEnter={handleSearch}
                style={{ maxWidth: 300 }}
              />
              <Button type="primary" onClick={handleSearch}>
                搜索
              </Button>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>
                重置
              </Button>
            </Flex>

            {query.isError && (
              <Alert showIcon type="error" title={errorMessage(query.error)} />
            )}

            <Spin spinning={query.isLoading || query.isFetching}>
              <div
                style={{
                  minHeight: 340,
                  maxHeight: 460,
                  overflowY: "auto",
                  padding: 4,
                }}
              >
                {!items.length && !query.isLoading ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无符合条件的图片素材"
                    style={{ marginBlock: 60 }}
                  />
                ) : (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))",
                      gap: 12,
                    }}
                  >
                    {items.map((asset) => {
                      const isCurrentSelected =
                        selected?.id === asset.id ||
                        (!selected && selectedAssetId === asset.id);
                      return (
                        <div
                          key={asset.id}
                          role="button"
                          tabIndex={0}
                          onClick={() => setSelected(asset)}
                          onDoubleClick={() => {
                            onSelect(asset);
                            onClose();
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              setSelected(asset);
                            }
                          }}
                          style={{
                            position: "relative",
                            border: `2px solid ${
                              isCurrentSelected
                                ? token.colorPrimary
                                : token.colorBorderSecondary
                            }`,
                            borderRadius: token.borderRadiusLG,
                            padding: 6,
                            cursor: "pointer",
                            backgroundColor: isCurrentSelected
                              ? token.colorPrimaryBg
                              : token.colorBgContainer,
                            transition: "all 0.2s",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                          }}
                        >
                          {isCurrentSelected && (
                            <CheckCircleFilled
                              style={{
                                position: "absolute",
                                top: 6,
                                right: 6,
                                fontSize: 16,
                                color: token.colorPrimary,
                                backgroundColor: "#fff",
                                borderRadius: "50%",
                                zIndex: 1,
                              }}
                            />
                          )}
                          <div
                            style={{
                              width: "100%",
                              height: 90,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              overflow: "hidden",
                              backgroundColor: token.colorFillQuaternary,
                              borderRadius: token.borderRadiusSM,
                            }}
                          >
                            <Image
                              src={asset.url}
                              alt={asset.original_name}
                              preview={false}
                              style={{
                                maxHeight: 90,
                                maxWidth: "100%",
                                objectFit: "contain",
                              }}
                              fallback="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 24 24'><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' fill='%23ccc'>图片</text></svg>"
                            />
                          </div>
                          <div
                            style={{
                              width: "100%",
                              marginTop: 6,
                              textAlign: "center",
                            }}
                          >
                            <Typography.Text
                              ellipsis={{ tooltip: asset.original_name }}
                              style={{
                                fontSize: 12,
                                display: "block",
                                lineHeight: "16px",
                              }}
                            >
                              {asset.original_name}
                            </Typography.Text>
                            <Typography.Text
                              type="secondary"
                              style={{
                                fontSize: 11,
                                display: "block",
                                marginTop: 2,
                              }}
                            >
                              {asset.width && asset.height
                                ? `${asset.width}×${asset.height} · `
                                : ""}
                              {formatBytes(asset.file_size)}
                            </Typography.Text>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </Spin>
          </>
        )}
      </Flex>
    </Modal>
  );
}

export default AssetSelectModal;
