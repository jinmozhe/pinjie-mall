import type { ProductRead, SkuInput, SkuRead } from "@pinjie/api-client";
import { DeleteOutlined, EditOutlined, EyeOutlined, InboxOutlined, PlusOutlined, PoweroffOutlined, ReloadOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Drawer, Form, Input, InputNumber, Select, Space, Switch, Tag, message } from "antd";
import { useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { PageFrame, QueryState } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi, type ProductFilters } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";
import { ProductEditor } from "./ProductEditor";
import { InventoryPanel } from "./InventoryPanel";

const statuses = [{ value: "draft", label: "草稿" }, { value: "on_sale", label: "上架" }, { value: "off_sale", label: "下架" }];
const types = [{ value: "physical", label: "实物" }, { value: "virtual", label: "虚拟" }];
type SkuForm = Omit<SkuInput, "specifications"> & { specs: { name: string; value: string }[] };

function SkuEditor({ product, sku, close, done }: { product: ProductRead; sku: SkuRead | null; close: () => void; done: () => Promise<void> }) {
  const [form] = Form.useForm<SkuForm>();
  const [remove, setRemove] = useState<(() => void)>();
  return <EditorModal title={sku ? `编辑 SKU：${sku.code}` : "增加 SKU"} onClose={close} onSave={async () => {
    const values = await form.validateFields();
    const specs = values.specs ?? [];
    if (new Set(specs.map((item) => item.name.trim())).size !== specs.length) throw new Error("规格名称不能重复");
    await commerceApi.writeSku(product.id, { code: values.code, price: values.price, weight_grams: product.product_type === "virtual" ? 0 : values.weight_grams,
      is_active: values.is_active, specifications: Object.fromEntries(specs.map((item) => [item.name.trim(), item.value.trim()])), revision: product.revision }, sku?.id);
    message.success("SKU 已保存"); await done(); close();
  }}>
    <Form form={form} layout="vertical" initialValues={sku ? { ...sku, specs: Object.entries(sku.specifications ?? {}).map(([name, value]) => ({ name, value })) } : { code: "", price: "0.00", weight_grams: product.product_type === "virtual" ? 0 : 1, is_active: true, specs: [] }}>
      <Form.Item name="code" label="SKU 编码" rules={[{ required: true, pattern: /^[A-Za-z0-9_-]+$/, max: 100 }]}><Input maxLength={100} /></Form.Item>
      <Space wrap align="start">
        <Form.Item name="price" label="售价（元）" rules={[{ required: true }]}><InputNumber<string> stringMode min="0" precision={2} /></Form.Item>
        <Form.Item name="weight_grams" label="重量（克）" rules={[{ required: true }]}><InputNumber disabled={product.product_type === "virtual"} min={0} max={1000000000} precision={0} /></Form.Item>
        <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
      </Space>
      <Form.List name="specs">{(fields, actions) => <>
        {fields.map((field) => <Space wrap key={field.key} align="start">
          <Form.Item name={[field.name, "name"]} label="规格名称" rules={[{ required: true, whitespace: true, max: 50 }]}><Input placeholder="例如颜色" maxLength={50} /></Form.Item>
          <Form.Item name={[field.name, "value"]} label="规格值" rules={[{ required: true, whitespace: true, max: 100 }]}><Input placeholder="例如蓝色" maxLength={100} /></Form.Item>
          <Button danger icon={<DeleteOutlined />} onClick={() => setRemove(() => () => actions.remove(field.name))}>移除</Button>
        </Space>)}
        <Button icon={<PlusOutlined />} disabled={fields.length >= 10} onClick={() => actions.add({ name: "", value: "" })}>增加规格项</Button>
      </>}</Form.List>
    </Form>
    <StandardConfirmModal open={Boolean(remove)} title="移除规格项" description="从当前 SKU 草稿移除此规格项，保存后生效；SKU 标识保持不变。" loading={false} onCancel={() => setRemove(undefined)} onConfirm={async () => { remove?.(); setRemove(undefined); }} />
  </EditorModal>;
}

