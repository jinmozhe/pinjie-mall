import type { AssetRead, ProductImageRead } from "@pinjie/api-client";
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, ReloadOutlined, UploadOutlined, VerticalAlignBottomOutlined, VerticalAlignTopOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Checkbox, Empty, Flex, Image, Input, Listy, Pagination, Space, Tag, Typography, Upload, theme } from "antd";
import { useEffect, useRef, useState } from "react";

import { QueryState } from "@/components/PageFrame";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";
import { validateGallery } from "./product-image-policy";

type Entry =
  | { key: string; status: "ready"; image: ProductImageRead }
  | { key: string; status: "queued" | "uploading" | "error"; file: globalThis.File; error?: string };
export type GalleryState = { uploading: boolean; unresolved: boolean };

export function ProductImageGallery({ initialImages, detail = false, onChange, onStateChange }: {
  initialImages: ProductImageRead[];
  detail?: boolean;
  onChange: (images: ProductImageRead[]) => void;
  onStateChange: (state: GalleryState) => void;
}) {
  const { token } = theme.useToken();
  const { message } = App.useApp();
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const allowed = canAccess(admin, "assets:read");
  const [entries, setEntries] = useState<Entry[]>(() => initialImages.map((image) => ({ key: "asset:" + image.asset_id, status: "ready", image })));
  const current = useRef(entries);
  const callbacks = useRef({ onChange, onStateChange });
  callbacks.current = { onChange, onStateChange };
  const alive = useRef(true);
  const running = useRef(false);
  const serial = useRef(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [removal, setRemoval] = useState<string[]>();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<string[]>([]);
  const [notice, setNotice] = useState<string>();
  const label = detail ? "详情图" : "轮播图";
  const busy = entries.some((entry) => entry.status === "queued" || entry.status === "uploading");
  const assets = useQuery({
    queryKey: ["commerce-image-assets", page, search],
    queryFn: () => adminApi.assets({ page, search: search || undefined, scene: "product" }),
    enabled: allowed,
  });
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const readyImages = (items: Entry[]) => items.flatMap((entry) => entry.status === "ready" ? [entry.image] : []);
  const publish = (items: Entry[]) => {
    if (!alive.current) return;
    current.current = items;
    setEntries(items);
    callbacks.current.onChange(readyImages(items));
    callbacks.current.onStateChange({
      uploading: items.some((entry) => entry.status === "queued" || entry.status === "uploading"),
      unresolved: items.some((entry) => entry.status !== "ready"),
    });
  };
  const fromAsset = (asset: AssetRead): ProductImageRead => ({
    asset_id: asset.id, url: asset.url, original_name: asset.original_name, file_size: asset.file_size,
    width: asset.width, height: asset.height, frame_count: asset.frame_count,
  });

  const pump = async () => {
    if (running.current || !alive.current) return;
    running.current = true;
    try {
      for (;;) {
        const entry = current.current.find((item) => item.status === "queued");
        if (!entry || entry.status !== "queued" || !alive.current) break;
        publish(current.current.map((item) => item.key === entry.key ? { ...entry, status: "uploading" } : item));
        try {
          const asset = await adminApi.uploadAsset(entry.file, "product");
          if (!alive.current) break;
          const image = fromAsset(asset);
          const error = validateGallery([...readyImages(current.current), image], detail);
          if (error) throw new Error(error);
          publish(current.current.map((item) => item.key === entry.key ? { key: entry.key, status: "ready", image } : item));
          void client.invalidateQueries({ queryKey: ["commerce-image-assets"] }, { throwOnError: true }).catch(() => {
            if (alive.current) setNotice("图片已上传，素材列表刷新失败，请重试查询");
          });
        } catch (error) {
          if (!alive.current) break;
          publish(current.current.map((item) => item.key === entry.key ? { ...entry, status: "error", error: errorMessage(error) } : item));
        }
      }
    } finally {
      running.current = false;
    }
  };

  const enqueue = (file: globalThis.File) => {
    if (current.current.length >= 20) { setNotice("每组最多 20 张，请先移除多余图片"); return Upload.LIST_IGNORE; }
    if (!/\.(jpe?g|png|webp)$/i.test(file.name)) { setNotice("只支持 JPEG、PNG、WebP 图片"); return Upload.LIST_IGNORE; }
    if (file.size > (detail ? 2 : 10) * 1024 * 1024) { setNotice(detail ? "详情单图不能超过 2 MiB" : "商品图片不能超过 10 MiB"); return Upload.LIST_IGNORE; }
    setNotice(undefined);
    serial.current += 1;
    publish([...current.current, { key: "upload:" + serial.current, status: "queued", file }]);
    void pump();
    return Upload.LIST_IGNORE;
  };

  const addAssets = (items: AssetRead[]) => {
    const images = items.map(fromAsset);
    if (current.current.length + images.length > 20) { setNotice("每组最多 20 张"); return; }
    const error = validateGallery([...readyImages(current.current), ...images], detail);
    if (error) { setNotice(error); return; }
    publish([...current.current, ...images.map((image): Entry => ({ key: "asset:" + image.asset_id, status: "ready", image }))]);
    setCandidates([]);
    setNotice(undefined);
  };
  const move = (key: string, destination: number) => {
    if (busy) return;
    const items = [...current.current];
    const index = items.findIndex((item) => item.key === key);
    const entry = items[index];
    if (!entry || destination < 0 || destination >= items.length) return;
    items.splice(index, 1);
    items.splice(destination, 0, entry);
    publish(items);
  };
  const eligible = (assets.data?.items ?? []).filter((asset) =>
    ["admin", "system"].includes(asset.uploader_type) && ["image/jpeg", "image/png", "image/webp"].includes(asset.mime_type));
  const candidateError = (ids: string[]) => {
    if (current.current.length + ids.length > 20) return "每组最多 20 张";
    return validateGallery([
      ...readyImages(current.current),
      ...eligible.filter((asset) => ids.includes(asset.id)).map(fromAsset),
    ], detail);
  };
  const selectable = eligible.filter((asset) => !candidateError([asset.id]));
  const updateCandidates = (ids: string[]) => {
    const error = candidateError(ids);
    if (error) {
      setNotice(error);
      return;
    }
    setCandidates(ids);
    setNotice(undefined);
  };
  const selectAllCandidates = () => {
    const ids: string[] = [];
    for (const asset of eligible) {
      if (!candidateError([...ids, asset.id])) ids.push(asset.id);
    }
    setCandidates(ids);
    setNotice(ids.length < selectable.length ? "本页素材无法同时加入，已选取符合整组预算的项目" : undefined);
  };
  const totalBytes = readyImages(entries).reduce((sum, image) => sum + image.file_size, 0);

  return <Space orientation="vertical" size="middle" style={{ width: "100%", minWidth: 0 }}>
    <Flex wrap gap={8} align="center">
      <Upload accept=".jpg,.jpeg,.png,.webp" multiple fileList={[]} beforeUpload={enqueue} disabled={entries.length >= 20 || busy}>
        <Button icon={<UploadOutlined />} loading={busy}>上传{label}</Button>
      </Upload>
      <Typography.Text type="secondary">{entries.length}/20 张 · {(totalBytes / 1024 / 1024).toFixed(2)} MiB</Typography.Text>
      <Button danger icon={<DeleteOutlined />} disabled={!selected.length || busy} onClick={() => setRemoval([...selected])}>移除所选</Button>
    </Flex>
    {detail && <Typography.Text type="secondary">静态详情图：单张 ≤ 2 MiB，整组 ≤ 20 MiB，单边 ≤ 4096 像素，每张 ≤ 800 万像素。</Typography.Text>}
    {notice && <Alert showIcon type="warning" title={notice} />}
    {entries.some((entry) => entry.status === "error") && <Alert showIcon type="error" title="部分图片未完成，请重试或移除失败项后保存" />}
    {!entries.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={"暂无" + label} /> : (
      <Image.PreviewGroup>
        {entries.map((entry, index) => <Flex key={entry.key} gap={12} wrap align="center"
          style={{ padding: token.paddingSM, border: token.lineWidth + "px solid " + token.colorBorderSecondary, borderRadius: token.borderRadius }}>
          <Checkbox aria-label={"选择" + label + "第" + (index + 1) + "张"} checked={selected.includes(entry.key)} disabled={busy}
            onChange={(event) => setSelected(event.target.checked ? [...selected, entry.key] : selected.filter((key) => key !== entry.key))} />
          <Tag>{!detail && index === 0 ? "主图" : index + 1}</Tag>
          {entry.status === "ready" && <Image src={entry.image.url} alt={entry.image.original_name} width={64} height={64} style={{ objectFit: "contain" }} />}
          <div style={{ flex: "1 1 180px", minWidth: 0, overflowWrap: "anywhere" }}>
            <Typography.Text>{entry.status === "ready" ? entry.image.original_name : entry.file.name}</Typography.Text>
            <div><Typography.Text type={entry.status === "error" ? "danger" : "secondary"}>
              {entry.status === "ready"
                ? ((entry.image.width && entry.image.height ? entry.image.width + " × " + entry.image.height : "尺寸待回填") + " · " + (entry.image.file_size / 1024).toFixed(0) + " KiB")
                : entry.status === "error" ? entry.error : entry.status === "queued" ? "等待上传" : "正在上传"}
            </Typography.Text></div>
          </div>
          <Space wrap size={4}>
            {entry.status === "error" && <Button icon={<ReloadOutlined />} disabled={busy} onClick={() => {
              publish(current.current.map((item) => item.key === entry.key ? { ...entry, status: "queued", error: undefined } : item));
              void pump();
            }}>重试</Button>}
            <Button icon={<ArrowUpOutlined />} aria-label={"上移" + label + "第" + (index + 1) + "张"} disabled={busy || index === 0} onClick={() => move(entry.key, index - 1)} />
            <Button icon={<ArrowDownOutlined />} aria-label={"下移" + label + "第" + (index + 1) + "张"} disabled={busy || index === entries.length - 1} onClick={() => move(entry.key, index + 1)} />
            <Button icon={<VerticalAlignTopOutlined />} aria-label={"置顶" + label + "第" + (index + 1) + "张"} disabled={busy || index === 0} onClick={() => move(entry.key, 0)} />
            <Button icon={<VerticalAlignBottomOutlined />} aria-label={"置底" + label + "第" + (index + 1) + "张"} disabled={busy || index === entries.length - 1} onClick={() => move(entry.key, entries.length - 1)} />
            <Button danger icon={<DeleteOutlined />} disabled={busy} onClick={() => setRemoval([entry.key])}>移除</Button>
          </Space>
        </Flex>)}
      </Image.PreviewGroup>
    )}
    {!allowed ? <Alert type="info" title="没有资产查询权限，可上传新图片；已绑定图片会保留。" /> : <>
      <Input.Search allowClear placeholder={"搜索已有" + label + "素材"} onSearch={(value) => { setSearch(value.trim()); setPage(1); setCandidates([]); }} />
      <QueryState loading={assets.isLoading} error={assets.error ? errorMessage(assets.error) : undefined} onRetry={() => void assets.refetch()} />
      {!assets.isLoading && !assets.isError && <>
        <Flex wrap gap={8} align="center">
          <Checkbox disabled={busy || !selectable.length} checked={selectable.length > 0 && selectable.every((asset) => candidates.includes(asset.id))}
            onChange={(event) => event.target.checked ? selectAllCandidates() : updateCandidates([])}>
            选择本页可用图片
          </Checkbox>
          <Button disabled={busy || !candidates.length} onClick={() => addAssets(eligible.filter((asset) => candidates.includes(asset.id)))}>加入所选图片</Button>
        </Flex>
        {!eligible.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可选图片" />}
        <Listy items={eligible} rowKey="id" styles={{ item: { padding: 0, border: 0, backgroundColor: "transparent" } }} itemRender={(asset) => {
          const selected = candidates.includes(asset.id);
          const reason = candidateError([...candidates.filter((id) => id !== asset.id), asset.id]);
          return <Flex key={asset.id} align="center" gap={8} style={{ minWidth: 0, paddingBlock: token.paddingXS }}>
            <Checkbox aria-label={"选择素材" + asset.original_name} checked={selected} disabled={busy || (!selected && Boolean(reason))}
              onChange={(event) => updateCandidates(event.target.checked ? [...candidates, asset.id] : candidates.filter((id) => id !== asset.id))} />
            <Image src={asset.url} alt={asset.original_name} width={40} height={40} style={{ objectFit: "contain" }} />
            <div style={{ minWidth: 0, flex: 1, overflowWrap: "anywhere" }}>{asset.original_name}
              {reason && <div><Typography.Text type="secondary">{reason}</Typography.Text></div>}
            </div>
          </Flex>;
        }} />
        <Pagination size="small" current={page} pageSize={20} total={assets.data?.total ?? 0} showSizeChanger={false}
          onChange={(value) => { setPage(value); setCandidates([]); }} />
      </>}
    </>}
    <StandardConfirmModal open={Boolean(removal)} title={"移除" + label} loading={false}
      description={"移除选中的 " + (removal?.length ?? 0) + " 项，保存商品后解除关联；已上传文件仍保留在资产库。取消会保留草稿。"}
      onCancel={() => setRemoval(undefined)} onConfirm={async () => {
        if (busy) throw new Error("上传进行中，请稍后操作");
        const keys = new Set(removal ?? []);
        publish(current.current.filter((entry) => !keys.has(entry.key)));
        setSelected(selected.filter((key) => !keys.has(key)));
        setRemoval(undefined);
        message.success("已从草稿移除，保存商品后生效");
      }} />
  </Space>;
}
