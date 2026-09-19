# 全栈 Monorepo 架构与 1Panel 部署规划方案

> 历史原始方案：本文记录 2026-08-10 的规划背景和当时评估过的技术选型，不代表当前 Admin 实现。当前 Admin 技术栈、运行入口和迁移后的约束以 [ADR 0011：Admin 采用 Ant Design Pro v6 与 Umi Max](../adr/0011-Admin采用AntDesignProV6与UmiMax决策.md)、`apps/admin/AGENTS.md` 和 [Admin 本地运行与验证排障手册](../operations/admin-local-development-and-validation-troubleshooting.md) 为准。
>
> 本文中的 `apps/frontend`、Vite Admin、Bearer Token、本地 Token Store、电商领域、自动迁移、应用商店数据库和日志文件挂载均为历史候选方案，不能作为当前实现或生产操作依据。当前事实以 [项目结构](project-structure.md)、[认证授权边界](authentication-authorization.md)、[模块边界](module-boundaries.md)、[容器运行手册](../operations/container-build-and-run.md)和 [1Panel 单机生产运行手册](../operations/1panel-production-runbook.md) 为准。

## 1. 方案背景与概述

随着业务场景的发展，后端骨架 `pinjie-standard` 需要扩展为包含 B 端后台管理前端与 C 端用户展示前端的全栈应用形态。为了保证代码的高效复用、类型安全以及部署运维的便利性，系统规划采用全栈 Monorepo 模式进行组织。

同时，考虑到线上服务器环境已安装并运行 1Panel (v2.2.4) 运维管理面板，本规划方案深度结合了 1Panel 的核心特性（如内置 OpenResty 网关、ACME 自动化 SSL 证书管理、应用商店 PostgreSQL/Redis 托管、可视化计划任务与日志管理），进行了架构上的精简与针对性适配。

本方案专门针对**真实电商业务系统**进行了领域建模，不仅包含了通用的 SaaS 后端骨架能力，还完整长出了电商心脏领域的架构与前后端 1:1 心智模型对齐，是一份可以直接指导实战开发的全栈架构宪法。

## 2. 官方全栈模板 (full-stack-fastapi-template) 功能参考对照

本方案在设计过程中，深入参考了官方全栈模板 [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) 的功能设计与工程实践，并结合本项目标准进行了吸收、改造和裁剪。

### 2.1 继承与吸收的核心功能

- **认证与账号管理流程**：完整保留官方模板中的 OAuth2 密码模式换码 (`/login/access-token`)、登录验证测试端点 (`/login/test-token`)、邮件令牌密码找回 (`password-recovery`) 和重置 (`reset-password`)，以及当前登录用户资料查询与修改 (`/users/me`)。
- **前后端 SDK 自动化生成**：吸收官方模板通过 `openapi-ts` 根据后端导出 `openapi.json` 自动构建前端强类型请求 SDK 的机制，保障全栈类型安全。
- **自动化测试校验理念**：继承官方模板在 CI 流程中通过 Pytest 运行自动化端点测试与单元测试的设计。
- **本地发件拦截测试**：参考官方模板拦截测试邮件的理念，在本地开发环境提供 Mailpit/Mailcatcher 的轻量工具配置，便于调试发件逻辑。

### 2.2 架构升级与本地化改造

- **后端架构升级**：官方模板使用 SQLModel 和平铺的 `crud.py` 结构；本项目升级为 **SQLAlchemy 2.0 async + Pydantic v2 强解耦的四层领域驱动架构**（Router 到 Service 到 Repository 到 Model），并强制采用 `ResponseModel[T]` 统一响应信封与严格的 Service 事务边界。
- **全栈组织形态升级**：官方模板使用简单的 `backend/` 和 `frontend/` 单应用结构；本项目升级为多端拆分的 **全栈 Monorepo 模式**（`apps/backend`、`apps/admin`、`apps/frontend` 以及 `packages/api-client`）。

### 2.3 针对 1Panel 弃用与剔除的组件

- **Traefik 网关与自建证书**：官方模板硬编码了 Traefik 容器；本项目在线上彻底放弃 Traefik，全权交由 1Panel OpenResty 网关管理。
- **仓库自带生产数据库容器**：官方模板通过 Compose 运行生产数据库；本项目放弃此做法，生产环境直接连接 1Panel 应用商店托管并享受自动备份的 PostgreSQL/Redis 实例。

