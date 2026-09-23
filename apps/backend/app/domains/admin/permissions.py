from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    code: str
    name: str
    description: str
    assignable_to_roles: bool = True


class PermissionCode(StrEnum):
    BRANDS_READ = "brands:read"
    BRANDS_CREATE = "brands:create"
    BRANDS_UPDATE = "brands:update"
    SPEC_ATTRIBUTES_READ = "spec-attributes:read"
    SPEC_ATTRIBUTES_CREATE = "spec-attributes:create"
    SPEC_ATTRIBUTES_UPDATE = "spec-attributes:update"
    PAYMENTS_READ = "payments:read"
    RECONCILIATION_READ = "reconciliation:read"
    MEMBERS_READ = "members:read"
    MEMBER_LEVELS_READ = "member-levels:read"
    MEMBER_LEVELS_CREATE = "member-levels:create"
    MEMBER_LEVELS_UPDATE = "member-levels:update"
    MEMBER_LEVEL_CONDITIONS_READ = "member-level-conditions:read"
    MEMBER_LEVEL_CONDITIONS_CREATE = "member-level-conditions:create"
    MEMBER_LEVEL_CONDITIONS_UPDATE = "member-level-conditions:update"
    MEMBER_PRICE_RULES_READ = "member-price-rules:read"
    MEMBER_PRICE_RULES_CREATE = "member-price-rules:create"
    MEMBER_PRICE_RULES_UPDATE = "member-price-rules:update"
    SETTINGS_ORDER_SHIPPING_READ = "settings:order-shipping:read"
    SETTINGS_ORDER_SHIPPING_UPDATE = "settings:order-shipping:update"
    SETTINGS_COMMISSION_CONTROL_READ = "settings:commission-control:read"
    SETTINGS_COMMISSION_CONTROL_UPDATE = "settings:commission-control:update"
    COMMISSION_POLICIES_READ = "commission-policies:read"
    COMMISSION_POLICIES_CREATE = "commission-policies:create"
    COMMISSION_POLICIES_UPDATE = "commission-policies:update"
    COMMISSION_POLICIES_PUBLISH = "commission-policies:publish"
    COMMISSIONS_READ = "commissions:read"
    WALLETS_READ = "wallets:read"
    POINTS_READ = "points:read"
    POINTS_ADJUST = "points:adjust"
    ORDERS_EXPORT = "orders:export"
    REFUNDS_EXPORT = "refunds:export"
    WITHDRAWALS_EXPORT = "withdrawals:export"
    PAYMENTS_EXPORT = "payments:export"
    RECONCILIATION_EXPORT = "reconciliation:export"
    MEMBERS_EXPORT = "members:export"
    COMMISSIONS_EXPORT = "commissions:export"
    WALLETS_EXPORT = "wallets:export"
    PRODUCT_CATEGORIES_READ = "product-categories:read"
    PRODUCT_CATEGORIES_CREATE = "product-categories:create"
    PRODUCT_CATEGORIES_UPDATE = "product-categories:update"
    PRODUCTS_READ = "products:read"
    PRODUCTS_CREATE = "products:create"
    PRODUCTS_UPDATE = "products:update"
    INVENTORY_READ = "inventory:read"
    INVENTORY_ADJUST = "inventory:adjust"
    SHIPPING_READ = "shipping:read"
    SHIPPING_CREATE = "shipping:create"
    SHIPPING_UPDATE = "shipping:update"
    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_DELETE = "users:delete"
    USERS_RESTORE = "users:restore"
    USERS_CREDENTIALS_RESET = "users:credentials:reset"
    USERS_SESSIONS_READ = "users:sessions:read"
    USERS_SESSIONS_REVOKE = "users:sessions:revoke"
    ADMINS_READ = "admins:read"
    ADMINS_CREATE = "admins:create"
    ADMINS_UPDATE = "admins:update"
    ADMINS_SUPERUSER_CHANGE = "admins:superuser:change"
    ADMINS_CREDENTIALS_RESET = "admins:credentials:reset"
    ADMINS_ROLES_ASSIGN = "admins:roles:assign"
    ADMINS_SESSIONS_READ = "admins:sessions:read"
    ADMINS_SESSIONS_REVOKE = "admins:sessions:revoke"
    ROLES_READ = "roles:read"
    ROLES_CREATE = "roles:create"
    ROLES_UPDATE = "roles:update"
    ROLES_DELETE = "roles:delete"
    ROLES_PERMISSIONS_ASSIGN = "roles:permissions:assign"
    PERMISSIONS_READ = "permissions:read"
    SECURITY_LOGIN_EVENTS_READ = "security:login-events:read"
    SECURITY_AUDIT_EVENTS_READ = "security:audit-events:read"
    SYSTEM_OVERVIEW_READ = "system:overview:read"
    SYSTEM_REQUEST_LOGS_READ = "system:request-logs:read"
    ASSETS_READ = "assets:read"
    ASSETS_DELETE = "assets:delete"
    SETTINGS_SITE_READ = "settings:site:read"
    SETTINGS_SITE_UPDATE = "settings:site:update"
    SETTINGS_REGISTRATION_READ = "settings:registration:read"
    SETTINGS_REGISTRATION_UPDATE = "settings:registration:update"
    FULFILLMENTS_SHIP = "fulfillments:ship"
    ORDERS_READ = "orders:read"
    ORDERS_ACCEPT = "orders:accept"
    REFUNDS_READ = "refunds:read"
    FULFILLMENTS_DELIVER_VIRTUAL = "fulfillments:deliver-virtual"
    REFUNDS_REVIEW = "refunds:review"
    RECONCILIATION_IMPORT = "reconciliation:import"
    RECONCILIATION_RESOLVE = "reconciliation:resolve"
    WITHDRAWALS_READ = "withdrawals:read"
    WITHDRAWALS_REVIEW = "withdrawals:review"
    WITHDRAWALS_COMPLETE_MANUAL = "withdrawals:complete-manual"