function ProductDetail({ id, close }: { id: string; close: () => void }) {
  const admin = useCurrentAdmin();
  const write = canAccess(admin, "products:update");
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["commerce-product", id], queryFn: () => commerceApi.product(id) });
  const [skuEdit, setSkuEdit] = useState<{ product: ProductRead; sku: SkuRead | null }>();
  const [inventory, setInventory] = useState<SkuRead>();
  const [selected, setSelected] = useState<SkuRead[]>([]);
  const [selectedRevision, setSelectedRevision] = useState<number>();
  const [edit, setEdit] = useState<ProductRead>();
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["commerce-product", id] }), client.invalidateQueries({ queryKey: ["commerce-products"] })]); };
  const batch = useLockedMutation({ mutationFn: (active: boolean) => {
    if (!selectedRevision) throw new Error("请先选择 SKU");
    return commerceApi.skusStatus(id, { sku_ids: selected.map((row) => row.id), revision: selectedRevision, is_active: active });
  }, onSuccess: async () => { setSelected([]); message.success("SKU 状态已更新"); await refresh(); }, onError: (error) => message.error(errorMessage(error)) });
  return <Drawer open width={1060} title="商品详情与 SKU" onClose={close}>
    <QueryState loading={query.isLoading} error={query.error ? errorMessage(query.error) : undefined} onRetry={() => void query.refetch()} />
    {query.data && <>
      <Descriptions column={{ xs: 1, sm: 2, md: 3 }} items={[
        { key: "name", label: "商品", children: query.data.name }, { key: "type", label: "类型", children: types.find((item) => item.value === query.data?.product_type)?.label },
        { key: "status", label: "状态", children: statuses.find((item) => item.value === query.data?.status)?.label },
        { key: "description", label: "说明", span: 3, children: query.data.description || "暂无说明" },
      ]} />
      <ResourceTable title="SKU" rows={query.data.skus} loading={false} retry={query.refetch}
        selection={write ? { keys: selected.map((row) => row.id), onChange: (_, rows) => { setSelected(rows); setSelectedRevision(query.data?.revision); }, disabled: batch.isPending } : undefined}
        toolbar={[
          write && <Space key="batch"><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending} onClick={() => batch.mutate(true)}>批量启用</Button><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending} onClick={() => batch.mutate(false)}>批量停用</Button></Space>,
          write && <Button key="edit" icon={<EditOutlined />} onClick={() => setEdit(query.data)}>编辑商品</Button>,
          write && <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => { if (query.data) setSkuEdit({ product: query.data, sku: null }); }}>增加 SKU</Button>,
        ]} columns={[
          { title: "编码", dataIndex: "code" }, { title: "规格", render: (_, row) => Object.entries(row.specifications ?? {}).map(([key, value]) => `${key}：${value}`).join(" / ") || "默认规格" },
          { title: "售价", render: (_, row) => `¥${row.price}` }, { title: "重量（克）", dataIndex: "weight_grams" },
          { title: "状态", render: (_, row) => row.is_active ? "启用" : "停用" },
          { title: "操作", width: "1%", render: (_, row) => <Space wrap={false}>
            {write && <Button icon={<EditOutlined />} disabled={batch.isPending} onClick={() => { if (query.data) setSkuEdit({ product: query.data, sku: row }); }}>编辑</Button>}
            {canAccess(admin, "inventory:read") && <Button icon={<InboxOutlined />} onClick={() => setInventory(row)}>库存与流水</Button>}
          </Space> },
        ]} />
    </>}
    {skuEdit && <SkuEditor product={skuEdit.product} sku={skuEdit.sku} close={() => setSkuEdit(undefined)} done={refresh} />}
    {inventory && <InventoryPanel sku={inventory} close={() => setInventory(undefined)} />}
    {edit && <ProductEditor target={edit} close={() => setEdit(undefined)} done={refresh} />}
  </Drawer>;
}

