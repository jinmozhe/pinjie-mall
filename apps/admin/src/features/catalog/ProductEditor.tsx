import type { CategoryRead, ProductCreate, ProductRead, ProductUpdate } from "@pinjie/api-client";
import { useQuery } from "@tanstack/react-query";
import { Alert, Divider, Form, Input, InputNumber, Radio, Select, Space, message } from "antd";
import { useRef, useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { QueryState } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";
import { ProductImages } from "./ProductImages";

export function ProductEditor({
  target,
  close,
  done,
}: {
  target: ProductRead | null;
  close: () => void;
  done: () => Promise<void>;
}) {
  const [form] = Form.useForm();
  const [images, setImages] = useState<string[]>(target?.image_asset_ids ?? []);
  const uploadingRef = useRef(false);
  const [uploading, setUploading] = useState(false);

  const categoriesQuery = useQuery({
    queryKey: ["commerce-categories-options"],
    queryFn: commerceApi.categories,
  });

  const categoryOptions = (categoriesQuery.data ?? []).map((cat: CategoryRead) => ({
    label: cat.name,
    value: cat.id,
  }));

  const onSave = async () => {
    if (uploadingRef.current) throw new Error("商品图片正在上传，请完成后再保存");
    const values = await form.validateFields();
    if (target) {
      const updatePayload: ProductUpdate = {
        name: values.name.trim(),
        category_id: values.category_id,
        product_type: target.product_type,
        brand_id: target.brand_id,
        purchase_limit_quantity: target.purchase_limit_quantity,
        description: values.description?.trim() || "",
        image_asset_ids: images,
        revision: target.revision,
      };
      await commerceApi.updateProduct(target.id, updatePayload);
      message.success("商品信息已更新");
    } else {
      const selectedCategory = categoriesQuery.data?.find((c) => c.id === values.category_id);
      if (!selectedCategory || categoriesQuery.isError) throw new Error("请成功加载并选择商品分类后保存");
      const payload: ProductCreate = {
        name: values.name.trim(),
        category_id: values.category_id,
        category_revision: selectedCategory.revision,
        product_type: values.product_type,
        description: values.description?.trim() || "",
        image_asset_ids: images,
        attributes: [],
        skus: [
          {
            code: values.sku_code.trim(),
            price: String(values.sku_price),
            market_price: values.sku_origin_price != null ? String(values.sku_origin_price) : null,
            initial_quantity: Number(values.initial_quantity || 0),
            is_active: true,
            selections: {},
          },
        ],
      };
      await commerceApi.createProduct(payload);
      message.success("商品已成功创建");
    }
    await done();
    close();
  };

  return (
    <EditorModal
      title={target ? `编辑商品：${target.name}` : "新建商品"}
      width={720}
      blocked={uploading}
      onClose={() => { if (!uploadingRef.current) close(); }}
      onSave={onSave}
    >
      <QueryState loading={categoriesQuery.isLoading} error={categoriesQuery.error?.message} onRetry={() => void categoriesQuery.refetch()} />
      <Form
        form={form}
        layout="vertical"
        initialValues={
          target
            ? {
                name: target.name,
                category_id: target.category_id,
                description: target.description,
              }
            : {
                product_type: "physical",
                initial_quantity: 100,
                sku_price: 99.0,
              }
        }
      >
        <Form.Item
          name="name"
          label="商品名称"
          rules={[{ required: true, whitespace: true, max: 200 }]}
        >
          <Input maxLength={200} placeholder="例如：品界特级有机绿茶 250g" />
        </Form.Item>

        <Space size="middle" style={{ width: "100%" }}>
          <Form.Item
            name="category_id"
            label="所属分类"
            rules={[{ required: true, message: "请选择商品分类" }]}
            style={{ width: 320 }}
          >
            <Select
              placeholder="选择商品分类"
              options={categoryOptions}
              loading={categoriesQuery.isLoading}
            />
          </Form.Item>

          {!target && (
            <Form.Item
              name="product_type"
              label="商品类型"
              rules={[{ required: true }]}
            >
              <Radio.Group>
                <Radio value="physical">实物商品 (需发货)</Radio>
                <Radio value="virtual">虚拟服务 (自动交付)</Radio>
              </Radio.Group>
            </Form.Item>
          )}
        </Space>

        <Form.Item name="description" label="商品描述">
          <Input.TextArea rows={3} maxLength={20000} placeholder="商品简要说明（选填）" />
        </Form.Item>

        <Form.Item label="商品主图与轮播图">
          <ProductImages
            value={images}
            onChange={setImages}
            onUploading={(value) => { uploadingRef.current = value; setUploading(value); }}
          />
        </Form.Item>

        {!target && (
          <>
            <Divider>初始货品规格 (SKU)</Divider>
            <Alert
              type="info"
              title="新建商品时创建首个标准货品，后续可在商品列表中新增变体或进行多规格转换。"
              className="mb-16"
            />
            <Space size="middle" style={{ width: "100%" }}>
              <Form.Item
                name="sku_code"
                label="SKU 编码"
                rules={[{ required: true, whitespace: true, max: 64 }]}
                style={{ width: 220 }}
              >
                <Input maxLength={64} placeholder="例如：TEA-GRN-250G" />
              </Form.Item>

              <Form.Item
                name="sku_price"
                label="售卖价格 (元)"
                rules={[{ required: true }]}
                style={{ width: 140 }}
              >
                <InputNumber min={0} precision={2} stringMode style={{ width: "100%" }} />
              </Form.Item>

              <Form.Item
                name="sku_origin_price"
                label="划线原价 (元)"
                style={{ width: 140 }}
              >
                <InputNumber min={0} precision={2} stringMode style={{ width: "100%" }} />
              </Form.Item>

              <Form.Item
                name="initial_quantity"
                label="初始库存量"
                rules={[{ required: true }]}
                style={{ width: 120 }}
              >
                <InputNumber min={0} max={1000000} precision={0} style={{ width: "100%" }} />
              </Form.Item>
            </Space>
          </>
        )}
      </Form>
    </EditorModal>
  );
}

export default ProductEditor;
