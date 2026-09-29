import type {
  CategoryRead,
  ProductCreate,
  ProductDetailRead,
  ProductImageRead,
  ProductUpdate,
} from "@pinjie/api-client";
import {
  ArrowLeftOutlined,
  FileImageOutlined,
  InfoCircleOutlined,
  MobileOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Radio,
  Select,
  Skeleton,
  Space,
  Tabs,
  Typography,
} from "antd";
import { useRef, useState } from "react";
import { history, useParams } from "@umijs/max";

import { RichTextEditor } from "@/components/RichTextEditor";
import { QueryState } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { PageContainer } from "@ant-design/pro-components";
import { ProductImageGallery, type GalleryState } from "./ProductImageGallery";
import { ProductDetailPreview } from "./ProductDetailPreview";
import { validateGallery } from "./product-image-policy";
import {
  ProductSpecificationForm,
  type ProductSpecificationFormHandle,
} from "./ProductSpecificationForm";

// ─── 新建商品页 ───────────────────────────────────────────────────────────────
export function ProductCreatePage() {
  return <ProductEditorPageInner target={null} />;
}

// ─── 编辑商品页 ───────────────────────────────────────────────────────────────
export function ProductEditPage() {
  const { id } = useParams<{ id: string }>();

  const detail = useQuery({
    queryKey: ["commerce-product-edit", id],
    queryFn: () => {
      if (!id) throw new Error("缺少商品标识");
      return commerceApi.product(id);
    },
    enabled: Boolean(id),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  // 等待首次加载完成后固定快照，防止后台刷新重置表单
  const snapshot = useRef<ProductDetailRead | null>(null);
  if (
    id &&
    !snapshot.current &&
    detail.isFetchedAfterMount &&
    detail.isSuccess &&
    !detail.isFetching
  ) {
    snapshot.current = detail.data;
  }

  if (detail.isLoading || (id && !snapshot.current)) {
    return (
      <PageContainer title="加载商品中">
        <Card>
          {detail.isError ? (
            <Alert
              showIcon
              type="error"
              title={errorMessage(detail.error)}
              action={
                <Button onClick={() => void detail.refetch()}>重试</Button>
              }
            />
          ) : (
            <Skeleton active paragraph={{ rows: 10 }} />
          )}
        </Card>
      </PageContainer>
    );
  }

  return (
    <ProductEditorPageInner
      key={id}
      target={id ? snapshot.current : null}
    />
  );
}

// ─── 核心编辑器页面（新建 target=null，编辑 target=ProductDetailRead） ────────
function ProductEditorPageInner({
  target,
}: {
  target: ProductDetailRead | null;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const isEdit = Boolean(target);

  // 监听分类 ID，用于规格模板加载
  const selectedCategoryId = Form.useWatch("category_id", form);
  // 监听文字说明，用于详情预览
  const description = Form.useWatch<string>("description", form) ?? "";

  // 图片状态
  const [images, setImages] = useState<ProductImageRead[]>(
    target?.image_assets ?? [],
  );
  const [details, setDetails] = useState<ProductImageRead[]>(
    target?.detail_images ?? [],
  );
  const galleryStates = useRef<Record<"main" | "detail", GalleryState>>({
    main: { uploading: false, unresolved: false },
    detail: { uploading: false, unresolved: false },
  });
  const uploadingRef = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  // 规格表单句柄（仅新建时使用）
  const [activeTab, setActiveTab] = useState("basic");
  const specificationFormRef = useRef<ProductSpecificationFormHandle>(null);

  // 分类列表
  const categoriesQuery = useQuery({
    queryKey: ["commerce-categories-options"],
    queryFn: commerceApi.categories,
  });
  const categoryOptions = (categoriesQuery.data ?? []).map(
    (cat: CategoryRead) => ({ label: cat.name, value: cat.id }),
  );

  const reportGallery = (key: "main" | "detail", state: GalleryState) => {
    galleryStates.current[key] = state;
    uploadingRef.current = Object.values(galleryStates.current).some(
      (s) => s.uploading,
    );
    setUploading(uploadingRef.current);
  };

  const goBack = () => {
    history.push("/catalog/products");
  };

  const handleSave = async () => {
    if (
      uploadingRef.current ||
      Object.values(galleryStates.current).some((s) => s.unresolved)
    ) {
      message.error("请完成图片上传或处理失败项后保存");
      setActiveTab("images");
      return;
    }
    const imageError =
      validateGallery(details, true) ?? validateGallery(images, false);
    if (imageError) {
      message.error(imageError);
      setActiveTab("images");
      return;
    }

    setSaving(true);
    try {
      let values;
      try {
        values = await form.validateFields();
      } catch (validationErr: unknown) {
        if (
          validationErr &&
          typeof validationErr === "object" &&
          "errorFields" in validationErr
        ) {
          const formErr = validationErr as {
            errorFields?: Array<{
              name: (string | number)[];
              errors?: string[];
            }>;
          };
          const firstField = formErr.errorFields?.[0];
          const firstMsg = firstField?.errors?.[0];
          if (firstMsg) message.error(firstMsg);
          const topFieldName = firstField?.name?.[0];
          if (
            topFieldName === "name" ||
            topFieldName === "category_id" ||
            topFieldName === "product_type" ||
            topFieldName === "description"
          ) {
            setActiveTab("basic");
          } else {
            setActiveTab("specifications");
          }
        }
        return;
      }

      if (isEdit && target) {
        // 编辑模式：只更新基本信息与图片
        const updatePayload: ProductUpdate = {
          name: values.name.trim(),
          category_id: values.category_id,
          product_type: target.product_type,
          brand_id: target.brand_id,
          purchase_limit_quantity: target.purchase_limit_quantity,
          description: values.description?.trim() || "",
          image_asset_ids: images.map((img) => img.asset_id),
          detail_image_asset_ids: details.map((img) => img.asset_id),
          revision: target.revision,
        };
        await commerceApi.updateProduct(target.id, updatePayload);
        message.success("商品信息已更新");
      } else {
        // 新建模式：需要包含规格与 SKU
        if (categoriesQuery.isError)
          throw new Error("商品分类加载失败，请恢复后再保存");
        let specification;
        try {
          specification = await specificationFormRef.current?.validate();
        } catch (specErr: unknown) {
          setActiveTab("specifications");
          throw specErr;
        }
        if (!specification) throw new Error("请选择商品分类后加载规格模板");
        const payload: ProductCreate = {
          name: values.name.trim(),
          category_id: values.category_id,
          category_revision: specification.categoryRevision,
          product_type: values.product_type,
          description: values.description?.trim() || "",
          image_asset_ids: images.map((img) => img.asset_id),
          detail_image_asset_ids: details.map((img) => img.asset_id),
          attributes: specification.attributes,
          skus: specification.skus,
        };
        await commerceApi.createProduct(payload);
        message.success("商品已成功创建");
      }
      goBack();
    } catch (error: unknown) {
      message.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  // ─── 各 Tab 内容 ─────────────────────────────────────────────────────────
  /** Tab 1：基本信息 */
  const basicInfoTab = (
    <div style={{ maxWidth: 720, paddingTop: 8 }}>
      <QueryState
        loading={categoriesQuery.isLoading}
        error={categoriesQuery.error?.message}
        onRetry={() => void categoriesQuery.refetch()}
      />
      <Form.Item
        name="name"
        label="商品名称"
        rules={[{ required: true, whitespace: true, max: 200 }]}
      >
        <Input maxLength={200} placeholder="例如：品界特级有机绿茶 250g" />
      </Form.Item>

      <Space size="middle" wrap>
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

        {!isEdit && (
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
        <RichTextEditor
          placeholder="商品简要说明（选填）"
          minHeight={160}
        />
      </Form.Item>
    </div>
  );

  /** Tab 2：规格属性 & SKU（仅新建时显示；编辑时引导至「规格维护」） */
  const specificationsTab = isEdit ? (
    <Alert
      showIcon
      type="info"
      title="编辑模式下规格与 SKU 通过「规格维护」单独管理"
      description="请回到商品列表，点击对应商品的「规格维护」按钮进行操作。规格维护支持追加候选值、转换规格模板及单独更新描述属性。"
    />
  ) : (
    <div style={{ paddingTop: 8 }}>
      <ProductSpecificationForm
        ref={specificationFormRef}
        categoryId={selectedCategoryId}
        mode="create"
      />
    </div>
  );

  /** Tab 3：主图与图集 */
  const imagesTab = (
    <Tabs
      defaultActiveKey="main"
      items={[
        {
          key: "main",
          label: "主图与轮播图",
          forceRender: true,
          children: (
            <ProductImageGallery
              initialImages={target?.image_assets ?? []}
              onChange={setImages}
              onStateChange={(state) => reportGallery("main", state)}
            />
          ),
        },
        {
          key: "detail",
          label: "商品详情图集",
          forceRender: true,
          children: (
            <ProductImageGallery
              detail
              initialImages={target?.detail_images ?? []}
              onChange={setDetails}
              onStateChange={(state) => reportGallery("detail", state)}
            />
          ),
        },
      ]}
    />
  );

  /** Tab 4：详情预览 */
  const previewTab = (
    <ProductDetailPreview description={description} images={details} />
  );

  // ─── 左侧垂直 Tab 配置 ────────────────────────────────────────────────────
  const tabItems = [
    {
      key: "basic",
      label: (
        <span>
          <InfoCircleOutlined /> 基本信息
        </span>
      ),
      forceRender: true,
      children: <div style={{ paddingLeft: 20 }}>{basicInfoTab}</div>,
    },
    {
      key: "specifications",
      label: (
        <span>
          <TagsOutlined /> 规格属性 &amp; SKU
        </span>
      ),
      forceRender: true,
      children: <div style={{ paddingLeft: 20 }}>{specificationsTab}</div>,
    },
    {
      key: "images",
      label: (
        <span>
          <FileImageOutlined /> 主图与图集
        </span>
      ),
      forceRender: true,
      children: <div style={{ paddingLeft: 20 }}>{imagesTab}</div>,
    },
    {
      key: "preview",
      label: (
        <span>
          <MobileOutlined /> 详情预览
        </span>
      ),
      children: <div style={{ paddingLeft: 20 }}>{previewTab}</div>,
    },
  ];

  const pageTitle = isEdit
    ? `编辑商品：${target?.name ?? ""}`
    : "新建商品";

  return (
    <PageContainer
      className="workspace-page"
      title={
        <Space align="center">
          <Button
            icon={<ArrowLeftOutlined />}
            type="text"
            onClick={goBack}
            aria-label="返回商品列表"
          />
          <Typography.Title
            id="page-heading"
            className="page-title"
            level={1}
            style={{ margin: 0 }}
          >
            {pageTitle}
          </Typography.Title>
        </Space>
      }
      content={
        isEdit
          ? "修改商品基本信息与图片；规格与 SKU 请通过列表页「规格维护」操作。"
          : "填写商品信息、规格属性与 SKU 定价，完成后保存创建。"
      }
      extra={
        <Space>
          <Button onClick={goBack} disabled={saving}>
            取消
          </Button>
          <Button
            type="primary"
            loading={saving}
            disabled={uploading}
            onClick={() => void handleSave()}
          >
            {uploading ? "图片上传中…" : isEdit ? "保存修改" : "创建商品"}
          </Button>
        </Space>
      }
    >
      <Card className="workspace-panel" variant="borderless">
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
          {/* 左侧垂直 Tabs + 右侧内容区 */}
          <Tabs
            tabPosition="left"
            activeKey={activeTab}
            onChange={setActiveTab}
            style={{ minHeight: 520 }}
            items={tabItems}
          />
        </Form>
      </Card>
    </PageContainer>
  );
}

export default ProductCreatePage;
