# ADR 0011: Admin 采用 Ant Design Pro v6 与 Umi Max

- 状态：已确认，已完成
- 日期：2026-08-20
- 决策者：大仙
- 当前标准：[Admin 工程标准](../architecture/admin-engineering-standard.md)

## 背景

迁移前 Admin 使用 Vite、React Router、Ant Design 5 和自建布局、请求、权限及应用入口。管理端已经具备登录、用户、管理员、角色权限、安全日志和系统状态能力，但新增管理页面仍需重复拼装路由、菜单、布局、表格、表单和状态处理。

官方 Ant Design Pro v6 以 `@umijs/max`、Ant Design 6、ProComponents 3、配置式路由、ProLayout、Access、Request、Locale 和 React Query 组成完整管理端工程方案。用户已确认采用官方 Pro v6 作为 Admin 的长期标准，以降低后续管理端基础设施开发量；具体能力仍需服从本项目既有安全、契约和单一事实来源边界。

## 决策

1. Admin 全面迁移到实施开始时官方主分支对应的 Ant Design Pro v6/Umi Max 兼容版本组合。
2. `@umijs/max` 替换 Vite 和独立 React Router 应用入口，采用 Umi 配置式路由、`src/app.tsx`、initialState、Access、Locale、React Query 和 ProLayout。项目保留 `src/lib/api/http.ts` 作为唯一安全传输层，Umi Request 不作为并行请求客户端。
3. Ant Design、ProComponents、Icons、React、Umi Max 及官方插件在 `apps/admin/package.json` 中分别显式声明，由根 `pnpm-lock.yaml` 锁定，不能把 `ant-design-pro` 仓库当作单一 npm 全家桶依赖。
4. Admin 继续使用根 `openapi.json` 和 `@pinjie/api-client` 唯一生成链。官方 OpenAPI 插件只有在不产生第二套 DTO、SDK 或契约副本时才可使用。
5. Browser Cookie Profile、HttpOnly、CSRF、单飞 Refresh、RBAC、服务端最终授权和审计链保持不变。删除与移除统一使用标准警告弹窗，范围与提交保护遵守 [Admin 工程实施标准](../architecture/admin-engineering-standard.md)，管理操作不使用密码二次确认。官方示例 Token、localStorage、Mock 和简单角色判断不进入生产实现。
6. pnpm Monorepo、Feature 边界、3001 端口、Nginx 同域代理、非 Root 容器、MSW、Playwright、axe、80% 覆盖率和 Fail Closed 门禁继续生效。
7. 官方模板的演示页面、远程素材、GA、演示 API、Chatbot、图表地图和其他未使用依赖不进入母版。

## 2026-08-22 实施澄清

保留项目 HTTP 管道仍属于 Umi 体系。Umi 继续托管路由、布局、运行时生命周期、插件契约和客户端 Access；项目传输层继续统一承担 Browser Cookie、CSRF、单飞 Refresh 和错误解包。这样既保留 Umi 的管理端工程能力，也避免官方示例 Request 与现有安全链形成双轨。

Umi 管理的 React Router、Bundler 和编译工具内部版本由当前兼容组合与根锁文件决定，不作为永久架构版本写入本 ADR。升级只采用 Umi 官方支持的组合；范围化安全 override 必须有专项证据和完整回归。

## 影响

- Admin 的工程入口、路由、布局、请求、权限、主题、测试和构建配置需要迁移。
- Backend、Web、数据库和公开 API 契约不修改实现，只参与跨栈回归。
- `packages/api-client` 不手工修改；如迁移后重新生成仍有差异，必须停止交付并修复生成链。
- Docker、Nginx、Playwright、CI、环境变量和项目文档需要适配 Umi 构建方式。

## 备选方案

### 继续 Vite，仅升级 Ant Design 与 ProComponents

该方案改动较小，但无法获得官方 Pro v6 的 Umi 路由、运行时、Access 和 ProLayout 工程基线。用户已确认选择完整官方架构迁移，因此不采用。

### 保留 Vite 与 Umi 双轨

双轨会产生两套路由、构建和运行时边界，增加认证、E2E 和部署排查成本，违反受控迁移和单一事实来源要求，因此不采用。

## 回滚

以迁移前可构建的 Admin Git 快照为回滚基线。回滚只恢复 Admin、锁文件、E2E、部署和文档改动，不修改 Git 历史，不影响 Backend、Web、数据库和 OpenAPI 契约。
