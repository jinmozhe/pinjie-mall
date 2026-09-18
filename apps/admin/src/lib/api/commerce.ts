import type {
  OrdersPageApiV1AdminOrdersGetData, CommerceExportRead, SelectedCommerceIds,
  PageResultPaymentAttemptRead, PageResultReconciliationRecordRead, PageResultMemberProfileRead,
  PageResultCommissionRead, PageResultAdminWalletRead, PageResultWalletLedgerRead,
  ReconciliationRecordCreate, ReconciliationRecordRead,
  ActiveStatusBatch, BatchCompleted, CategoryInput, CategoryRead, CategoryUpdate,
  FreightQuote, FreightQuoteInput, InventoryAdjustment, InventoryMovementRead, InventoryRead,
  PageResultInventoryMovementRead, PageResultProductRead, PageResultShippingTemplateRead,
  ProductCreate, ProductRead, ProductStatusBatch, ProductStatusUpdate, ProductUpdate,
  ShippingTemplateInput, ShippingTemplateRead, ShippingTemplateUpdate, SkuUpdate, SkuStatusBatch,
  OrderRead, FulfillmentRead, RefundRequestRead, RefundReview, ShipmentCreate, VirtualDeliveryCreate,
  PageResultAdminOrderSummary, PageResultRefundRequestRead, PageResultWithdrawalRead, WithdrawalRead, WithdrawalReview,
} from "@pinjie/api-client";

import { apiRequest, jsonBody } from "./http";

export type ProductFilters = {
  page: number; search?: string; category_id?: string;
  status?: ProductRead["status"]; product_type?: ProductRead["product_type"];
};

export type CommerceFilters = NonNullable<OrdersPageApiV1AdminOrdersGetData["query"]>;
export type CommerceResource = "orders" | "refunds" | "withdrawals" | "payments" | "reconciliation-records" | "members" | "commissions" | "wallets";

export function queryString(values: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  return query.toString();
}

