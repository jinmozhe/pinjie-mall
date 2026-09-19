import type {
  AdminAuthSessionOut,
  AdminRegistrationSettingRead,
  AdminSiteSettingRead,
  AdminBulkStatusUpdateIn,
  AdminCreateIn,
  AdminLoginIn,
  AdminProfileUpdateIn,
  AdminRead,
  AdminSuperuserUpdateIn,
  AdminUserCreateIn,
  AdminUserRead,
  AdminUpdateIn,
  AssetBulkDeleteIn,
  AssetBulkDeleteResult,
  AssetRead,
  BatchActionResult,
  PageResultSessionRead,
  PageResultAdminRead,
  PageResultAuditEventRead,
  PageResultAssetRead,
  PageResultLoginEventRead,
  PageResultRequestLogRead,
  PageResultRoleRead,
  PageResultAdminUserRead,
  PermissionRead,
  RoleCreateIn,
  RoleBulkDeleteIn,
  RoleBulkStatusUpdateIn,
  RoleRead,
  RefreshSessionOut,
  RegistrationSettingPatchIn,
  RolePermissionAssignIn,
  RoleUpdateIn,
  StatusUpdateIn,
  SiteSettingPatchIn,
  SystemOverviewRead,
  UserUpdateIn,
  UserBulkDeleteIn,
  UserBulkStatusUpdateIn,
  UserPrincipalOut,
  UserRestoreBatchIn,
  UploadScene,
  UploaderType,
} from "@pinjie/api-client";

import { apiRequest, jsonBody } from "./http";

