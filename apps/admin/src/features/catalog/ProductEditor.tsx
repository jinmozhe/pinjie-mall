import type { ProductCreate, ProductRead, ShippingTemplateRead } from "@pinjie/api-client";
import { useQuery } from "@tanstack/react-query";
import { Alert, Form, Input, InputNumber, Pagination, Select, Space, message } from "antd";
import { useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { QueryState } from "@/components/PageFrame";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { ProductImages } from "./ProductImages";

export function ProductEditor({ target, close, done }: { target: ProductRead | null; close: () => void; done: () => Promise<void> }) {
  const admin = useCurrentAdmin();
  const [form] = Form.useForm<ProductCreate>();
  const [shippingPage, setShippingPage] = useState(1);
  const [uploading, setUploading] = useState(false);
  const productType = Form.useWatch("product_type", form);
  const categories = useQuery({ queryKey: ["commerce-categories"], queryFn: commerceApi.categories, enabled: canAccess(admin, "product-categories:read") });
  const shipping = useQuery({ queryKey: ["commerce-shipping", shippingPage], queryFn: () => commerceApi.shipping(shippingPage), enabled: canAccess(admin, "shipping:read") });
  const chosenTemplate = useQuery({ queryKey: ["commerce-shipping-detail", target?.shipping_template_id],
    enabled: Boolean(target?.shipping_template_id) && canAccess(admin, "shipping:read"),
    queryFn: () => { if (!target?.shipping_template_id) throw new Error("未选择运费模板"); return commerceApi.shippingDetail(target.shipping_template_id); } });
  const templates: ShippingTemplateRead[] = [...(shipping.data?.items ?? [])];
  if (chosenTemplate.data && !templates.some((row) => row.id === chosenTemplate.data?.id)) templates.push(chosenTemplate.data);
  return <EditorModal title={target ? "编辑商品资料" : "新建商品"} width={820} onClose={close} onSave={async () => {
    if (uploading) throw new Error("请等待商品图片上传完成后保存");
    const values = await form.validateFields();
    const common = { name: values.name.trim(), description: values.description ?? "", product_type: values.product_type,
      category_id: values.category_id, shipping_template_id: values.product_type === "virtual" ? null : values.shipping_template_id ?? null,
      image_asset_ids: values.image_asset_ids ?? [] };
    if (target) await commerceApi.updateProduct(target.id, { ...common, revision: target.revision });
    else await commerceApi.createProduct({ ...common, skus: values.skus.map((sku) => ({ ...sku, specifications: {}, weight_grams: values.product_type === "virtual" ? 0 : sku.weight_grams })) });
    message.success("商品已保存"); await done(); close();
  }}>
    <Form form={form} layout="vertical" initialValues={target ?? { product_type: "physical", description: "", image_asset_ids: [], skus: [{ code: "", specifications: {}, price: "0.00", weight_grams: 1, is_active: true }] }}>
      <Form.Item name="name" label="商品名称" rules={[{ required: true, whitespace: true, max: 200 }]}><Input maxLength={200} /></Form.Item>
      <Space wrap align="start">
        <Form.Item name="product_type" label="商品类型" rules={[{ required: true }]}><Select disabled={Boolean(target)} style={{ width: 180 }} options={[{ value: "physical", label: "实物商品" }, { value: "virtual", label: "虚拟商品" }]} /></Form.Item>
        <Form.Item name="category_id" label="所属分类" rules={[{ required: true }]}><Select style={{ width: 220 }} showSearch optionFilterProp="label" options={(categories.data ?? []).map((row) => ({ value: row.id, label: `${row.name}${row.is_active ? "" : "（停用）"}`, disabled: !row.is_active }))} /></Form.Item>
      </Space>
      {categories.error && <Alert type="error" title={errorMessage(categories.error)} />}
      {!canAccess(admin, "product-categories:read") && <Alert type="warning" title="新建商品需要商品分类查看权限，请联系管理员分配。" />}
      {productType === "physical" && <>
        <Form.Item name="shipping_template_id" label="运费模板"><Select allowClear options={templates.map((row) => ({ value: row.id, label: `${row.name}${row.is_active ? "" : "（停用）"}`, disabled: !row.is_active }))} /></Form.Item>
        <QueryState loading={shipping.isLoading} error={shipping.error ? errorMessage(shipping.error) : undefined} onRetry={() => void shipping.refetch()} />
        <Pagination size="small" current={shippingPage} total={shipping.data?.total} pageSize={20} showSizeChanger={false} onChange={setShippingPage} />
      </>}
      <Form.Item name="description" label="商品说明"><Input.TextArea rows={4} maxLength={20000} showCount /></Form.Item>
      <Form.Item name="image_asset_ids" label="商品图片，首张为主图"><ProductImages onUploading={setUploading} /></Form.Item>
      {!target && <>
        <Alert type="info" title="先创建默认 SKU；保存后在商品详情中编辑规格或增加其他 SKU。" />
        <Space wrap align="start">
          <Form.Item name={["skus", 0, "code"]} label="SKU 编码" rules={[{ required: true, pattern: /^[A-Za-z0-9_-]+$/, max: 100 }]}><Input maxLength={100} /></Form.Item>
          <Form.Item name={["skus", 0, "price"]} label="售价（元）" rules={[{ required: true }]}><InputNumber<string> stringMode min="0" precision={2} /></Form.Item>
          {productType === "physical" && <Form.Item name={["skus", 0, "weight_grams"]} label="重量（克）" rules={[{ required: true }]}><InputNumber min={1} max={1000000000} precision={0} /></Form.Item>}
        </Space>
      </>}
    </Form>
  </EditorModal>;
}