## 3. 核心架构规划：全栈 Monorepo 模式

### 3.1 目录结构设计 (电商领域前后端 1:1 心智模型对齐)

仓库采用基于 `pnpm workspace` 的全栈 Monorepo 目录划分，结合现代前端最高级的垂直领域切片架构（Feature-Sliced Design），实现前后端电商领域的心智模型完全对齐：

```text
/ (仓库根目录)
├── apps/                        # 业务应用层（极简规范命名）
│   ├── backend/                 # [核心] FastAPI 标准后端（领域驱动架构）
│   │   ├── app/
│   │   │   ├── api/             # 全局依赖注入辅助 (deps.py)
│   │   │   ├── core/            # 跨领域基础设施 (config, response, exceptions, middleware, audit, security, cache_keys)
│   │   │   ├── db/              # 数据库引擎与基础设施 (session.py, base.py, models/)
│   │   │   ├── domains/         # 高内聚领域模块 (Router -> Service -> Repository -> Model)
│   │   │   │   ├── auth/        # 1. 认证领域 (登录、Token 刷新、密码重置)
│   │   │   │   ├── users/       # 2. 用户领域 (个人中心、账号基础能力)
│   │   │   │   ├── admin/       # 3. B 端 RBAC 权限领域 (管理员、角色、菜单)
│   │   │   │   ├── system/      # 4. 系统工具领域 (健康检查、日志、配置)
│   │   │   │   ├── products/    # 5. [电商心脏] 商品领域 (SPU/SKU、分类、规格属性)
│   │   │   │   ├── inventory/   # 6. [电商心脏] 库存领域 (乐观锁/Redis锁扣减、预扣存)
│   │   │   │   ├── cart/        # 7. [电商心脏] 购物车领域 (后端持久化、登录双轨合并)
│   │   │   │   ├── orders/      # 8. [电商心脏] 订单领域 (订单生命周期状态机、定时超时取消)
│   │   │   │   ├── payment/     # 9. [电商心脏] 支付领域 (微信/支付宝回调幂等处理)
│   │   │   │   ├── promotions/  # 10. [电商心脏] 促销领域 (优惠券、满减活动)
│   │   │   │   └── reviews/     # 11. [电商心脏] 评价领域 (商品评价、评分晒图)
│   │   │   ├── services/        # 跨领域编排 Workflows / UseCases
│   │   │   └── api_router.py    # 统一路由挂载入口 (APIRouter prefix & tags)
│   │   ├── alembic/             # Alembic 数据库迁移 (env.py, versions/*.py)
│   │   ├── scripts/             # 种子数据填充与维护脚本 (seed_admin.py, sync_permissions.py)
│   │   ├── tests/               # Pytest 自动化测试套件 (conftest.py, test_app_smoke.py)
│   │   ├── Dockerfile           # 多阶段构建 Dockerfile
│   │   └── pyproject.toml / uv.lock
│   │
│   ├── frontend/                # [C端] 用户展示/电商前端 (Next.js 14/15 垂直领域架构)
│   │   ├── src/
│   │   │   ├── app/             # [框架路由入口层] 仅做 Next.js 路由挂载 (Thin Wrapper)
│   │   │   │   ├── (auth)/      # 认证路由组 (渲染 features/auth)
│   │   │   │   ├── (user)/      # 用户路由组 (渲染 features/user)
│   │   │   │   ├── (shop)/      # 电商主路由组 (渲染 features/products, cart, checkout)
│   │   │   │   ├── (orders)/    # 订单路由组 (渲染 features/orders)
│   │   │   │   ├── layout.tsx   # 根布局组件 (包含 ErrorBoundary 与 Providers)
│   │   │   │   └── page.tsx     # 官网/电商首页
│   │   │   ├── features/        # [1:1 对齐后端的垂直业务切片层]
│   │   │   │   ├── auth/        # 认证业务领域 (login-form.tsx, use-login-api.ts)
│   │   │   │   ├── user/        # 用户业务领域 (profile-form.tsx, address-picker.tsx)
│   │   │   │   ├── products/    # 商品业务领域 (product-card.tsx, sku-selector.tsx, use-products-api.ts)
│   │   │   │   ├── cart/        # 购物车领域 (cart-drawer.tsx, cart-item.tsx, use-cart-api.ts)
│   │   │   │   ├── checkout/    # 结算履约领域 (checkout-form.tsx, payment-picker.tsx)
│   │   │   │   ├── orders/      # 订单业务领域 (order-timeline.tsx, status-badge.tsx, use-orders-api.ts)
│   │   │   │   ├── promotions/  # 促销活动领域 (coupon-input.tsx, activity-banner.tsx)
│   │   │   │   └── reviews/     # 评价业务领域 (review-list.tsx, star-rating.tsx)
│   │   │   ├── components/      # [跨领域公共 UI 层] 纯通用 UI 原子组件 (shadcn/ui button, dialog, input)
│   │   │   ├── hooks/           # 通用前端工具 Hooks (use-debounce.ts, use-media-query.ts)
│   │   │   ├── stores/          # Zustand 客户端本地持久化状态 (use-auth-store, use-cart-store)
│   │   │   ├── lib/             # 前端核心基础设施 (http.ts 拦截解包, utils.ts 工具)
│   │   │   └── types/           # 前端本地补充类型定义
│   │   ├── public/              # 静态图片与图标资源
│   │   ├── next.config.js       # Next.js 配置文件
│   │   ├── tailwind.config.js   # Tailwind CSS 配置文件
│   │   └── Dockerfile           # 生产部署 Dockerfile
│   │
│   └── admin/                   # [B端] 后台管理系统前端 (React + Vite + Ant Design 5.x)
│       ├── src/
│       │   ├── pages/           # 管理端页面路由
│       │   │   ├── login/       # 登录页
│       │   │   ├── dashboard/   # 数据大盘
│       │   │   ├── system/      # RBAC 权限与系统日志
│       │   │   ├── products/    # [电商运营] SPU/SKU 编辑、商品上下架、分类规格
│       │   │   ├── orders/      # [电商运营] 订单列表、发货履约、退款审核
│       │   │   └── promotions/  # [电商运营] 优惠券发放、满减活动配置
│       │   ├── components/      # ProComponents 与自定义通用 UI 组件
│       │   ├── hooks/           # 管理端 React Hooks
│       │   ├── stores/          # 管理端 Zustand 状态 (Admin Session)
│       │   └── lib/             # HTTP Client 与信封解包拦截器
│       ├── vite.config.ts
│       └── Dockerfile
│
├── packages/                    # 共享依赖与 SDK 导出
│   └── api-client/              # 根据 OpenAPI 规范自动生成的 TypeScript 请求 SDK
│       ├── src/                 # 导出的 API 函数与 DTO 类型定义 (models/, services/)
│       └── package.json
│
├── docker-compose.yml           # 精简应用编排（仅编排 backend、admin、frontend 容器）
├── .env.example                 # 环境变量说明模板（生产环境变量由 1Panel 注入）
├── .github/workflows/           # GitHub Actions 自动化 CI/CD 流水线 (ci-backend.yml, deploy.yml)
└── pnpm-workspace.yaml          # Monorepo Workspace 配置文件
```