export const adminApi = {
  login: (input: AdminLoginIn) =>
    apiRequest<AdminAuthSessionOut>("/api/v1/admin/auth/login", {
      method: "POST",
      body: jsonBody(input),
    }, { retryAuth: false }),
  me: () => apiRequest<AdminRead>("/api/v1/admin/auth/me"),
  updateProfile: (input: AdminProfileUpdateIn) =>
    apiRequest<AdminRead>("/api/v1/admin/auth/profile", {
      method: "PATCH",
      body: jsonBody(input),
    }),
  uploadAsset: (file: globalThis.File, scene: UploadScene = "avatar") => {
    const body = new globalThis.FormData();
    body.set("file", file);
    body.set("scene", scene);
    return apiRequest<AssetRead>("/api/v1/assets/upload", { method: "POST", body });
  },
  assets: ({ page, search, scene, uploaderType }: { page: number; search?: string; scene?: UploadScene; uploaderType?: UploaderType }) => {
    const query = new URLSearchParams({ page: String(page), page_size: "20" });
    if (search) query.set("search", search);
    if (scene) query.set("scene", scene);
    if (uploaderType) query.set("uploader_type", uploaderType);
    return apiRequest<PageResultAssetRead>(`/api/v1/assets?${query}`);
  },
  deleteAsset: (id: string) =>
    apiRequest<boolean>(`/api/v1/assets/${id}`, { method: "DELETE" }),
  deleteAssetsBulk: (input: AssetBulkDeleteIn) =>
    apiRequest<AssetBulkDeleteResult>(
      "/api/v1/assets/batch",
      { method: "DELETE", body: jsonBody(input) },
    ),
  logout: () => apiRequest<boolean>("/api/v1/admin/auth/logout", { method: "POST" }, { retryAuth: false }),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiRequest<RefreshSessionOut>("/api/v1/admin/auth/password", {
      method: "POST",
      body: jsonBody({ current_password: currentPassword, new_password: newPassword }),
    }),
  users: ({
    page,
    search,
    lifecycle,
  }: {
    page: number;
    search?: string;
    lifecycle: "all" | "active" | "inactive" | "deleted";
  }) => {
    const query = new URLSearchParams({ page: String(page), page_size: "20" });
    if (search) query.set("search", search);
    query.set("lifecycle", lifecycle);
    return apiRequest<PageResultAdminUserRead>(`/api/v1/admin/users?${query}`);
  },
  createUser: (input: AdminUserCreateIn) =>
    apiRequest<AdminUserRead>("/api/v1/admin/users", { method: "POST", body: jsonBody(input) }),
  updateUser: (id: string, input: UserUpdateIn) =>
    apiRequest<UserPrincipalOut>(`/api/v1/admin/users/${id}`, { method: "PATCH", body: jsonBody(input) }),
  setUserStatus: (id: string, isActive: boolean) =>
    apiRequest<UserPrincipalOut>(
      `/api/v1/admin/users/${id}/status`,
      { method: "PATCH", body: jsonBody({ is_active: isActive } satisfies StatusUpdateIn) },
    ),
  setUserStatusBulk: (input: UserBulkStatusUpdateIn) =>
    apiRequest<BatchActionResult>(
      "/api/v1/admin/users/status/batch",
      { method: "PATCH", body: jsonBody(input) },
    ),
  deleteUsersBulk: (input: UserBulkDeleteIn) =>
    apiRequest<BatchActionResult>(
      "/api/v1/admin/users/batch",
      { method: "DELETE", body: jsonBody(input) },
    ),
  restoreUser: (id: string) =>
    apiRequest<AdminUserRead>(`/api/v1/admin/users/${id}/restore`, { method: "POST" }),
  restoreUsersBulk: (input: UserRestoreBatchIn) =>
    apiRequest<BatchActionResult>(
      "/api/v1/admin/users/restore/batch",
      { method: "POST", body: jsonBody(input) },
    ),
  resetUserPassword: (id: string, newPassword: string) =>
    apiRequest<{ completed?: boolean }>(
      `/api/v1/admin/users/${id}/credentials/password`,
      { method: "PUT", body: jsonBody({ new_password: newPassword }) },
    ),
  userSessions: (id: string, page = 1) =>
    apiRequest<PageResultSessionRead>(`/api/v1/admin/users/${id}/sessions?page=${page}&page_size=20`),
  revokeUserSessions: (id: string) =>
    apiRequest<{ completed?: boolean }>(
      `/api/v1/admin/users/${id}/sessions/revoke-all`,
      { method: "POST" },
    ),
  admins: (page: number) => apiRequest<PageResultAdminRead>(`/api/v1/admin/admins?page=${page}&page_size=20`),
  createAdmin: (input: AdminCreateIn) =>
    apiRequest<AdminRead>("/api/v1/admin/admins", { method: "POST", body: jsonBody(input) }),
  updateAdmin: (id: string, input: AdminUpdateIn) =>
    apiRequest<AdminRead>(
      `/api/v1/admin/admins/${id}`,
      { method: "PATCH", body: jsonBody(input) },
    ),
  setAdminSuperuser: (id: string, isSuperuser: boolean) =>
    apiRequest<AdminRead>(
      `/api/v1/admin/admins/${id}/superuser`,
      { method: "PATCH", body: jsonBody({ is_superuser: isSuperuser } satisfies AdminSuperuserUpdateIn) },
    ),
  setAdminStatus: (id: string, isActive: boolean) =>
    apiRequest<AdminRead>(
      `/api/v1/admin/admins/${id}/status`,
      { method: "PATCH", body: jsonBody({ is_active: isActive } satisfies StatusUpdateIn) },
    ),
  setAdminStatusBulk: (input: AdminBulkStatusUpdateIn) =>
    apiRequest<AdminRead[]>(
      "/api/v1/admin/admins/status/batch",
      { method: "PATCH", body: jsonBody(input) },
    ),
  resetAdminPassword: (id: string, newPassword: string) =>
    apiRequest<{ completed?: boolean }>(
      `/api/v1/admin/admins/${id}/credentials/password`,
      { method: "PUT", body: jsonBody({ new_password: newPassword }) },
    ),
  assignAdminRoles: (id: string, roleIds: string[]) =>
    apiRequest<AdminRead>(
      `/api/v1/admin/admins/${id}/roles`,
      { method: "PUT", body: jsonBody({ role_ids: roleIds }) },
    ),
  adminSessions: (id: string, page = 1) =>
    apiRequest<PageResultSessionRead>(`/api/v1/admin/admins/${id}/sessions?page=${page}&page_size=20`),
  revokeAdminSessions: (id: string) =>
    apiRequest<{ completed?: boolean }>(
      `/api/v1/admin/admins/${id}/sessions/revoke-all`,
      { method: "POST" },
    ),
  roles: (page = 1) => apiRequest<PageResultRoleRead>(`/api/v1/admin/roles?page=${page}&page_size=100`),
  roleOptions: async ({ signal }: { signal?: globalThis.AbortSignal } = {}): Promise<RoleRead[]> => {
    const first = await apiRequest<PageResultRoleRead>("/api/v1/admin/roles?page=1&page_size=100", { signal });
    const roles = new Map(first.items.map((role) => [role.id, role]));
    for (let page = 2; page <= first.total_pages; page += 1) {
      const result = await apiRequest<PageResultRoleRead>(`/api/v1/admin/roles?page=${page}&page_size=100`, { signal });
      for (const role of result.items) roles.set(role.id, role);
    }
    return [...roles.values()];
  },
  createRole: (input: RoleCreateIn) =>
    apiRequest<RoleRead>("/api/v1/admin/roles", { method: "POST", body: jsonBody(input) }),
  updateRole: (id: string, input: RoleUpdateIn) =>
    apiRequest<RoleRead>(
      `/api/v1/admin/roles/${id}`,
      { method: "PATCH", body: jsonBody(input) },
    ),
  deleteRole: (id: string) =>
    apiRequest<{ completed?: boolean }>(`/api/v1/admin/roles/${id}`, { method: "DELETE" }),
  setRoleStatusBulk: (input: RoleBulkStatusUpdateIn) =>
    apiRequest<BatchActionResult>(
      "/api/v1/admin/roles/status/batch",
      { method: "PATCH", body: jsonBody(input) },
    ),
  deleteRolesBulk: (input: RoleBulkDeleteIn) =>
    apiRequest<BatchActionResult>(
      "/api/v1/admin/roles/batch",
      { method: "DELETE", body: jsonBody(input) },
    ),
  assignPermissions: (id: string, permissionCodes: string[]) =>
    apiRequest<RoleRead>(
      `/api/v1/admin/roles/${id}/permissions`,
      {
        method: "PUT",
        body: jsonBody({ permission_codes: permissionCodes } satisfies RolePermissionAssignIn),
      },
    ),
  permissions: () => apiRequest<PermissionRead[]>("/api/v1/admin/permissions"),
  loginEvents: (page = 1) => apiRequest<PageResultLoginEventRead>(`/api/v1/admin/security/login-events?page=${page}&page_size=20`),
  auditEvents: (page = 1) => apiRequest<PageResultAuditEventRead>(`/api/v1/admin/security/audit-events?page=${page}&page_size=20`),
  requestLogs: (page = 1) => apiRequest<PageResultRequestLogRead>(`/api/v1/admin/system/request-logs?page=${page}&page_size=20`),
  systemOverview: () => apiRequest<SystemOverviewRead>("/api/v1/admin/system/overview"),
  siteSetting: () => apiRequest<AdminSiteSettingRead>("/api/v1/admin/settings/site"),
  updateSiteSetting: (input: SiteSettingPatchIn) =>
    apiRequest<AdminSiteSettingRead>("/api/v1/admin/settings/site", {
      method: "PATCH",
      body: jsonBody(input),
    }),
  uploadSiteLogo: (file: globalThis.File, revision: number) => {
    const body = new globalThis.FormData();
    body.set("file", file);
    body.set("revision", String(revision));
    return apiRequest<AdminSiteSettingRead>("/api/v1/admin/settings/site/logo", {
      method: "PUT",
      body,
    });
  },
  deleteSiteLogo: (revision: number) =>
    apiRequest<AdminSiteSettingRead>(
      `/api/v1/admin/settings/site/logo?revision=${encodeURIComponent(String(revision))}`,
      { method: "DELETE" },
    ),
  registrationSetting: () =>
    apiRequest<AdminRegistrationSettingRead>("/api/v1/admin/settings/registration"),
  updateRegistrationSetting: (input: RegistrationSettingPatchIn) =>
    apiRequest<AdminRegistrationSettingRead>("/api/v1/admin/settings/registration", {
      method: "PATCH",
      body: jsonBody(input),
    }),
};
