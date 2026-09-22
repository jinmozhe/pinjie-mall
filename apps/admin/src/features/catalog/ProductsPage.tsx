import { Alert } from "antd";

import { PageFrame } from "@/components/PageFrame";

export function ProductsPage() {
  return (
    <PageFrame title="商品管理" description="商品模型正在升级为品牌、属性与规格采用版本。">
      <Alert
        type="warning"
        title="商品管理正在迁移"
        description="新的品牌、属性、规格和 SKU 契约已由后端提供。本页面将在商品管理专项中重新接入。"
      />
    </PageFrame>
  );
}

export default ProductsPage;