### 3.2 后端 API 领域与功能扩展

后端保持已有的 Router 到 Service 到 Repository 到 Model 四层架构，继续使用 `ResponseModel[T]` 响应信封、Service 层事务控制与全局 `AppException` 拦截。在此基础上，补全以下核心领域与端点：

- **Auth 认证领域 (`app/domains/auth/`)**
  - `POST /auth/login/access-token`：使用 OAuth2 密码模式获取 JWT。
  - `POST /auth/login/test-token`：测试并返回当前登录用户信息的 `test-token` 接口。
  - `POST /auth/password-recovery/{email}`：申请密码重置邮件。
  - `POST /auth/reset-password`：校验邮件 Token 并完成密码重置。
  - `POST /auth/refresh-token`：无感刷新 Access Token。
- **Users 领域 (`app/domains/users/`)**
  - C 端个人资料修改与密码更新接口 (`GET/PATCH /users/me`)。
  - 管理员对用户账号的查询、禁用与角色绑定。
- **Admin/RBAC 领域 (`app/domains/admin/`)**
  - 管理员认证、角色权限分配、菜单路由管理与 `require_permission` 拦截依赖。
- **System 工具领域 (`app/domains/system/`)**
  - `/health-check` 健康检查探针与邮件测试端口。
- **Products 商品领域 (`app/domains/products/`)**
  - SPU 与 SKU 列表查询、详情、规格属性选择、分类树导航。
