import type { ProductDetailRead, SkuRead } from "@pinjie/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { commerceApi } from "@/lib/api/commerce";
import { boundedCombinationCount, readSkuJob, runSkuJob, type SkuJob } from "./batch-sku-job";

const sku: SkuRead = {
  id: "sku-created", code: "SKU-1", price: "2.00", cost_price: null, market_price: null,
  weight_grams: null, is_active: true, spec_value_ids: ["candidate"], sku_no: 1,
  specifications: {}, specification_key: "candidate", archived_at: null,
};
const product: ProductDetailRead = {
  id: "product", name: "商品", product_type: "physical", category_id: "category",
  description_format: "restricted_html_v1", status: "draft", revision: 1, skus: [], attributes: [],
  image_assets: [], detail_image_asset_ids: [], detail_images: [],
};
const created: ProductDetailRead = { ...product, revision: 2, skus: [sku] };
const makeJob = (): SkuJob => ({ version: 1, rows: [{
  input: { code: sku.code, price: sku.price, cost_price: null, market_price: null, weight_grams: null,
    is_active: true, spec_value_ids: ["candidate"], revision: 1 },
  quantity: 5, attempted: false, completed: false,
}] });

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.removeItem("sku-job-test");
});

describe("bounded SKU derivation and recovery", () => {
  it("rejects huge products before expansion while preserving zero and limit cases", () => {
    expect(boundedCombinationCount([100, 100, 100, 100])).toBe(101);
    expect(boundedCombinationCount([10, 10])).toBe(100);
    expect(boundedCombinationCount([100, 100, 0])).toBe(0);
    expect(boundedCombinationCount([])).toBe(0);
  });

  it("persists created SKU facts and replays exactly the original unknown inventory request after reload", async () => {
    vi.spyOn(commerceApi, "product").mockResolvedValue(product);
    const write = vi.spyOn(commerceApi, "writeSku").mockResolvedValue(created);
    const inventory = vi.spyOn(commerceApi, "inventory").mockResolvedValue({ sku_id: sku.id, available: 0, reserved: 0, revision: 1 });
    const adjust = vi.spyOn(commerceApi, "adjustInventory").mockRejectedValueOnce(new Error("response lost"));
    const saved = vi.fn().mockResolvedValue(undefined);
    let job = makeJob();
    const persist = () => window.sessionStorage.setItem("sku-job-test", JSON.stringify(job));
    await expect(runSkuJob(product.id, job, persist, saved, vi.fn(), vi.fn())).rejects.toThrow("response lost");
    expect(saved).toHaveBeenCalledWith(created);
    expect(job.rows[0]!.skuId).toBe(sku.id);
    expect(job.rows[0]!.completed).toBe(false);
    const original = globalThis.structuredClone(job.rows[0]!.adjustment);
    job = readSkuJob("sku-job-test")!;
    vi.mocked(commerceApi.product).mockResolvedValue(created);
    adjust.mockResolvedValue({ id: "movement", sku_id: sku.id, request_id: original!.request_id,
      actor_id: "admin", actor_type: "admin", source_type: "manual_adjustment", source_id: null,
      quantity_delta: 5, before_available: 0, after_available: 5, expected_revision: 1, resulting_revision: 2,
      reason: original!.reason, request_hash: "hash", created_at: "2026-10-11T00:00:00Z" });
    await runSkuJob(product.id, job, persist, saved, vi.fn(), vi.fn());
    expect(write).toHaveBeenCalledTimes(1);
    expect(inventory).toHaveBeenCalledTimes(1);
    expect(adjust.mock.calls.map((call) => call[1])).toEqual([original, original]);
    expect(job.rows[0]!.completed).toBe(true);
  });

  it("reads back an unknown SKU creation before considering another write", async () => {
    vi.spyOn(commerceApi, "product").mockResolvedValueOnce(product).mockResolvedValue(created);
    const write = vi.spyOn(commerceApi, "writeSku").mockRejectedValue(new Error("connection closed"));
    const saved = vi.fn().mockResolvedValue(undefined);
    const job = makeJob();
    job.rows[0]!.quantity = 0;
    await expect(runSkuJob(product.id, job, vi.fn(), saved, vi.fn(), vi.fn())).rejects.toThrow("connection closed");
    await runSkuJob(product.id, job, vi.fn(), saved, vi.fn(), vi.fn());
    expect(write).toHaveBeenCalledTimes(1);
    expect(job.rows[0]!.skuId).toBe(sku.id);
    expect(job.rows[0]!.completed).toBe(true);
  });

  it("fails closed for malformed recovery data", () => {
    window.sessionStorage.setItem("sku-job-test", JSON.stringify({ version: 1, rows: [{ input: {} }] }));
    expect(() => readSkuJob("sku-job-test")).toThrow();
  });

  it("preserves a completed creation but stops further writes after leaving the product or account", async () => {
    vi.spyOn(commerceApi, "product").mockResolvedValue(product);
    vi.spyOn(commerceApi, "writeSku").mockResolvedValue(created);
    const inventory = vi.spyOn(commerceApi, "inventory");
    const adjust = vi.spyOn(commerceApi, "adjustInventory");
    const job = makeJob();
    let active = true;
    await expect(runSkuJob(product.id, job, vi.fn(), async () => { active = false; }, vi.fn(), () => {
      if (!active) throw new Error("account changed");
    })).rejects.toThrow("account changed");
    expect(job.rows[0]!.skuId).toBe(sku.id);
    expect(inventory).not.toHaveBeenCalled();
    expect(adjust).not.toHaveBeenCalled();
  });
});
