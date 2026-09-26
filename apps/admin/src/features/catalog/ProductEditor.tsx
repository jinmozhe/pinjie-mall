import type { CategoryRead, ProductCreate, ProductRead, ProductDetailRead, ProductImageRead, ProductUpdate } from "@pinjie/api-client";
import { useQuery } from "@tanstack/react-query";
import { Form, Input, Radio, Select, Space, App, Modal, Tabs } from "antd";
import { useRef, useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { QueryState } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";
import { ProductImageGallery, type GalleryState } from "./ProductImageGallery";
import { ProductDetailPreview } from "./ProductDetailPreview";
import { validateGallery } from "./product-image-policy";
import { errorMessage } from "@/lib/api/http";
import { ProductSpecificationForm, type ProductSpecificationFormHandle } from "./ProductSpecificationForm";

export function ProductEditor({ target, close, done }: {
  target: ProductRead | null; close: () => void; done: () => Promise<void>;
}) {
  const detail = useQuery({
    queryKey: ["commerce-product-edit", target?.id],
    queryFn: () => { if (!target) throw new Error("缺少商品标识"); return commerceApi.product(target.id); },
    enabled: Boolean(target),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const snapshot = useRef<ProductDetailRead | null>(null);
  if (target && !snapshot.current && detail.isFetchedAfterMount && detail.isSuccess && !detail.isFetching) {
    snapshot.current = detail.data;
  }
  if (target && !snapshot.current) return <Modal open title="加载商品详情" footer={null} onCancel={close}>
    <QueryState loading={detail.isFetching} error={detail.error ? errorMessage(detail.error) : undefined} onRetry={() => void detail.refetch()} />
  </Modal>;
  return <ProductEditorForm key={target?.id ?? "new"} target={target ? snapshot.current : null} close={close} done={done} />;
}

function ProductEditorForm({
  target,
  close,
  done,
}: {
  target: ProductDetailRead | null;
  close: () => void;
  done: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const selectedCategoryId = Form.useWatch("category_id", form);
  const [images, setImages] = useState<ProductImageRead[]>(target?.image_assets ?? []);
  const [details, setDetails] = useState<ProductImageRead[]>(target?.detail_images ?? []);
  const galleryStates = useRef<Record<"main" | "detail", GalleryState>>({ main: { uploading: false, unresolved: false }, detail: { uploading: false, unresolved: false } });
  const description = Form.useWatch<string>("description", form) ?? "";
  const uploadingRef = useRef(false);
  const specificationFormRef = useRef<ProductSpecificationFormHandle>(null);
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
    if (uploadingRef.current || Object.values(galleryStates.current).some((state) => state.unresolved)) throw new Error("请完成图片上传或处理失败项后保存");
    const imageError = validateGallery(details, true) ?? validateGallery(images, false);
    if (imageError) throw new Error(imageError);
    const values = await form.validateFields();
    if (target) {
      const updatePayload: ProductUpdate = {
        name: values.name.trim(),
        category_id: values.category_id,
        product_type: target.product_type,
        brand_id: target.brand_id,
        purchase_limit_quantity: target.purchase_limit_quantity,
        description: values.description?.trim() || "",
        image_asset_ids: images.map((image) => image.asset_id),
        detail_image_asset_ids: details.map((image) => image.asset_id),
        revision: target.revision,
      };
      await commerceApi.updateProduct(target.id, updatePayload);
      message.success("商品信息已更新");
    } else {
      if (categoriesQuery.isError) throw new Error("商品分类加载失败，请恢复后再保存");
      const specification = await specificationFormRef.current?.validate();
      if (!specification) throw new Error("请选择商品分类后加载规格模板");
      const payload: ProductCreate = {
        name: values.name.trim(),
        category_id: values.category_id,
        category_revision: specification.categoryRevision,
        product_type: values.product_type,
        description: values.description?.trim() || "",
        image_asset_ids: images.map((image) => image.asset_id),
        detail_image_asset_ids: details.map((image) => image.asset_id),
        attributes: specification.attributes,
        skus: specification.skus,
      };
      await commerceApi.createProduct(payload);
      message.success("商品已成功创建");
    }
    try { await done(); }
    catch (error) { message.warning("商品已保存，列表刷新失败：" + errorMessage(error)); }
    close();
  };

  const reportGallery = (key: "main" | "detail", state: GalleryState) => {
    galleryStates.current[key] = state;
    uploadingRef.current = Object.values(galleryStates.current).some((value) => value.uploading);
    setUploading(uploadingRef.current);
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
        requiredMark="optional"
        initialValues={
          target
            ? {
                name: target.name,
                category_id: target.category_id,
                description: target.description,
              }
            : {
                product_type: "physical",
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

        <Space size="medium" wrap style={{ width: "100%" }}>
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

        <Form.Item name="description" label="商品文字说明">
          <Input.TextArea rows={3} maxLength={20000} placeholder="商品简要说明（选填）" />
        </Form.Item>

        <Tabs items={[
          { key: "main", label: "主图与轮播图", forceRender: true, children: <ProductImageGallery initialImages={target?.image_assets ?? []} onChange={setImages} onStateChange={(state) => reportGallery("main", state)} /> },
          { key: "detail", label: "商品详情图集", forceRender: true, children: <ProductImageGallery detail initialImages={target?.detail_images ?? []} onChange={setDetails} onStateChange={(state) => reportGallery("detail", state)} /> },
          { key: "preview", label: "手机宽度预览", children: <ProductDetailPreview description={description} images={details} /> },
        ]} />

        {!target && <ProductSpecificationForm ref={specificationFormRef} categoryId={selectedCategoryId} mode="create" />}
      </Form>
    </EditorModal>
  );
}

export default ProductEditor;
