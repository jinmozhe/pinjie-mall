import { describe, expect, it } from "vitest";

import access from "./access";
import type { AdminInitialState } from "./app";

const settings = {} as AdminInitialState["settings"];
const commerceDenied = {
  canCatalog: false, canProducts: false, canCategories: false, canShipping: false,
  canBrands: false, canSpecAttributes: false, canInventory: false,
  canTrade: false, canPayments: false, canReconciliation: false, canMembers: false,
  canCommissions: false, canWallets: false, canOrders: false, canRefunds: false,
  canDistribution: false, canWithdrawals: false,
  canMemberLevels: false, canMemberPrices: false, canPoints: false,
  canPolicies: false, canReferralNetwork: false,
};

function state(permissions: string[] = [], isSuperuser = false): AdminInitialState {
  return {
    settings,
    currentAdmin: {
      id: "01900000-0000-7000-8000-000000000001",
      username: "permission-admin",
      display_name: null,
      is_active: true,
      is_superuser: isSuperuser,
      roles: [],
      permissions,
      created_at: "2026-08-22T00:00:00Z",
      updated_at: "2026-08-22T00:00:00Z",
    },
  };
}

describe("admin access mapping", () => {
  it("denies every protected area without a current administrator", () => {
    expect(access({ settings })).toEqual({
      ...commerceDenied,
      canMembership: false,
      canUsers: false,
      canFinance: false,
      canSystemMgmt: false,
      canAdmins: false,
      canRoles: false,
      canAssets: false,
      canSettings: false,
      canOps: false,
      canSystem: false,
      canSecurity: false,
    });
  });

  it.each(["security:login-events:read", "security:audit-events:read", "system:request-logs:read"])(
    "allows the security workspace for %s",
    (permission) => {
      expect(access(state([permission])).canSecurity).toBe(true);
    },
  );

  it("maps ordinary read permissions and grants every area to superusers", () => {
    expect(access(state(["users:read", "admins:read", "roles:read", "assets:read", "system:overview:read", "settings:site:read"]))).toEqual({
      ...commerceDenied,
      canMembership: true,
      canUsers: true,
      canFinance: false,
      canSystemMgmt: true,
      canAdmins: true,
      canRoles: true,
      canAssets: true,
      canSettings: true,
      canOps: true,
      canSystem: true,
      canSecurity: false,
    });
    expect(access(state([], true))).toEqual({
      canCatalog: true, canProducts: true, canCategories: true, canShipping: true,
      canBrands: true, canSpecAttributes: true, canInventory: true,
      canTrade: true, canPayments: true, canReconciliation: true, canMembers: true,
      canCommissions: true, canWallets: true, canOrders: true, canRefunds: true,
      canDistribution: true, canWithdrawals: true,
      canMemberLevels: true, canMemberPrices: true, canPoints: true,
      canPolicies: true, canReferralNetwork: true,
      canMembership: true,
      canFinance: true,
      canSystemMgmt: true,
      canOps: true,
      canUsers: true,
      canAdmins: true,
      canRoles: true,
      canAssets: true,
      canSettings: true,
      canSystem: true,
      canSecurity: true,
    });
  });
});
