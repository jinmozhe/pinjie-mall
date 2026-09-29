import type { AssetRead } from "@pinjie/api-client";
import {
  DeleteOutlined,
  FolderOpenOutlined,
  PictureOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Alert, App, Button, Flex, Image, Typography, Upload, theme } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";

import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";
import { AssetSelectModal } from "./AssetSelectModal";

export type BrandLogoPickerProps = {
  value?: string | null;
  url?: string | null;
  onChange?: (assetId: string | null, url: string | null) => void;
  disabled?: boolean;
  maxSizeMb?: number;
};

const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function BrandLogoPicker({
  value,
  url,
  onChange,
  disabled = false,
  maxSizeMb = 2,
}: BrandLogoPickerProps) {
  const { message } = App.useApp();
  const { token } = theme.useToken();

  const [uploading, setUploading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmRemoval, setConfirmRemoval] = useState(false);
  const [error, setError] = useState<string>();

  const beforeUpload: UploadProps["beforeUpload"] = (file) => {
    if (!IMAGE_TYPES.has(file.type)) {
      setError("仅支持 JPG、PNG 或 WebP 格式图片");
      return Upload.LIST_IGNORE;
    }
    if (file.size > maxSizeMb * 1024 * 1024) {
      setError(`图片大小不能超过 ${maxSizeMb} MB`);
      return Upload.LIST_IGNORE;
    }
    setError(undefined);
    return true;
  };

  const customRequest: UploadProps["customRequest"] = async ({ file, onError, onSuccess }) => {
    setUploading(true);
    setError(undefined);
    try {
      const asset = await adminApi.uploadAsset(file as globalThis.File, "product");
      onChange?.(asset.id, asset.url);
      onSuccess?.(asset);
      message.success("LOGO 图片上传成功");
    } catch (caught) {
      const text = errorMessage(caught);
      setError(text);
      onError?.(caught instanceof Error ? caught : new Error(text));
    } finally {
      setUploading(false);
    }
  };

  const handleSelectAsset = (asset: AssetRead) => {
    onChange?.(asset.id, asset.url);
    message.success("已选择素材作为品牌 LOGO");
  };

  const handleRemove = async () => {
    onChange?.(null, null);
    setConfirmRemoval(false);
    message.success("已移除 LOGO 关联，保存后生效");
  };

  const hasLogo = Boolean(url || value);

  return (
    <div>
      {hasLogo ? (
        <Flex gap={16} align="center" wrap="wrap">
          <div
            style={{
              width: 84,
              height: 84,
              borderRadius: token.borderRadiusLG,
              border: `1px solid ${token.colorBorderSecondary}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: token.colorFillQuaternary,
              overflow: "hidden",
            }}
          >
            {url ? (
              <Image
                src={url}
                alt="品牌 LOGO"
                style={{
                  maxHeight: 80,
                  maxWidth: 80,
                  objectFit: "contain",
                }}
              />
            ) : (
              <PictureOutlined style={{ fontSize: 32, color: token.colorTextTertiary }} />
            )}
          </div>
          <Flex vertical gap={8}>
            <Flex gap={8} wrap="wrap">
              <Upload
                accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                beforeUpload={beforeUpload}
                customRequest={customRequest}
                disabled={disabled || uploading}
                maxCount={1}
                showUploadList={false}
              >
                <Button
                  size="small"
                  icon={<UploadOutlined />}
                  loading={uploading}
                  disabled={disabled}
                >
                  重新上传
                </Button>
              </Upload>
              <Button
                size="small"
                icon={<FolderOpenOutlined />}
                disabled={disabled || uploading}
                onClick={() => setModalOpen(true)}
              >
                从素材库选择
              </Button>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={disabled || uploading}
                onClick={() => setConfirmRemoval(true)}
              >
                移除
              </Button>
            </Flex>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              已绑定 LOGO 资产。点击图片可预览大图，修改后需点击弹窗保存生效。
            </Typography.Text>
          </Flex>
        </Flex>
      ) : (
        <Flex vertical gap={8}>
          <Flex gap={8} wrap="wrap">
            <Upload
              accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
              beforeUpload={beforeUpload}
              customRequest={customRequest}
              disabled={disabled || uploading}
              maxCount={1}
              showUploadList={false}
            >
              <Button
                icon={<UploadOutlined />}
                loading={uploading}
                disabled={disabled}
              >
                上传 LOGO
              </Button>
            </Upload>
            <Button
              icon={<FolderOpenOutlined />}
              disabled={disabled || uploading}
              onClick={() => setModalOpen(true)}
            >
              从素材库选择
            </Button>
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            建议上传 1:1 正方形图片，支持 JPG、PNG 或 WebP，单张大小不超过 {maxSizeMb} MB。
          </Typography.Text>
        </Flex>
      )}

      {error && <Alert showIcon type="error" title={error} style={{ marginTop: 8 }} />}

      <AssetSelectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSelect={handleSelectAsset}
        selectedAssetId={value}
        scene="product"
        title="选择品牌 LOGO 素材"
      />

      <StandardConfirmModal
        open={confirmRemoval}
        title="确认移除品牌 LOGO"
        description="移除选中的 LOGO 后，保存品牌即可解除关联；已上传的文件资产仍保留在素材库中。取消将保留现有草稿。"
        loading={false}
        onCancel={() => setConfirmRemoval(false)}
        onConfirm={handleRemove}
      />
    </div>
  );
}

export default BrandLogoPicker;
