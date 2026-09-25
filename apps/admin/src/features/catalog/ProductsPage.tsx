import type { ProductRead, SkuRead } from "@pinjie/api-client";
import {
  CheckCircleOutlined,
  EditOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  SearchOutlined,
  TagsOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Select,
  Space,
  Table,
  Tag,
  App,
} from "antd";
import { useState } from "react";
import type { ColumnsType } from "antd/es/table";

import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";
import { InventoryPanel } from "./InventoryPanel";
import { ProductEditor } from "./ProductEditor";
import { ProductSpecificationsPanel } from "./ProductSpecificationsPanel";

export function ProductsPage() {
  const { message } = App.useApp();
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ProductRead["status"]>();
  const [typeFilter, setTypeFilter] = useState<ProductRead["product_type"]>();
  const [selected, setSelected] = useState<ProductRead[]>([]);
  const [editingProduct, setEditingProduct] = useState<ProductRead | null | undefined>(undefined);
  const [inspectProduct, setInspectProduct] = useState<ProductRead | null>(null);
  const [inventorySku, setInventorySku] = useState<SkuRead | null>(null);
  const [specificationProductId, setSpecificationProductId] = useState<string>();

  const allowed = canAccess(admin, "products:read");
  const canCreate = canAccess(admin, "products:create");
  const canUpdate = canAccess(admin, "products:update");

  const query = useQuery({
    queryKey: ["commerce-products", page, search, statusFilter, typeFilter],
    queryFn: () =>
      commerceApi.products({
        page,
        search: search || undefined,
        status: statusFilter,
        product_type: typeFilter,
      }),
    enabled: allowed,
  });

  const categoriesQuery = useQuery({
    queryKey: ["commerce-categories-map"],
    queryFn: commerceApi.categories,
    enabled: allowed && canAccess(admin, "product-categories:read"),
  });

  const categoryMap = new Map((categoriesQuery.data ?? []).map((cat) => [cat.id, cat.name]));

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["commerce-products"] });
  };

  const batchStatusMutation = useLockedMutation({
    mutationFn: (targetStatus: "on_sale" | "off_sale") =>
      commerceApi.productsStatus({
        targets: selected.map(({ id, revision }) => ({ id, revision })),
        status: targetStatus,
      }),
    onSuccess: async () => {
      message.success("批量状态已更新");
      setSelected([]);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const singleStatus = useLockedMutation({
    mutationFn: ({ product, status }: { product: ProductRead; status: "on_sale" | "off_sale" }) =>
      commerceApi.productStatus(product.id, { status, revision: product.revision }),
    onSuccess: async () => {
      message.success("商品状态已更新");
      setSelected([]);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  return (
    <PageFrame
      title="商品管理"
      description="管理商品资料、分类归属、稳定 SKU 变体与销售上下架状态。"
    >
      {!allowed ? (
        <Alert type="warning" title="无权查看商品管理" />
      ) : (
        <Space orientation="vertical" size="large" style={{ width: "100%" }}>
          <Card size="small">
            <Form
              layout="inline"
              disabled={batchStatusMutation.isPending || singleStatus.isPending}
              onFinish={(values: {
                search?: string;
                status?: ProductRead["status"];
                product_type?: ProductRead["product_type"];
              }) => {
                setSearch(values.search?.trim() || "");
                setStatusFilter(values.status || undefined);
                setTypeFilter(values.product_type || undefined);
                setPage(1);
                setSelected([]);
              }}
            >
              <Form.Item name="search">
                <Input
                  placeholder="搜索商品名称或 SKU 编码"
                  allowClear
                  style={{ width: 240 }}
                  prefix={<SearchOutlined />}
                />
              </Form.Item>
              <Form.Item name="status" initialValue="">
                <Select
                  style={{ width: 140 }}
                  options={[
                    { label: "全部状态", value: "" },
                    { label: "在售中 (on_sale)", value: "on_sale" },
                    { label: "已下架 (off_sale)", value: "off_sale" },
                    { label: "草稿中 (draft)", value: "draft" },
                  ]}
                />
              </Form.Item>
              <Form.Item name="product_type" initialValue="">
                <Select
                  style={{ width: 140 }}
                  options={[
                    { label: "全部类型", value: "" },
                    { label: "实物商品 (physical)", value: "physical" },
                    { label: "虚拟商品 (virtual)", value: "virtual" },
                  ]}
                />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit">
                  查询
                </Button>
              </Form.Item>
            </Form>
          </Card>

          {categoriesQuery.error && <Alert type="error" title="商品分类加载失败" description={categoriesQuery.error.message} action={<Button onClick={() => void categoriesQuery.refetch()}>重试</Button>} />}
          <ResourceTable
            title="商品列表"
            rows={query.data?.items ?? []}
            loading={query.isLoading}
            fetching={query.isFetching}
            error={query.error}
            retry={query.refetch}
            page={page}
            total={query.data?.total}
            onPage={(next) => { if (!batchStatusMutation.isPending && !singleStatus.isPending) { setSelected([]); setPage(next); } }}
            selection={
              canUpdate
                ? {
                    keys: selected.map((row) => row.id),
                    onChange: (_, rows) => setSelected(rows),
                    disabled: batchStatusMutation.isPending,
                  }
                : undefined
            }
            toolbar={[
              canUpdate && (
                <Space key="batch">
                  <Button
                    icon={<CheckCircleOutlined />}
                    disabled={!selected.length || batchStatusMutation.isPending}
                    onClick={() => batchStatusMutation.mutate("on_sale")}
                  >
                    批量上架
                  </Button>
                  <Button
                    icon={<MinusCircleOutlined />}
                    disabled={!selected.length || batchStatusMutation.isPending}
                    onClick={() => batchStatusMutation.mutate("off_sale")}
                  >
                    批量下架
                  </Button>
                </Space>
              ),
              canCreate && (
                <Button
                  key="new"
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setEditingProduct(null)}
                >
                  新建商品
                </Button>
              ),
            ]}
            columns={[
              {
                title: "商品名称",
                dataIndex: "name",
                ellipsis: true,
              },
              {
                title: "所属分类",
                dataIndex: "category_id",
                render: (id: unknown) => (typeof id === "string" ? categoryMap.get(id) ?? id : "-"),
              },
              {
                title: "类型",
                dataIndex: "product_type",
                render: (v) =>
                  v === "physical" ? (
                    <Tag color="blue">实物商品</Tag>
                  ) : (
                    <Tag color="purple">虚拟服务</Tag>
                  ),
              },
              {
                title: "状态",
                dataIndex: "status",
                render: (v) => {
                  if (v === "on_sale") return <Tag color="success">在售中</Tag>;
                  if (v === "off_sale") return <Tag color="default">已下架</Tag>;
                  return <Tag color="warning">草稿</Tag>;
                },
              },
              {
                title: "SKU 货品",
                render: (_, row) => (
                  <Button
                    size="small"
                    icon={<UnorderedListOutlined />}
                    onClick={() => setInspectProduct(row)}
                  >
                    {row.skus.length} 款变体
                  </Button>
                ),
              },
              {
                title: "版本",
                dataIndex: "revision",
                render: (v) => `v${v}`,
              },
              {
                title: "操作",
                width: "1%",
                render: (_, row) => (
                  <Space>
                    {canUpdate && (
                      <Button
                        icon={<EditOutlined />}
                        onClick={() => setEditingProduct(row)}
                      >
                        编辑
                      </Button>
                    )}
                    {canUpdate && (
                      <Button
                        icon={<TagsOutlined />}
                        onClick={() => setSpecificationProductId(row.id)}
                      >
                        规格维护
                      </Button>
                    )}
                    {canUpdate && row.status === "off_sale" && (
                      <Button
                        type="link"
                        size="small"
                        disabled={singleStatus.isPending || batchStatusMutation.isPending}
                        onClick={() => singleStatus.mutate({ product: row, status: "on_sale" })}
                      >
                        上架
                      </Button>
                    )}
                    {canUpdate && row.status === "on_sale" && (
                      <Button
                        type="link"
                        size="small"
                        danger
                        disabled={singleStatus.isPending || batchStatusMutation.isPending}
                        onClick={() => singleStatus.mutate({ product: row, status: "off_sale" })}
                      >
                        下架
                      </Button>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      )}

      {inspectProduct && (
        <Drawer
          title={`【${inspectProduct.name}】货品变体列表`}
          open
          size={760}
          onClose={() => setInspectProduct(null)}
        >
          <Table
            size="small"
            pagination={false}
            rowKey="id"
            scroll={{ x: "max-content" }}
            dataSource={inspectProduct.skus}
            columns={([
              { title: "SKU 编码", dataIndex: "code" },
              {
                title: "售价",
                dataIndex: "price",
                render: (v: string | number) => `￥${v}`,
              },
              {
                title: "划线原价",
                dataIndex: "market_price",
                render: (v: string | number | null) => (v ? `￥${v}` : "-"),
              },
              {
                title: "状态",
                render: (_, row: SkuRead) => (
                  <Tag color={row.is_active ? "success" : "default"}>
                    {row.is_active ? "正常" : "已停用"}
                  </Tag>
                ),
              },
              {
                title: "操作",
                width: "1%",
                render: (_, row: SkuRead) => (
                  <Button
                    size="small"
                    disabled={!canAccess(admin, "inventory:read")}
                    onClick={() => setInventorySku(row)}
                  >
                    库存详情 / 盘点
                  </Button>
                ),
              },
            ] as ColumnsType<SkuRead>).map((col) => ({
              ...col,
              onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
              onCell: () => ({ style: { whiteSpace: "nowrap" } }),
            }))}
          />
        </Drawer>
      )}

      {editingProduct !== undefined && (
        <ProductEditor
          target={editingProduct}
          close={() => setEditingProduct(undefined)}
          done={refresh}
        />
      )}

      {specificationProductId && (
        <ProductSpecificationsPanel
          productId={specificationProductId}
          canUpdate={canUpdate}
          close={() => setSpecificationProductId(undefined)}
          done={refresh}
        />
      )}

      {inventorySku && (
        <InventoryPanel
          sku={inventorySku}
          close={() => setInventorySku(null)}
        />
      )}
    </PageFrame>
  );
}

export default ProductsPage;