- **Inventory 库存领域 (`app/domains/inventory/`)**
  - 高并发库存防超卖扣减（乐观锁版本号/Redis锁扣减）、库存解锁与同步。
- **Cart 购物车领域 (`app/domains/cart/`)**
  - 后端持久化购物车、登录后本地与服务端双轨购物车合并。
- **Orders 订单领域 (`app/domains/orders/`)**
  - 订单生命周期状态机控制（待支付到已完成/已退款）、订单创建、超时自动取消。
- **Payment 支付领域 (`app/domains/payment/`)**
  - 微信/支付宝网关接入、支付异步回调幂等处理。
- **Promotions 促销领域 (`app/domains/promotions/`)**
  - 优惠券领取、满减活动核销。
- **Reviews 评价领域 (`app/domains/reviews/`)**
  - 商品评价发表、评分晒图与好评率统计。

### 3.3 前后端 TypeScript SDK 自动化生成联动

为规避传统开发中手动维护前端接口类型与 API 函数的低效问题，引入基于 OpenAPI 规范的 SDK 联动机制：

- 后端增加或更新路由后，通过脚本自动生成或更新根目录的 `openapi.json`。
- 前端运行根目录命令 `pnpm generate-api`，调用 OpenAPI TS Client 转换工具。
- 在 `packages/api-client/` 中自动导出类型安全的 TypeScript 请求函数，`admin` 和 `frontend` 直接引用该包。

#### api-client 版本化策略决策

`@pinjie/api-client` 当前通过 `workspace:*` 方式供 Monorepo 内部的 `apps/admin` 和 `apps/frontend` 直接引用，无需发布到 npm 仓库。**如果未来需要跨仓库消费同一套 SDK**（如微信小程序、移动端 App、外包团队），则需要配置发布到 GitHub Packages 或私有 npm 仓库（如 Verdaccio），并在后端 Schema 更新后同步打 semver 版本号发布，防止各端类型版本不一致导致仅在运行时报错的隐性问题。在此决策明确之前，`api-client` 不对外发布。

### 3.4 apps/admin 后台管理系统技术栈选型与方案对比

针对 `apps/admin` 后台管理前端，系统性地评估了目前主流的 React 方案，并确定了最终的技术落地配置。

#### 1. 多方案对比评估

| 评估维度 | 方案一：React + Vite + Ant Design 5.x + ProComponents (选中) | 方案二：Refine + Ant Design | 方案三：shadcn/ui + Tailwind CSS |
| --- | --- | --- | --- |
| **基础 UI 库** | Ant Design 5.x (MIT 免费开源) | Ant Design / 原生 UI | shadcn/ui (代码复制模式) |
| **高级 B 端组件** | `@ant-design/pro-components` (MIT 免费开源) | Refine Headless Hooks | TanStack Table 自行封装 |
| **标准 CRUD 效率** | 极高（ProTable / ProForm 几行代码完成） | 极高（自动绑 CRUD 与数据源） | 中等（需手动二次封装表格与表单） |
| **非标/定制页面自由度** | **极高（原生 React，无任何黑盒限制）** | 中等（复杂非标页面需要绕过框架） | 极高（代码 100% 掌控） |
| **上手与维护成本** | 低（团队极其熟悉，国内社区生态繁荣） | 较高（需学习 Refine 框架契约） | 中等（需维护较多基础组件代码） |
| **API SDK 接入模式** | 结合 TanStack Query 优雅包装 `api-client` | 编写 Refine Data Provider 绑定 | 结合 TanStack Query 包装 `api-client` |

#### 2. 最终落地的技术栈明细

- **核心框架与构建**：Vite + React 18/19 + TypeScript。
- **UI 组件体系**：Ant Design 5.x + `@ant-design/pro-components`（全套基于 MIT 协议免费开源）。
- **业务功能模块**：基础系统权限管理之外，涵盖电商核心运营模块（商品 SPU/SKU 管理、订单发货履约、退款审核、优惠券发放活动配置）。
- **异步数据与缓存**：TanStack Query v5 (React Query)，用于无缝包装 `packages/api-client` 的 SDK 函数。
- **全局 UI 状态**：Zustand（处理主题切换、侧边栏展开折叠等轻量状态）。
- **路由与权限**：React Router v6/v7 + 自定义权限守卫。

