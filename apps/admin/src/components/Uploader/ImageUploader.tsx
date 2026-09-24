import type { UploadScene } from "@pinjie/api-client";
import { UploadOutlined } from "@ant-design/icons";
import { Alert, Button, Upload, App } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";

import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";

export type ImageUploaderProps = {
  value?: string | null;
  onChange?: (url: string) => void;
  onUploadingChange?: (uploading: boolean) => void;
  scene?: UploadScene;
  disabled?: boolean;
  maxSizeMb?: number;
};

const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function ImageUploader({
  onChange,
  onUploadingChange,
  scene = "avatar",
  disabled = false,
  maxSizeMb = 2,
}: ImageUploaderProps) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string>();

  const beforeUpload: UploadProps["beforeUpload"] = (file) => {
    if (!IMAGE_TYPES.has(file.type)) {
      setError("仅支持 JPG、PNG 或 WebP 图片");
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
    onUploadingChange?.(true);
    setError(undefined);
    try {
      const asset = await adminApi.uploadAsset(file as globalThis.File, scene);
      onChange?.(asset.url);
      onSuccess?.(asset);
      message.success("图片上传成功");
    } catch (caught) {
      const text = errorMessage(caught);
      setError(text);
      onError?.(caught instanceof Error ? caught : new Error(text));
    } finally {
      setUploading(false);
      onUploadingChange?.(false);
    }
  };

  return (
    <div>
      <Upload
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
        beforeUpload={beforeUpload}
        customRequest={customRequest}
        disabled={disabled || uploading}
        maxCount={1}
        showUploadList={false}
      >
        <Button icon={<UploadOutlined />} loading={uploading} disabled={disabled}>
          选择图片
        </Button>
      </Upload>
      {error && <Alert showIcon type="error" title={error} style={{ marginTop: 12 }} />}
    </div>
  );
}

export default ImageUploader;
