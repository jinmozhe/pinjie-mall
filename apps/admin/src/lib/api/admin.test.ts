import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "./admin";
import { http, HttpResponse } from "msw";
import { server } from "@/test/setup";

const targetId = "01900000-0000-7000-8000-000000000041";

describe("admin API request shapes", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads role options after the first 100 records", async () => {
    const pages: number[] = [];
    server.use(http.get("http://localhost:3000/api/v1/admin/roles", ({ request }) => {
      const page = Number(new globalThis.URL(request.url).searchParams.get("page"));
      pages.push(page);
      const items = Array.from({ length: page === 1 ? 100 : 1 }, (_, index) => ({ id: `role-${(page - 1) * 100 + index}` }));
      return HttpResponse.json({ data: { items, page, page_size: 100, total: 101, total_pages: 2 } });
    }));
    const roles = await adminApi.roleOptions();
    expect(pages).toEqual([1, 2]);
    expect(roles).toHaveLength(101);
    expect(roles[100]?.id).toBe("role-100");
  });

  it("rejects incomplete role options when a later page fails", async () => {
    server.use(http.get("http://localhost:3000/api/v1/admin/roles", ({ request }) =>
      new globalThis.URL(request.url).searchParams.get("page") === "1"
        ? HttpResponse.json({ data: { items: [{ id: "first" }], page: 1, page_size: 100, total: 101, total_pages: 2 } })
        : HttpResponse.json({ code: "SERVICE_UNAVAILABLE" }, { status: 503 })));
    await expect(adminApi.roleOptions()).rejects.toMatchObject({ status: 503 });
  });

  it("sends uploads and uncovered bulk lifecycle requests", async () => {
    const bodies: Record<string, unknown> = {};
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/v1/assets/upload")) {
        const form = init?.body as globalThis.FormData;
        bodies.uploadScene = form.get("scene");
        bodies.uploadFile = form.get("file");
      } else if (url.endsWith("/api/v1/admin/settings/site/logo")) {
        const form = init?.body as globalThis.FormData;
        bodies.siteLogoRevision = form.get("revision");
        bodies.siteLogoFile = form.get("file");
      } else if (url.endsWith("/api/v1/admin/users/status/batch")) {
        bodies.userStatus = JSON.parse(String(init?.body));
      } else if (url.endsWith(`/api/v1/admin/users/${targetId}/restore`)) {
        bodies.restoredUserId = targetId;
      } else if (url.endsWith("/api/v1/admin/roles/status/batch")) {
        bodies.roleStatus = JSON.parse(String(init?.body));
      }
      return new Response(JSON.stringify({
        code: "OK",
        message: "操作成功",
        data: { id: targetId, completed_count: 1, target_ids: [targetId] },
        request_id: "api-test",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    const file = new globalThis.File(["png"], "avatar.png", { type: "image/png" });
    await adminApi.uploadAsset(file);
    await adminApi.uploadSiteLogo(file, 7);
    await adminApi.setUserStatusBulk({ user_ids: [targetId], is_active: false });
    await adminApi.restoreUser(targetId);
    await adminApi.setRoleStatusBulk({ role_ids: [targetId], is_active: false });

    expect(bodies.uploadScene).toBe("avatar");
    expect(bodies.uploadFile).toBeInstanceOf(globalThis.File);
    expect(bodies.siteLogoRevision).toBe("7");
    expect(bodies.siteLogoFile).toBeInstanceOf(globalThis.File);
    expect(bodies.userStatus).toEqual({ user_ids: [targetId], is_active: false });
    expect(bodies.restoredUserId).toBe(targetId);
    expect(bodies.roleStatus).toEqual({ role_ids: [targetId], is_active: false });
  });
});