export const commerceApi = {
  export: (resource: CommerceResource, input: SelectedCommerceIds) => apiRequest<CommerceExportRead>(`/api/v1/admin/${resource}/export`, { method: "POST", body: jsonBody(input) }),
  payments: (filters: CommerceFilters) => apiRequest<PageResultPaymentAttemptRead>(`/api/v1/admin/payments?${queryString(filters)}`),
  reconciliations: (filters: CommerceFilters) => apiRequest<PageResultReconciliationRecordRead>(`/api/v1/admin/reconciliation-records?${queryString(filters)}`),
  reconcile: (input: ReconciliationRecordCreate) => apiRequest<ReconciliationRecordRead>("/api/v1/admin/reconciliation-records", { method: "POST", body: jsonBody(input) }),
  members: (filters: CommerceFilters) => apiRequest<PageResultMemberProfileRead>(`/api/v1/admin/members?${queryString(filters)}`),
  commissions: (filters: CommerceFilters) => apiRequest<PageResultCommissionRead>(`/api/v1/admin/commissions?${queryString(filters)}`),
  wallets: (filters: CommerceFilters) => apiRequest<PageResultAdminWalletRead>(`/api/v1/admin/wallets?${queryString(filters)}`),
  ledgers: (id: string, page: number) => apiRequest<PageResultWalletLedgerRead>(`/api/v1/admin/wallets/${id}/ledgers?page=${page}&page_size=20`),
  categories: () => apiRequest<CategoryRead[]>("/api/v1/admin/product-categories"),
  createCategory: (input: CategoryInput) => apiRequest<CategoryRead>("/api/v1/admin/product-categories", { method: "POST", body: jsonBody(input) }),
  updateCategory: (id: string, input: CategoryUpdate) => apiRequest<CategoryRead>(`/api/v1/admin/product-categories/${id}`, { method: "PUT", body: jsonBody(input) }),
  categoriesStatus: (input: ActiveStatusBatch) => apiRequest<BatchCompleted>("/api/v1/admin/product-categories/status/batch", { method: "PATCH", body: jsonBody(input) }),
  products: (filters: ProductFilters) => apiRequest<PageResultProductRead>(`/api/v1/admin/products?${queryString({ ...filters, page_size: 20 })}`),
  product: (id: string) => apiRequest<ProductRead>(`/api/v1/admin/products/${id}`),
  createProduct: (input: ProductCreate) => apiRequest<ProductRead>("/api/v1/admin/products", { method: "POST", body: jsonBody(input) }),
  updateProduct: (id: string, input: ProductUpdate) => apiRequest<ProductRead>(`/api/v1/admin/products/${id}`, { method: "PUT", body: jsonBody(input) }),
  productStatus: (id: string, input: ProductStatusUpdate) => apiRequest<ProductRead>(`/api/v1/admin/products/${id}/status`, { method: "PUT", body: jsonBody(input) }),
  productsStatus: (input: ProductStatusBatch) => apiRequest<BatchCompleted>("/api/v1/admin/products/status/batch", { method: "PATCH", body: jsonBody(input) }),
  writeSku: (productId: string, input: SkuUpdate, skuId?: string) => apiRequest<ProductRead>(`/api/v1/admin/products/${productId}/skus${skuId ? `/${skuId}` : ""}`, { method: skuId ? "PUT" : "POST", body: jsonBody(input) }),
  skusStatus: (productId: string, input: SkuStatusBatch) => apiRequest<ProductRead>(`/api/v1/admin/products/${productId}/skus/status/batch`, { method: "PATCH", body: jsonBody(input) }),
  inventory: (skuId: string) => apiRequest<InventoryRead>(`/api/v1/admin/inventory/${skuId}`),
  adjustInventory: (skuId: string, input: InventoryAdjustment) => apiRequest<InventoryMovementRead>(`/api/v1/admin/inventory/${skuId}/adjustments`, { method: "POST", body: jsonBody(input) }),
  movements: (skuId: string, page: number) => apiRequest<PageResultInventoryMovementRead>(`/api/v1/admin/inventory/${skuId}/movements?page=${page}&page_size=20`),
  shipping: (page: number) => apiRequest<PageResultShippingTemplateRead>(`/api/v1/admin/shipping-templates?page=${page}&page_size=20`),
  shippingDetail: (id: string) => apiRequest<ShippingTemplateRead>(`/api/v1/admin/shipping-templates/${id}`),
  createShipping: (input: ShippingTemplateInput) => apiRequest<ShippingTemplateRead>("/api/v1/admin/shipping-templates", { method: "POST", body: jsonBody(input) }),
  updateShipping: (id: string, input: ShippingTemplateUpdate) => apiRequest<ShippingTemplateRead>(`/api/v1/admin/shipping-templates/${id}`, { method: "PUT", body: jsonBody(input) }),
  shippingStatus: (input: ActiveStatusBatch) => apiRequest<BatchCompleted>("/api/v1/admin/shipping-templates/status/batch", { method: "PATCH", body: jsonBody(input) }),
  quote: (id: string, input: FreightQuoteInput) => apiRequest<FreightQuote>(`/api/v1/admin/shipping-templates/${id}/quote`, { method: "POST", body: jsonBody(input) }),
  orders: (filters: CommerceFilters) => apiRequest<PageResultAdminOrderSummary>(`/api/v1/admin/orders?${queryString(filters)}`),
  order: (id: string) => apiRequest<OrderRead>(`/api/v1/admin/orders/${id}`),
  fulfillment: (id: string) => apiRequest<FulfillmentRead>(`/api/v1/admin/orders/${id}/fulfillment`),
  ship: (id: string, input: ShipmentCreate) => apiRequest<FulfillmentRead>(`/api/v1/admin/orders/${id}/fulfillment/shipment`, { method: "POST", body: jsonBody(input) }),
  deliverVirtual: (id: string, input: VirtualDeliveryCreate) => apiRequest<FulfillmentRead>(`/api/v1/admin/orders/${id}/fulfillment/virtual-delivery`, { method: "POST", body: jsonBody(input) }),
  refunds: (filters: CommerceFilters) => apiRequest<PageResultRefundRequestRead>(`/api/v1/admin/refunds?${queryString(filters)}`),
  approveRefund: (id: string, input: RefundReview) => apiRequest<RefundRequestRead>(`/api/v1/admin/refunds/${id}/approve`, { method: "POST", body: jsonBody(input) }),
  rejectRefund: (id: string, input: RefundReview) => apiRequest<RefundRequestRead>(`/api/v1/admin/refunds/${id}/reject`, { method: "POST", body: jsonBody(input) }),
  withdrawals: (filters: CommerceFilters) => apiRequest<PageResultWithdrawalRead>(`/api/v1/admin/withdrawals?${queryString(filters)}`),
  approveWithdrawal: (id: string, input: WithdrawalReview) => apiRequest<WithdrawalRead>(`/api/v1/admin/withdrawals/${id}/approve`, { method: "POST", body: jsonBody(input) }),
  rejectWithdrawal: (id: string, input: WithdrawalReview) => apiRequest<WithdrawalRead>(`/api/v1/admin/withdrawals/${id}/reject`, { method: "POST", body: jsonBody(input) }),
};
