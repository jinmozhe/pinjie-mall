import type { ProductRead, SkuRead } from "@pinjie/api-client";
import { EditOutlined, SearchOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Tag } from "antd";
import { useState } from "react";

import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { InventoryPanel } from "./InventoryPanel";

export function InventoryPage() {
  const admin = useCurrentAdmin();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [activeSku, setActiveSku] = useState<SkuRead | null>(null);

  const allowed = canAccess(admin, "inventory:read");
  const canAdjust = canAccess(admin, "inventory:adjust");

  const query = useQuery({
    queryKey: ["commerce-products-inventory", page, search],
    queryFn: () => commerceApi.products({ page, search: search || undefined }),
    enabled: allowed,
  });

  // 平铺 SKU 列表便于库存审计与快速盘点
  const flatSkus: Array<{
    sku: SkuRead;
    product: ProductRead;
  }> = [];

  for (const product of query.data?.items ?? []) {
    for (const sku of product.skus) {
      flatSkus.push({ sku, product });
    }
  }

  return (
    <PageFrame
      title="库存管理"
      description="查询货品 SKU 实时库存、订单预占追踪与幂等盘点调整流水。"
    >
      {!allowed ? (
        <Alert type="warning" title="无权查看库存数据" />
      ) : (
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Card title="快捷定位 SKU" size="small">
            <Form layout="inline" onFinish={(values: { search?: string }) => {
              setSearch(values.search?.trim() || "");
              setPage(1);
            }}>
              <Form.Item name="search">
                <Input
                  placeholder="输入商品名称或 SKU 编码"
                  allowClear
                  style={{ width: 320 }}
                  prefix={<SearchOutlined />}
                />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit">
                  查询库存
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <ResourceTable
            title="货品库存列表"
            rows={flatSkus}
            loading={query.isLoading}
            fetching={query.isFetching}
            error={query.error}
            retry={query.refetch}
            page={page}
            total={query.data?.total}
            onPage={setPage}
            columns={[
              {
                title: "SKU 编码",
                dataIndex: ["sku", "code"],
                ellipsis: true,
              },
              {
                title: "所属商品",
                dataIndex: ["product", "name"],
                ellipsis: true,
              },
              {
                title: "商品类型",
                dataIndex: ["product", "product_type"],
                render: (v) => (v === "physical" ? <Tag color="blue">实物商品</Tag> : <Tag color="purple">虚拟服务</Tag>),
              },
              {
                title: "SKU 状态",
                render: (_, row) => (
                  <Tag color={row.sku.is_active ? "success" : "default"}>
                    {row.sku.is_active ? "正常可售" : "已停用"}
                  </Tag>
                ),
              },
              {
                title: "售价",
                dataIndex: ["sku", "price"],
                render: (v) => `￥${v}`,
              },
              {
                title: "操作",
                width: "1%",
                render: (_, row) => (
                  <Button
                    icon={<EditOutlined />}
                    type={canAdjust ? "primary" : "default"}
                    onClick={() => setActiveSku(row.sku)}
                  >
                    {canAdjust ? "盘点 / 调库存" : "查看流水"}
                  </Button>
                ),
              },
            ]}
          />
        </Space>
      )}

      {activeSku && (
        <InventoryPanel
          sku={activeSku}
          close={() => setActiveSku(null)}
        />
      )}
    </PageFrame>
  );
}

export default InventoryPage;
