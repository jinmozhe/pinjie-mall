import type { ProductRead } from "@pinjie/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/setup";
import { ProductRecommendationCell } from "./ProductRecommendationCell";

const product: ProductRead = {
  id: "01900000-0000-7000-8000-000000000001", name: "推荐礼盒",
  category_id: "01900000-0000-7000-8000-000000000002", product_type: "physical",
  description_format: "restricted_html_v1", status: "on_sale", revision: 3,
  is_home_recommended: true, home_recommend_sort: 8, skus: [], attributes: [],
};

function mount(canUpdate = true) {
  const lock = vi.fn();
  const done = vi.fn(async () => undefined);
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<ConfigProvider locale={zhCN}><App><QueryClientProvider client={client}>
    <ProductRecommendationCell product={product} canUpdate={canUpdate} disabled={false} lock={lock} done={done} />
  </QueryClientProvider></App></ConfigProvider>);
  return { lock, done };
}

describe("首页推荐配置", () => {
  it("hides write controls from read-only administrators", () => {
    mount(false);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "排序" })).not.toBeInTheDocument();
    expect(screen.getByText("已推荐")).toBeInTheDocument();
  });

  it("keeps the saved switch state after rejection and preserves the sort in the request", async () => {
    const requests: unknown[] = [];
    server.use(http.put("*/api/v1/admin/products/:id/recommendation", async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json({ code: "PRODUCT_REVISION_CONFLICT", message: "商品已变更，请重新读取" }, { status: 409 });
    }));
    const user = userEvent.setup();
    const { done, lock } = mount();
    await user.click(screen.getByRole("switch", { name: "推荐礼盒首页推荐" }));
    await screen.findByText("商品已变更，请重新读取");
    expect(requests).toEqual([{ revision: 3, is_home_recommended: false, home_recommend_sort: 8 }]);
    expect(screen.getByRole("switch")).toBeChecked();
    expect(done).not.toHaveBeenCalled();
    await waitFor(() => expect(lock).toHaveBeenLastCalledWith(product.id, false));
  });

  it("does not write on cancel and retains the original version and sort draft after a failed save", async () => {
    const requests: unknown[] = [];
    server.use(http.put("*/api/v1/admin/products/:id/recommendation", async ({ request }) => {
      requests.push(await request.json());
      return requests.length === 1
        ? HttpResponse.json({ code: "DEPENDENCY_UNAVAILABLE", message: "保存失败，请重试" }, { status: 503 })
        : HttpResponse.json({ code: "OK", message: "成功", data: { ...product, home_recommend_sort: 2, revision: 4 } });
    }));
    const user = userEvent.setup();
    const { done } = mount();
    await user.click(screen.getByRole("button", { name: "排序" }));
    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(requests).toEqual([]);
    await user.click(screen.getByRole("button", { name: "排序" }));
    const input = screen.getByRole("spinbutton", { name: "推荐排序" });
    await user.clear(input);
    await user.type(input, "2");
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent("保存失败"));
    expect(input).toHaveValue("2");
    expect(done).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(done).toHaveBeenCalledOnce());
    expect(requests).toEqual([
      { revision: 3, is_home_recommended: true, home_recommend_sort: 2 },
      { revision: 3, is_home_recommended: true, home_recommend_sort: 2 },
    ]);
  });
});
