import type { AdminRead } from "@pinjie/api-client";
import { createContext, useContext } from "react";

// 全局管理员身份上下文
export const AdminContext = createContext<AdminRead | null>(null);

// 获取当前登录管理员信息，未初始化时抛出异常
export function useCurrentAdmin(): AdminRead {
  const admin = useContext(AdminContext);
  if (!admin) throw new Error("AdminContext is unavailable");
  return admin;
}

// 判定管理员是否具备指定权限或超级管理员身份
export function canAccess(admin: AdminRead, permission: string): boolean {
  return admin.is_superuser || admin.permissions.includes(permission);
}