> **架构演进注记**：当前 B 端规划模块（商品/订单/促销/RBAC）数量可控，Vite 单体 SPA 完全能够承载，无需引入额外复杂度。当未来 B 端扩展到多个独立团队负责的模块（如运营、财务、仓储、数据分析），且各模块需要独立发布、独立版本迭代时，再考虑引入 Webpack Module Federation（模块联邦）或多 Vite 入口拆分，实现子应用独立部署、按需加载，同时保持统一的导航框架体验。

### 3.5 apps/frontend C端用户展示/电商前端技术栈选型与方案对比

针对 `apps/frontend` 侧，系统定位为**支持商品展示、品牌宣传、社交分享以及包含用户中心、购物车、订单列表等复杂交互的电商/全栈 C 端应用**。

#### 1. 核心诉求与业务特征

- **重度依赖 SEO 搜索引擎收录与首屏加载速度**：商品详情页、活动落地页与分类页必须能够被百度、Google 抓取，社交分享时需要有动态 Open Graph 元标签预览。
- **重度依赖交互与用户状态管理**：用户中心、购物车、结算与订单管理等页面，要求支持无刷新交互并优雅响应 API 数据流。

#### 2. 多方案对比评估

| 评估维度 | 方案一：Next.js (App Router) + Tailwind + shadcn/ui (选中) | 方案二：Vite + React + Tailwind + shadcn/ui | 方案三：Astro + React + Tailwind |
| --- | --- | --- | --- |
| **渲染模式** | **混合渲染 (SSG / SSR / ISR)** | 纯客户端单页渲染 (CSR) | 静态生成 / 组件岛 (SSG) |
| **SEO & 社交预览卡片** | **原生极佳** (服务端直出带有数据与 Open Graph 的 HTML) | 极差 (返回空 `<div id="root"></div>`，爬虫抓取不到内容) | **原生极佳** (纯静态预渲染) |
| **用户中心/购物车交互** | **极佳** (`"use client"` 搭配 TanStack Query 与 SDK 完美交互) | 极佳 (标准的 React 单页交互) | 中等 (在复杂用户交互和状态管理上略显繁琐) |
| **UI 视觉与动效表现** | **极致** (Tailwind CSS + shadcn/ui + Framer Motion 动效) | **极致** (Tailwind CSS + shadcn/ui + Framer Motion 动效) | 优秀 |
| **1Panel v2.2.4 部署** | 极简 (可静态 SSG 导出或作为轻量 Node.js 容器运行) | **最简单** (纯静态文件托管) | **最简单** (纯静态文件托管) |

#### 3. 最终落地的技术栈明细

- **核心框架**：Next.js 14/15 (App Router)，天然支持电商场景的混合渲染。
- **样式与 UI 系统**：Tailwind CSS + `shadcn/ui`，代码 100% 自由掌控，实现高颜值的电商视觉呈现。
- **微动效与过渡**：`Framer Motion`，用于商品图预览、购物车加购动效以及平滑页面过渡。
- **数据请求与状态管理**：`TanStack Query v5`（客户端组件中优雅包装 `packages/api-client`）+ `Zustand`（处理购物车与本地 Session）。
- **生产部署模式（强制锁定）**：`next.config.js` 中配置 `output: 'standalone'`，以 Node.js standalone 容器模式部署，禁止在容器化环境下使用 ISR（Incremental Static Regeneration）。ISR 依赖容器内部磁盘缓存，容器重建后缓存丢失会导致所有页面冷重启、性能抖动；商品详情页等数据实时性要求高的页面统一使用 SSR 模式，结合后端 Redis 缓存层保障响应性能。

### 3.6 前端架构分层与全局异常治理规范

为了与后端的"Router 到 Service 到 Repository 到 Model 四层强边界"及统一响应信封保持一致，针对 `apps/frontend` 和 `apps/admin` 制定了强约束的前端开发规范。

#### 1. 前端四层强边界架构

```text
路由接入层 (Page / Route Layer)
       │
       ▼
视图 UI 层 (Component / View Layer)
       │
       ▼
业务/数据服务层 (Feature / Hook Layer)
       │
       ▼
接口与数据协议层 (API Client / Package Layer)
```