export function ProductsPage() {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const allowed = canAccess(admin, "products:read");
  const write = canAccess(admin, "products:update");
  const [filters, setFilters] = useState<ProductFilters>({ page: 1 });
  const [search, setSearch] = useState("");
  const [edit, setEdit] = useState<{ target: ProductRead | null }>();
  const [detail, setDetail] = useState<string>();
  const [selected, setSelected] = useState<ProductRead[]>([]);
  const query = useQuery({ queryKey: ["commerce-products", filters], queryFn: () => commerceApi.products(filters), enabled: allowed });
  const categories = useQuery({ queryKey: ["commerce-categories"], queryFn: commerceApi.categories, enabled: allowed && canAccess(admin, "product-categories:read") });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["commerce-products"] }); };
  const change = (patch: Partial<ProductFilters>) => { setSelected([]); setFilters((current) => ({ ...current, ...patch, page: patch.page ?? 1 })); };
  const batch = useLockedMutation({ mutationFn: (status: "on_sale" | "off_sale") => commerceApi.productsStatus({ targets: selected.map(({ id, revision }) => ({ id, revision })), status }),
    onSuccess: async () => { message.success("商品状态已更新"); setSelected([]); await refresh(); }, onError: (error) => message.error(errorMessage(error)) });
  const single = useLockedMutation({ mutationFn: ({ row, status }: { row: ProductRead; status: "on_sale" | "off_sale" }) => commerceApi.productStatus(row.id, { revision: row.revision, status }),
    onSuccess: async () => { message.success("商品状态已更新"); await refresh(); }, onError: (error) => message.error(errorMessage(error)) });
  return <PageFrame title="商品管理" description="管理商品资料、SKU 与库存，完成商品上架准备。">
    {!allowed ? <Alert type="warning" title="无权查看商品" /> : <>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search value={search} onChange={(event) => setSearch(event.target.value)} placeholder="商品名称 / SKU 编码" allowClear onSearch={() => change({ search: search.trim() || undefined })} style={{ width: 240 }} />
        <Select aria-label="商品状态" placeholder="全部状态" allowClear value={filters.status} options={statuses} style={{ width: 140 }} onChange={(status: ProductFilters["status"]) => change({ status })} />
        <Select aria-label="商品类型" placeholder="全部类型" allowClear value={filters.product_type} options={types} style={{ width: 140 }} onChange={(product_type: ProductFilters["product_type"]) => change({ product_type })} />
        <Select aria-label="商品分类" placeholder="全部分类" allowClear value={filters.category_id} options={(categories.data ?? []).map((row) => ({ value: row.id, label: row.name }))} style={{ width: 180 }} onChange={(category_id: string | undefined) => change({ category_id })} />
        <Button icon={<ReloadOutlined />} onClick={() => { setSearch(""); setSelected([]); setFilters({ page: 1 }); }}>重置</Button>
      </Space>
      <ResourceTable title="商品" rows={query.data?.items ?? []} loading={query.isLoading} fetching={query.isFetching} error={query.error} retry={query.refetch}
        page={filters.page} total={query.data?.total} onPage={(page) => change({ page })}
        selection={write ? { keys: selected.map((row) => row.id), onChange: (_, rows) => setSelected(rows), disabled: batch.isPending || single.isPending } : undefined}
        toolbar={[
          write && <Space key="batch"><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending || single.isPending} onClick={() => batch.mutate("on_sale")}>批量上架</Button><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending || single.isPending} onClick={() => batch.mutate("off_sale")}>批量下架</Button></Space>,
          canAccess(admin, "products:create") && <Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => setEdit({ target: null })}>新建商品</Button>,
        ]} columns={[
          { title: "名称", dataIndex: "name", ellipsis: true }, { title: "分类", render: (_, row) => categories.data?.find((item) => item.id === row.category_id)?.name ?? row.category_id },
          { title: "类型", render: (_, row) => types.find((item) => item.value === row.product_type)?.label },
          { title: "状态", render: (_, row) => <Tag color={row.status === "on_sale" ? "success" : "default"}>{statuses.find((item) => item.value === row.status)?.label}</Tag> },
          { title: "SKU 数", render: (_, row) => row.skus.length },
          { title: "操作", width: "1%", render: (_, row) => <Space wrap={false}>
            <Button icon={<EyeOutlined />} onClick={() => setDetail(row.id)}>详情</Button>
            {write && <><Button icon={<EditOutlined />} disabled={batch.isPending || single.isPending} onClick={() => setEdit({ target: row })}>编辑</Button>
              <Button icon={<PoweroffOutlined />} disabled={batch.isPending || single.isPending} onClick={() => single.mutate({ row, status: row.status === "on_sale" ? "off_sale" : "on_sale" })}>{row.status === "on_sale" ? "下架" : "上架"}</Button></>}
          </Space> },
        ]} />
    </>}
    {edit && <ProductEditor target={edit.target} close={() => setEdit(undefined)} done={refresh} />}
    {detail && <ProductDetail id={detail} close={() => setDetail(undefined)} />}
  </PageFrame>;
}

export default ProductsPage;
