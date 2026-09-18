import { ArrowUpOutlined, DeleteOutlined, UploadOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Image, Input, List, Pagination, Space, Tag, Upload, message } from "antd";
import { useRef, useState } from "react";

import { QueryState } from "@/components/PageFrame";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";

export function ProductImages({ value = [], onChange, onUploading }: { value?: string[]; onChange?: (value: string[]) => void; onUploading?: (busy: boolean) => void }) {
  const admin = useCurrentAdmin();
  const allowed = canAccess(admin, "assets:read");
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [remove, setRemove] = useState<string>();
  const [uploading, setUploading] = useState(false);
  const uploadLock = useRef(false);
  const latestValue = useRef(value);
  latestValue.current = value;
  const query = useQuery({ queryKey: ["commerce-image-assets", page, search], enabled: allowed,
    queryFn: () => adminApi.assets({ page, search: search || undefined, scene: "product" }) });
  const images = (query.data?.items ?? []).filter((asset) => ["admin", "system"].includes(asset.uploader_type) && ["image/jpeg", "image/png", "image/webp"].includes(asset.mime_type));
  return <Space direction="vertical" style={{ width: "100%" }}>
    <div>{value.map((id, index) => <Tag key={id} style={{ marginBottom: 8 }}>
      {index === 0 ? "主图" : `图片 ${index + 1}`}：{images.find((item) => item.id === id)?.original_name ?? id.slice(0, 12)}
      {index > 0 && <Button type="text" size="small" aria-label={`将图片 ${index + 1} 设为主图`} icon={<ArrowUpOutlined />} onClick={() => onChange?.([id, ...value.filter((item) => item !== id)])} />}
      <Button type="text" size="small" danger aria-label={`移除图片 ${index + 1}`} icon={<DeleteOutlined />} onClick={() => setRemove(id)} />
    </Tag>)}</div>
    <Space wrap>
      <Input.Search allowClear placeholder="搜索商品图片" onSearch={(text) => { setPage(1); setSearch(text.trim()); }} />
      <Upload accept="image/jpeg,image/png,image/webp" showUploadList={false} disabled={uploading || value.length >= 20} beforeUpload={(file) => {
        if (uploadLock.current) return false;
        uploadLock.current = true;
        onUploading?.(true);
        setUploading(true);
        void adminApi.uploadAsset(file, "product").then(async (asset) => {
          const current = latestValue.current;
          if (!current.includes(asset.id) && current.length < 20) onChange?.([...current, asset.id]);
          await client.invalidateQueries({ queryKey: ["commerce-image-assets"] });
          message.success("图片已上传并加入草稿");
        }).catch((error) => message.error(errorMessage(error))).finally(() => { uploadLock.current = false; setUploading(false); onUploading?.(false); });
        return false;
      }}><Button loading={uploading} icon={<UploadOutlined />}>上传商品图片</Button></Upload>
    </Space>
    {!allowed ? <Alert type="info" title="没有资产查询权限，可上传新图片；已绑定图片会保留。" /> : <>
      <QueryState loading={query.isLoading} error={query.error ? errorMessage(query.error) : undefined} onRetry={() => void query.refetch()} />
      {!query.isLoading && !query.error && <List size="small" dataSource={images} locale={{ emptyText: "暂无可选商品图片" }} renderItem={(asset) => <List.Item actions={[
        <Button key="choose" disabled={value.includes(asset.id) || value.length >= 20} onClick={() => onChange?.([...value, asset.id])}>{value.includes(asset.id) ? "已选" : "选择"}</Button>,
      ]}><Space><Image src={asset.url} alt={asset.original_name} width={40} height={40} /><span>{asset.original_name}</span></Space></List.Item>} />}
      <Pagination size="small" current={page} total={query.data?.total} pageSize={20} showSizeChanger={false} onChange={setPage} />
    </>}
    <StandardConfirmModal open={Boolean(remove)} title="移除商品图片" description="仅从商品草稿移除绑定，保存商品后生效；文件资产仍保留。" loading={false} onCancel={() => setRemove(undefined)} onConfirm={async () => { onChange?.(value.filter((id) => id !== remove)); setRemove(undefined); }} />
  </Space>;
}
