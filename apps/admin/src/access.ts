import type { AdminInitialState } from "./app";

export default function access(initialState?: AdminInitialState) {
  const admin = initialState?.currentAdmin;
  const has = (permission: string) => Boolean(admin && (admin.is_superuser || admin.permissions.includes(permission)));
  return {
    canCatalog: ["products:read", "product-categories:read", "shipping:read"].some(has),
    canProducts: has("products:read"),
    canCategories: has("product-categories:read"),
    canShipping: has("shipping:read"),
    canTrade: ["orders:read", "refunds:read", "payments:read", "reconciliation:read"].some(has),
    canPayments: has("payments:read"),
    canReconciliation: has("reconciliation:read"),
    canMembers: has("members:read"),
    canCommissions: has("commissions:read"),
    canWallets: has("wallets:read"),
    canOrders: has("orders:read"),
    canRefunds: has("refunds:read"),
    canDistribution: ["withdrawals:read", "members:read", "commissions:read", "wallets:read"].some(has),
    canWithdrawals: has("withdrawals:read"),
    canUsers: Boolean(admin && (admin.is_superuser || admin.permissions.includes("users:read"))),
    canAdmins: Boolean(admin && (admin.is_superuser || admin.permissions.includes("admins:read"))),
    canRoles: Boolean(admin && (admin.is_superuser || admin.permissions.includes("roles:read"))),
    canAssets: Boolean(admin && (admin.is_superuser || admin.permissions.includes("assets:read"))),
    canSettings: Boolean(admin && (admin.is_superuser || [
      "settings:site:read",
      "settings:registration:read",
    ].some((permission) => admin.permissions.includes(permission)))),
    canSystem: Boolean(admin && (admin.is_superuser || admin.permissions.includes("system:overview:read"))),
    canSecurity: Boolean(admin && (admin.is_superuser || [
      "security:login-events:read",
      "security:audit-events:read",
      "system:request-logs:read",
    ].some((permission) => admin.permissions.includes(permission)))),
  };
}
