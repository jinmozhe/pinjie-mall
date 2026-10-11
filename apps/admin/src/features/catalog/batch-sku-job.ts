import type { InventoryAdjustment, ProductRead, SkuUpdate } from "@pinjie/api-client";

import { commerceApi } from "@/lib/api/commerce";
import { ApiError } from "@/lib/api/http";

export type SkuJobRow = {
  input: SkuUpdate;
  quantity: number;
  attempted: boolean;
  skuId?: string;
  adjustment?: InventoryAdjustment;
  completed: boolean;
};
export type SkuJob = { version: 1; rows: SkuJobRow[] };

export function boundedCombinationCount(dimensions: number[]): number {
  if (!dimensions.length || dimensions.includes(0)) return 0;
  let count = 1;
  for (const size of dimensions) {
    count *= size;
    if (count > 100) return 101;
  }
  return count;
}

// Browser storage contains operation drafts only. Authentication remains in HttpOnly cookies.
export function readSkuJob(key: string): SkuJob | null {
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  const value: unknown = JSON.parse(raw);
  const record = (item: unknown): item is Record<string, unknown> => Boolean(item) && typeof item === "object";
  const money = (item: unknown) => typeof item === "string" && /^\d+(\.\d{1,2})?$/.test(item);
  const optionalMoney = (item: unknown) => item == null || money(item);
  const positive = (item: unknown) => typeof item === "number" && Number.isSafeInteger(item) && item > 0;
  if (!record(value) || value.version !== 1 || !Array.isArray(value.rows) || !value.rows.length || value.rows.length > 100) {
    throw new Error("SKU 恢复草稿损坏，请保留此标签页并联系管理员核查，禁止重新提交库存。");
  }
  for (const row of value.rows) {
    if (!record(row) || !record(row.input)) throw new Error("SKU 恢复草稿格式无效");
    const input = row.input;
    if (typeof input.code !== "string" || !/^[A-Za-z0-9_-]{1,100}$/.test(input.code)
      || !money(input.price) || !optionalMoney(input.cost_price) || !optionalMoney(input.market_price)
      || (input.weight_grams != null && !(typeof input.weight_grams === "number" && Number.isSafeInteger(input.weight_grams) && input.weight_grams >= 0))
      || typeof input.is_active !== "boolean" || !positive(input.revision)
      || !Array.isArray(input.spec_value_ids) || !input.spec_value_ids.every((id) => typeof id === "string")
      || typeof row.quantity !== "number" || !Number.isSafeInteger(row.quantity) || row.quantity < 0 || row.quantity > 1000000000
      || typeof row.attempted !== "boolean" || typeof row.completed !== "boolean"
      || (row.skuId !== undefined && typeof row.skuId !== "string")) throw new Error("SKU 恢复草稿字段无效");
    if (row.adjustment !== undefined) {
      const adjustment = row.adjustment;
      if (!record(adjustment) || !row.skuId || typeof adjustment.request_id !== "string"
        || !positive(adjustment.revision) || adjustment.quantity_delta !== row.quantity
        || typeof adjustment.reason !== "string") throw new Error("库存恢复请求无效");
    }
  }
  // Every field consumed by the runner has been checked above; API validation remains authoritative.
  return value as SkuJob;
}

export async function runSkuJob(
  productId: string,
  job: SkuJob,
  persist: () => void,
  saved: (product: ProductRead) => Promise<void>,
  progress: (completed: number, total: number, code: string) => void,
  ensureActive: () => void,
): Promise<void> {
  ensureActive();
  let product: ProductRead = await commerceApi.product(productId);
  for (const [index, row] of job.rows.entries()) {
    ensureActive();
    progress(index, job.rows.length, row.input.code);
    if (row.completed) continue;
    if (!row.skuId) {
      const existing = product.skus.find((sku) => sku.code === row.input.code);
      if (existing) {
        const sameMoney = (left: string | number | null | undefined, right: string | number | null | undefined) =>
          left == null || right == null ? left == null && right == null : Number(left) === Number(right);
        if (!row.attempted || existing.archived_at !== null
          || [...(existing.spec_value_ids ?? [])].sort().join() !== [...(row.input.spec_value_ids ?? [])].sort().join()
          || !sameMoney(existing.price, row.input.price) || !sameMoney(existing.cost_price, row.input.cost_price)
          || !sameMoney(existing.market_price, row.input.market_price) || existing.is_active !== row.input.is_active
          || existing.weight_grams !== row.input.weight_grams) {
          throw new Error(`SKU ${row.input.code} 与已保存内容冲突，请核查商品后继续。`);
        }
        row.skuId = existing.id;
      } else {
        if (!row.attempted) row.input.revision = product.revision;
        const previouslyAttempted = row.attempted;
        row.attempted = true;
        persist(); // Save the exact create request before any network side effect.
        try {
          product = await commerceApi.writeSku(productId, row.input);
        } catch (error) {
          if (!previouslyAttempted && error instanceof ApiError && error.source === "request"
            && [400, 403, 404, 409, 422].includes(error.status)) {
            // An explicit rejection of the first attempt permits cancelling the uncreated draft.
            row.attempted = false;
            persist();
          }
          throw error;
        }
        const created = product.skus.find((sku) => sku.code === row.input.code);
        if (!created) throw new Error("创建响应缺少 SKU，请点击继续先核对商品结果。");
        row.skuId = created.id;
      }
      persist();
      ensureActive();
      await saved(product); // Creation is a committed fact even if inventory later fails.
    }
    if (row.quantity > 0) {
      if (!row.adjustment) {
        ensureActive();
        const inventory = await commerceApi.inventory(row.skuId);
        row.adjustment = {
          request_id: globalThis.crypto.randomUUID(),
          revision: inventory.revision,
          quantity_delta: row.quantity,
          reason: "批量派生初始可售库存",
        };
        persist();
      }
      try {
        // Replaying the original request also queries its outcome under the server's lock.
        // Its id and payload (including revision) must remain identical after unknown results.
        ensureActive();
        await commerceApi.adjustInventory(row.skuId, row.adjustment);
      } catch (error) {
        if (error instanceof ApiError && error.source === "request" && error.code === "INVENTORY_REVISION_CONFLICT") {
          // Server checks the idempotency record before revision: this request was not applied.
          row.adjustment = undefined;
          persist();
        }
        throw error;
      }
    }
    row.completed = true;
    persist();
  }
  ensureActive();
  await saved(product);
  ensureActive();
}