- **路由接入层 (Page / Route Layer)**：位于 `src/app/` 目录，处理 Next.js App Router 路由参数、服务端数据预拉取 (Server Components) 与 SEO 元数据 `generateMetadata`。`page.tsx` 只做路由入口挂载（Thin Wrapper），只有数行代码，禁止手写长串逻辑。
- **视图 UI 层与业务服务层 (Feature / View Layer)**：位于 `src/features/{domain}/` 目录，真正承载高内聚的业务领域资产（如 `products/`, `cart/`, `orders/` 领域的组件、Hook、Types）。严格区分 Server Components 与 Client Components。
- **通用 UI 层 (Common Component Layer)**：位于 `src/components/` 目录，存放跨领域的纯通用 UI 原子组件（如 `shadcn/ui` 的 button、dialog）和全局组件（header、footer）。
- **接口与数据协议层 (API Client Layer)**：位于 `src/lib/http.ts` 及 `packages/api-client`，负责请求响应信封自动拆包与 401/403/500 分级拦截。

#### 2. 前端领域隔离与代码所有权边界规则 (Code Ownership Guardrail)

为保障 `src/features/` 架构的持久健康，强制约定：**业务切片 `features/{domain}/` 之间严禁直接跨域隐式耦合或循环引用具体实现**。任何跨领域的共享必须通过 `src/components/` 通用组件、`src/stores/` 全局状态或 `packages/api-client` 类型契约进行解耦。

#### 3. 后端 ResponseModel[T] 信封自动解包规范 (Response Unwrapper)

前端 HTTP 客户端拦截器统一对接后端的响应信封：

- **自动解包机制**：HTTP Client 拦截器收到后端响应后，校验 HTTP 状态码与业务 `code`。若 `code == 200`（成功），拦截器**自动解包提取 `.data` 字段透传给上层**，组件层获取到的直接就是强类型泛型 `T`，无需在每个页面中重复手动编写 `.data.data`。
- **业务异常抛出**：若 `code != 200`，拦截器自动将其判定为业务异常 `BusinessError` 并抛出，附带后端返回的 `message` 与 `request_id`。

#### 4. 全局异常分级拦截与防护 (Global Interceptors & Error Boundary)

- **401 Unauthorized (Token 过期)**：触发无感 Refresh Token 逻辑；若刷新失败，自动清理本地 Session 缓存，优雅跳转至登录页，并弹出 Toast 提示"登录状态失效"。
- **403 Forbidden (无权限)**：统一弹窗 Toast 提示"无权限访问该资源"。
- **500 / 网络中断**：自动展示轻量 Notification / Toast 提示，并记录带有后端 `request_id` 的客户端错误日志，便于排查追踪。
- **前端防白屏兜底**：在 React 组件树根部与关键路由节点挂载 `ErrorBoundary`，当出现未捕获的渲染运行时异常时，展示友好的降级倒塌页面，杜绝全屏白屏。

### 3.7 Zustand 本地状态划分与全栈 TypeScript 类型流转规范

针对前端的数据存储与类型绑定，明确区分"服务器接口数据"与"客户端本地状态"的处理边界，并确立自动化的类型流转规范。

#### 1. Zustand 客户端本地状态划分 (`src/stores/`)

前端不使用全局状态库（如 Zustand / Redux）保存所有接口返回的数据，接口数据统一交由各个 `src/features/{domain}/` 中的 `TanStack Query` Hooks 管理。Zustand 仅在 `src/stores/` 目录下按模块管理纯粹的客户端本地持久化状态：

- **`useAuthStore` (`src/stores/use-auth-store.ts`)**：
  - **保存数据**：`accessToken`（JWT 令牌）、`currentUser`（当前登录用户脱敏概要信息）、`isLoggedIn`（登录状态标记）。
  - **应用场景**：顶部导航栏实时显示用户头像昵称、请求拦截器读取 Token 塞入 `Authorization` 请求头、路由守卫鉴权。
- **`useCartStore` (`src/stores/use-cart-store.ts`)**：
  - **保存数据**：`cartItems`（未登录/本地离线购物车列表）、`isDrawerOpen`（购物车抽屉显隐控制）。
  - **应用场景**：全站任意页面点击"加入购物车"触发抽屉弹窗、顶部购物车图标实时显示选购数量 Badge、配合 `persist` 中间件存储至 `localStorage` 实现离线恢复。
- **`useUIStore` (`src/stores/use-ui-store.ts`)**：
  - **保存数据**：`theme`（亮色/暗黑主题模式）、`isMobileMenuOpen`（移动端侧边栏开启状态）。
  - **应用场景**：跨页面的纯客户端 UI 交互协同。