PERMISSION_CATALOG: tuple[PermissionDefinition, ...] = (
    PermissionDefinition("brands:read", "查看品牌", "查看商品品牌资料"),
    PermissionDefinition("brands:create", "创建品牌", "创建商品品牌及图片引用"),
    PermissionDefinition("brands:update", "修改品牌", "修改品牌资料和启用状态"),
    PermissionDefinition("spec-attributes:read", "查看属性库", "查看公共属性及标准候选值"),
    PermissionDefinition("spec-attributes:create", "创建公共属性", "创建公共销售或描述属性"),
    PermissionDefinition("spec-attributes:update", "修改公共属性", "修改公共属性及标准候选值"),
    PermissionDefinition("payments:read", "查看支付记录", "查询支付意图与渠道状态"),
    PermissionDefinition("reconciliation:read", "查看对账记录", "查询渠道对账匹配及差异"),
    PermissionDefinition("members:read", "查看会员档案", "查询会员等级及首次推荐关系"),
    PermissionDefinition("member-levels:read", "查看会员等级", "查看会员等级与默认折扣"),
    PermissionDefinition("member-levels:create", "创建会员等级", "创建会员等级与默认折扣"),
    PermissionDefinition("member-levels:update", "修改会员等级", "修改会员等级、启停与默认折扣"),
    PermissionDefinition("member-level-conditions:read", "查看会员资格条件", "查看会员等级自动资格条件"),
    PermissionDefinition("member-level-conditions:create", "创建会员资格条件", "创建会员等级资格条件"),
    PermissionDefinition("member-level-conditions:update", "修改会员资格条件", "修改会员等级资格条件与启停"),
    PermissionDefinition("member-price-rules:read", "查看会员价格规则", "查看 SKU、商品和分类会员价格规则"),
    PermissionDefinition("member-price-rules:create", "创建会员价格规则", "创建会员价格规则"),
    PermissionDefinition("member-price-rules:update", "修改会员价格规则", "修改会员价格规则与启停"),
    PermissionDefinition("settings:order-shipping:read", "查看平台运费", "查看统一平台运费配置"),
    PermissionDefinition("settings:order-shipping:update", "修改平台运费", "修改统一平台运费配置"),
    PermissionDefinition("settings:commission-control:read", "查看分佣总开关", "查看全平台分佣总开关"),
    PermissionDefinition("settings:commission-control:update", "修改分佣总开关", "修改全平台分佣总开关"),
    PermissionDefinition("commission-policies:read", "查看分佣政策", "查看分佣政策、来源规则与三级矩阵"),
    PermissionDefinition("commission-policies:create", "创建分佣政策", "创建分佣政策草稿"),
    PermissionDefinition("commission-policies:update", "修改分佣政策", "修改草稿政策及其规则矩阵"),
    PermissionDefinition("commission-policies:publish", "发布分佣政策", "发布草稿并归档旧生效政策"),
    PermissionDefinition("commissions:read", "查看佣金", "查询两级佣金及追回状态"),
    PermissionDefinition("wallets:read", "查看钱包", "查询双轨钱包及不可变流水"),
    PermissionDefinition("points:read", "查看积分", "查询积分账户和不可变积分流水"),
    PermissionDefinition("points:adjust", "调整积分", "人工授予或冲销积分并记录审计"),
    PermissionDefinition("orders:export", "导出订单", "导出选中订单摘要"),
    PermissionDefinition("refunds:export", "导出退款", "导出选中退款申请"),
    PermissionDefinition("withdrawals:export", "导出提现", "导出选中提现申请"),
    PermissionDefinition("payments:export", "导出支付", "导出选中支付记录"),
    PermissionDefinition("reconciliation:export", "导出对账", "导出选中对账记录"),
    PermissionDefinition("members:export", "导出会员", "导出选中会员及推荐关系"),
    PermissionDefinition("commissions:export", "导出佣金", "导出选中佣金记录"),
    PermissionDefinition("wallets:export", "导出钱包", "导出选中钱包余额摘要"),
    PermissionDefinition("orders:read", "查看订单", "查看订单列表、成交快照和履约状态"),
    PermissionDefinition("orders:accept", "接单", "确认已付款订单进入履约处理"),
    PermissionDefinition("refunds:read", "查看退款", "查看退款申请及审核版本"),
    PermissionDefinition("product-categories:read", "查看商品分类", "查看商品分类树"),
    PermissionDefinition("product-categories:create", "创建商品分类", "创建三级商品分类"),
    PermissionDefinition("product-categories:update", "修改商品分类", "修改分类资料、层级和启停"),
    PermissionDefinition("products:read", "查看商品", "查看商品资料和全部 SKU"),
    PermissionDefinition("products:create", "创建商品", "创建商品、稳定 SKU 与零库存账户"),
    PermissionDefinition("products:update", "修改商品", "修改商品资料、SKU 和上下架"),
    PermissionDefinition("inventory:read", "查看库存", "查看 SKU 库存与调整流水"),
    PermissionDefinition("inventory:adjust", "调整库存", "按幂等请求调整库存并记录流水"),
    PermissionDefinition("shipping:read", "查看运费模板", "查看运费模板和试算运费"),
    PermissionDefinition("shipping:create", "创建运费模板", "创建地区运费模板"),
    PermissionDefinition("shipping:update", "修改运费模板", "修改运费规则与启停"),
    PermissionDefinition("users:read", "查看用户", "查看用户列表和详情"),
    PermissionDefinition("users:create", "创建用户", "创建普通用户账户"),
    PermissionDefinition("users:update", "修改用户", "修改用户资料和状态"),
    PermissionDefinition("users:delete", "删除用户", "将用户账户移入回收站"),
    PermissionDefinition("users:restore", "恢复用户", "从回收站恢复软删除用户账户"),
    PermissionDefinition("users:credentials:reset", "重置用户密码", "重置用户登录密码"),
    PermissionDefinition("users:sessions:read", "查看用户会话", "查看用户设备与会话"),
    PermissionDefinition("users:sessions:revoke", "撤销用户会话", "撤销用户一个或全部会话"),
    PermissionDefinition("admins:read", "查看管理员", "查看管理员列表和详情"),
    PermissionDefinition("admins:create", "创建管理员", "创建后台管理员"),
    PermissionDefinition("admins:update", "修改管理员资料与状态", "修改管理员资料和启用状态"),
    PermissionDefinition(
        "admins:superuser:change",
        "设为超级管理员",
        "仅超级管理员可授予或取消其他管理员的超级管理员身份",
        assignable_to_roles=False,
    ),
    PermissionDefinition("admins:credentials:reset", "重置管理员密码", "重置管理员登录密码"),
    PermissionDefinition("admins:roles:assign", "分配管理员角色", "修改管理员角色集合"),
    PermissionDefinition("admins:sessions:read", "查看管理员会话", "查看管理员会话"),
    PermissionDefinition("admins:sessions:revoke", "撤销管理员会话", "撤销管理员全部会话"),
    PermissionDefinition("roles:read", "查看角色", "查看角色和授权"),
    PermissionDefinition("roles:create", "创建角色", "创建后台角色"),
    PermissionDefinition("roles:update", "修改角色", "修改角色资料和状态"),
    PermissionDefinition("roles:delete", "删除角色", "删除未被使用的角色"),
    PermissionDefinition("roles:permissions:assign", "分配角色权限", "修改角色权限集合"),
    PermissionDefinition("permissions:read", "查看权限目录", "查看源码权限目录"),
    PermissionDefinition("security:login-events:read", "查看登录事件", "查看登录安全事件"),
    PermissionDefinition("security:audit-events:read", "查看审计事件", "查看高风险操作审计"),
    PermissionDefinition("system:overview:read", "查看系统概览", "查看系统健康状态、运行配置摘要和业务遥测"),
    PermissionDefinition("system:request-logs:read", "查看请求日志", "查看启用后的请求元数据"),
    PermissionDefinition("assets:read", "查看文件资产", "查看统一文件与多媒体资产列表"),
    PermissionDefinition("assets:delete", "删除文件资产", "删除文件资产及其存储对象"),
    PermissionDefinition("settings:site:read", "查看站点设置", "查看 Web 公共站点资料和 LOGO"),
    PermissionDefinition("settings:site:update", "修改站点设置", "修改 Web 公共站点资料和 LOGO"),
    PermissionDefinition("settings:registration:read", "查看注册设置", "查看 Web 公开注册开关"),
    PermissionDefinition("settings:registration:update", "修改注册设置", "修改 Web 公开注册开关"),
    PermissionDefinition("fulfillments:ship", "订单发货", "对已付款实物订单填写物流发货信息"),
    PermissionDefinition("fulfillments:deliver-virtual", "完成虚拟交付", "对已付款虚拟订单登记交付引用"),
    PermissionDefinition("refunds:review", "审核退款", "审核通过或驳回用户退款申请"),
    PermissionDefinition("reconciliation:import", "导入支付对账", "导入渠道账单并记录匹配或差异"),
    PermissionDefinition("reconciliation:resolve", "处置对账差异", "人工确认并记录对账差异处置原因"),
    PermissionDefinition("withdrawals:read", "查看提现申请", "查看待审核的佣金钱包提现申请"),
    PermissionDefinition("withdrawals:review", "审核提现申请", "审核通过或驳回佣金钱包提现申请"),
    PermissionDefinition("withdrawals:complete-manual", "确认线下提现", "确认线下转账完成并结清提现冻结余额"),
)

PERMISSION_CODES = frozenset(item.code for item in PERMISSION_CATALOG)
ROLE_ASSIGNABLE_PERMISSION_CODES = frozenset(item.code for item in PERMISSION_CATALOG if item.assignable_to_roles)
CATALOG_VERSION = "2026-09-23.1"

__all__ = [
    "CATALOG_VERSION",
    "PERMISSION_CATALOG",
    "PERMISSION_CODES",
    "ROLE_ASSIGNABLE_PERMISSION_CODES",
    "PermissionCode",
    "PermissionDefinition",
]