#### 2. 全栈 TypeScript 类型自动化流转链路

在 Monorepo 模式下，前端实现 **零手动书写 API 接口类型** 的自动化流转链路：

```text
[后端 Pydantic Schema / ORM Models]
                │
                ▼ (uv run alembic / python scripts)
   [后端导出生成 openapi.json]
                │
                ▼ (pnpm generate-api 自动解析)
[packages/api-client (导出强类型 API SDK & DTO Types)]
                │
                ▼ (import type { ProductDetailDto } from "@pinjie/api-client")
[src/features/{domain}/ (TanStack Query 包装 API 消费 Hook)]
                │
                ▼ (const { data: product } = useProductDetail(id))
[src/app/ & src/features/ (页面与 View 组件直接拿到强类型数据，无需二次断言)]
```

### 3.8 企业级全栈开发红线与业务机制规范

为了让本规划文档成为可以直接指导实战开发的全栈架构宪法，特制定以下针对后端数据库、电商四大核心业务机制以及前端数据状态的强约束红线：

#### 1. 后端数据库与事务控制强约束红线

- **事务控界红线**：只有 Service 层的 Public 写方法允许显式提交事务 (`commit`)；Repository 仓储层、Helper 方法以及 Private 私有方法**绝对禁止调用 `commit`**，只允许 `flush`。
- **异步关联加载红线**：SQLAlchemy 2.0 async 查询如果需要访问关联模型（如 Order 加载 OrderItem），必须显式在查询中配置 `selectinload` 或 `joinedload`，严禁在响应序列化阶段触发延迟懒加载，从根本上杜绝 `MissingGreenlet` 异常。
- **数据模型强约束**：主键统一使用 UUID v7，时间统一使用 `DateTime(timezone=True)`，JSON 强约束使用 PostgreSQL `JSONB`，数据库表及所有字段**必须显式声明中文 `comment` 注释**。
- **异常分层治理红线**：Service 及以下分层统一只抛出 `AppException` 业务异常，严禁在 Service 或 Repository 中抛出 FastAPI 的 `HTTPException`。

#### 2. 电商四大核心业务机制防御红线

- **`inventory` 高并发防超卖机制**：库存扣减严禁使用无锁原语更新。高并发下必须统一采用数据库乐观锁（`version` 字段校验）或者 Redis 分布式锁/预扣减机制，保证库存安全。
- **`payment` 异步回调幂等性机制**：微信/支付宝支付网关的回调接口，必须根据第三方支付单号 (`out_trade_no`) 在 Redis 或数据库中做**强幂等校验**，防止重复上报导致状态乱序。
- **`cart` 双轨购物车合并机制**：用户未登录时使用 Zustand + `localStorage`；用户登录成功瞬间，自动触发双轨合并接口，将本地暂存的购物车商品增量追加落库。
- **`orders` 状态机与超时自动取消**：订单生命周期严格遵循单向状态机流转（待支付到已支付到待发货到已发货到已完成/已退款）。超过支付时限由定时任务自动触发状态重置与库存解锁。

#### 3. 前端数据状态隔离红线

- **状态管理边界红线**：严禁将接口返回的服务端数据（如商品列表、订单详情）塞入 Zustand 充当全局缓存。接口数据全权交由 `TanStack Query` 管理（自动缓存与失效重刷）；Zustand 仅在 `src/stores/` 目录下保存 Token、购物车暂存与 UI 主题等真正的客户端本地持久化状态。

## 4. 1Panel v2.2.4 对比分析与选型决策

在设计全栈 Monorepo 部署方案时，深入核对了 1Panel v2.2.4 面板的能力，对传统全栈模板中的部署部分进行了全面瘦身与去重复化设计。

### 4.1 冲突与重叠功能对比

| 部署需求 | 传统全栈模板方案 | 1Panel v2.2.4 内置能力 | 决策与选型理由 |
| --- | --- | --- | --- |
| 网关与反向代理 | 仓库内挂载 Traefik 容器并维护 `traefik.yml` | 内置 OpenResty 站点管理，支持可视化的路由转发、WAF 与伪静态 | **完全移除 Traefik 容器**。Traefik 会与 1Panel OpenResty 抢占 80/443 端口造成端口冲突。全量路由转发交由 1Panel OpenResty 处理。 |
| SSL 证书续签 | Traefik 配置 Let's Encrypt ACME | 内置 ACME 自动化证书工具，支持自动申请和定时自动续订 | **彻底移除仓库自建证书逻辑**。直接在 1Panel 站点管理中一键开启自动续期。 |
| 数据库托管 | 在 `docker-compose.yml` 中运行 PostgreSQL 和 Redis | 应用商店提供标准 PostgreSQL 和 Redis 镜像一键托管 | **仓库不包含数据库容器**。避免自建 DB 容器带来的持久化挂载风险与运维开销。直接连接 1Panel 商店托管的数据库。 |
| 数据库备份 | 手写 shell 备份脚本或容器 | 1Panel 计划任务支持每日定时备份 PostgreSQL 到本地或云存储 (S3/OSS) | **放弃手写备份脚本**。直接使用 1Panel 的图形化计划任务配置定时备份与故障恢复。 |
| 日志管理 | 安装专门的日志收集容器 | 1Panel 容器日志查看器与物理文件管理器 | **挂载共享目录**。Loguru 的 `logs/` 目录直接挂载到宿主机，在 1Panel 界面直观在线排查日志。 |

## 5. 基于 1Panel v2.2.4 的线上部署落地规范

### 5.1 容器网络与端口隔离策略

项目的 `docker-compose.yml` 仅包含 `backend`、`admin` 与 `frontend` 三个应用容器：

- **容器端口映射**：全部限制在本地环回口，例如 `127.0.0.1:18168`（后端 API）、`127.0.0.1:3001`（管理后台），严禁将端口直接暴露到公网 0.0.0.0。
- **环境隔离**：生产环境变量（`POSTGRES_PASSWORD`、`SECRET_KEY` 等）通过 1Panel 的容器 / Compose 环境变量管理功能动态注入，绝不随代码入库。

### 5.2 1Panel OpenResty 网关代理与标头配置

在 1Panel 站点的反向代理配置中，针对各服务配置如下代理规则：

```nginx
# 示例：针对 api.yourdomain.com 反向代理到 http://127.0.0.1:18168
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

这确保了 FastAPI 后端的中立性，使其能通过代理头精准解析真实的客户端 IP，从而保障审计日志、登录日志与 Redis 限流模块正常生效。

### 5.3 数据库自动化迁移 (Alembic)

后端容器启动命令配置为在 Python Web 服务启动前先升级表结构：

```bash
uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 18168 --proxy-headers --forwarded-allow-ips="*"
```

保证了代码发布后，数据库表结构会自动跟进最新迁移，无需手动介入操作。

### 5.4 GitHub Actions 与 1Panel 的 CI/CD 流程

- **代码检查与构建 (CI)**：每次提交触发 GitHub Actions，自动在临时容器中运行 Ruff 静态检查、Mypy 类型检查和 Pytest 测试集。
- **镜像构建 (CD)**：测试通过后，打包 `backend`、`admin` 和 `frontend` 的 Docker 镜像并推送至 GHCR。
- **一键更新发布**：GitHub Actions 通过 SSH 触发 1Panel 执行 Compose 拉取与无缝热重载命令：

```bash
docker compose pull && docker compose up -d --remove-orphans
```

## 6. 总结

本方案在保持 `pinjie-standard` 强规范、高品质 FastAPI 后端内核的前提下，完成了全栈 Monorepo 的结构搭建。确立了 `apps/admin`（B 端后台：React + Vite + Ant Design 5.x + ProComponents）与 `apps/frontend`（C 端电商展示：Next.js App Router + Tailwind CSS + shadcn/ui）的技术落地规划。补全了后端完整的电商核心领域（`products/`, `inventory/`, `cart/`, `orders/`, `payment/`, `promotions/`, `reviews/`），确立了前端基于 `src/features/{domain}/` 的垂直领域切片架构，实现了前后端电商领域 1:1 心智模型完全对齐，以及跨域隔离保护规则。补充了后端事务与异步加载强约束、电商四大核心机制防超卖/幂等/双轨合并/状态机防御线，以及前端数据状态隔离红线。结合线上 1Panel v2.2.4 的现实条件，参照官方全栈模板进行吸收与改造，剔除了冗余的 Traefik 网关和自建数据库容器，实现了代码仓库关注业务开发，1Panel 面板关注系统运维的协同模式。
