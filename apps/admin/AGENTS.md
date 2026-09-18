# Admin 项目规则

## 作用范围与技术栈

- 本文件适用于 `apps/admin/**`，并继承仓库根 `AGENTS.md`。
- Admin 是 B 端管理工具，采用官方 Ant Design Pro v6 的 Umi Max、React、TypeScript、Ant Design 6、ProComponents、TanStack Query 技术体系。路由、布局、权限和运行时配置由 Umi Max 管理。
- 本项目不需要 Web 端，C 端采用小程序端；前阶段聚焦 Backend 与 Admin。界面应紧凑、稳定、工作导向，优先支持扫描、筛选、比较和重复操作。

## 目录与状态边界

- `config/routes.ts` 负责配置式路由；当前路由页面位于 `src/features/<feature>/*Page.tsx`，Feature 内聚页面、组件、Hook 和领域适配。`src/components/` 放跨页面组件，`src/lib/` 放 HTTP、导航等基础设施。
- 页面和 Feature 不得直接调用原始 `fetch`、拼接底层请求或重复处理响应结构。`src/lib/api/http.ts` 是唯一传输层，统一处理 Cookie 会话、CSRF、单飞 Refresh、响应解包、错误分类和登录失效；不得引入 Umi Request 或另一套客户端形成并行请求管道。
- 服务端数据、缓存和请求状态由 TanStack Query 管理。Zustand 只保存真正的客户端状态，禁止复制 Query 数据形成双份事实来源。
- 临时弹窗、表单和草稿优先使用组件本地状态。Zustand 不保存 Token、Cookie 内容和其他敏感凭据；浏览器认证边界遵守 `docs/architecture/authentication-authorization.md`。
- 独立应用禁止直接互相引用。共享类型和请求能力只能通过 `@pinjie/api-client` 等 `packages/` 公共包进入。
- Feature 只能通过明确公共入口协作，不得导入其他 Feature 的内部组件、Hook、Store 或请求实现。完整边界见 `docs/architecture/module-boundaries.md`。

## API 与类型

- `@pinjie/api-client` 是 OpenAPI 生成类型的唯一来源；当前领域端点由 `src/lib/api/admin.ts` 基于项目 HTTP 管道封装。页面层只消费生成类型和解包后的业务数据，禁止手工复制 OpenAPI 已提供的 DTO，禁止生成或维护第二套 SDK、DTO 或契约副本。
- API 契约变化时，先更新后端并导出根 `openapi.json`，再从根目录运行 `pnpm generate-api`，最后适配 Admin。
- 破坏性契约变化必须在同一全栈计划中完成消费者迁移或建立有删除期限的受控迁移窗口，禁止在页面长期维护新旧响应分支。
- `packages/api-client/src/` 是生成目录，禁止手工修改。
- 避免 `any`、非空断言和无依据的类型转换；外部输入必须在边界处校验或收窄。

## UI 与交互

- 优先使用 Ant Design 和 ProComponents 的现有组件、表单、表格、反馈和主题能力，避免重复实现基础控件；`ProTable`、`ModalForm` 和 `DrawerForm` 适用于标准场景，但不强制用于复杂工作流、特殊交互或有明确性能约束的页面。
- 所有 `ProTable` 列表页面（含只读日志）必须在表格上方工具栏左侧通过 `headerTitle` 显示“XX列表”（XX 为数据名称），右侧显示并启用刷新、密度、列设置、全屏四个内建图标按钮。刷新接入当前 Query 并保留分页与查询条件；接入示例见 `docs/architecture/admin-engineering-standard.md`。
- 搜索、筛选和重置按需实现；预计数据较多且需求不明确时，开发前向用户确认是否需要及具体条件。保留已有查询能力。
- 操作按钮使用 Ant Design 图标并提供明确文本或 Tooltip；危险操作必须有清晰文案和错误反馈，删除与移除类操作按本节统一二次确认。
- 页面状态至少覆盖加载、空数据、失败、无权限和成功反馈。表格与表单需处理窄屏、长文本和溢出。
- `Table`、`ProTable` 表头和单元格须 `white-space: nowrap`，优先用 `onHeaderCell`、`onCell` 或公共表格样式；空表与自适应布局也不换行，长文本用列宽、Tooltip 或明确溢出处理。
- `ProTable` 和 `Table` 统一设置 `scroll={{ x: "max-content" }}`，无论有无数据都保持一致。禁止用 `rows.length ? { x: "max-content" } : undefined` 做条件分支：列头的 `white-space: nowrap` 始终存在，空数据时取消 `scroll.x` 会导致列头宽度撑出容器，触发意外横向滚动条。`ResourceTable` 公共组件已固定此行为，新增独立 Table 时同样遵守。详见工程标准。
- 操作列沿用 `width: "1%"` 和按钮布局，表头、单元格及按钮容器保持单行，不随意换行或固定大宽度。
- 使用 `ProTable` 的列表由 `ProTable` 统一呈现空数据状态，外层 `QueryState` 只处理加载、失败和重试，禁止再传 `empty` 或额外渲染 Ant Design `Empty`。未使用 `ProTable` 的列表、抽屉和面板继续通过 `QueryState empty` 或 Ant Design `Empty` 呈现“暂无数据”。
- 新增数据列表或修改列表操作能力时，必须按服务端权限提供受控批量选择和至少一种与实体生命周期一致的批量操作。已有软删除时对接批量软删除，已有硬删除时对接批量硬删除；没有删除语义时提供启停、分配、导出等合法批量操作，禁止前端循环调用单条写接口模拟批量事务。局部样式、文案或缺陷修复保留既有批量能力，不自动扩大为新增批量功能。
- 批量操作成功后清空选择并刷新数据，失败时保留选择并显示明确错误；翻页、筛选或搜索条件变化时清空不可见选择。没有批量写权限时不显示选择列和批量入口。
- Admin 全局只维护 `StandardConfirmModal` 一个通用标准警告弹窗，页面传入标题、说明、加载状态、执行回调及必要的业务表单内容。按钮固定为“确定”和“取消”，不提供密码输入；已有合规确认不得重复叠加。
- 所有删除、移入回收站、永久删除、移除及同类清除已保存资源或关联的操作，无论软删除、硬删除、单条或批量，都必须先显示标准警告弹窗并由用户明确确认。包括 LOGO、头像等非列表入口；仅修改草稿的移除也先确认，并说明保存后生效。文案明确目标或数量、实际影响和恢复方式，取消不得改变数据、草稿或已选范围。
- 提交前设置同步防重锁，提交期间确认按钮显示 Loading 并禁用，禁止取消、关闭、遮罩和 Esc 关闭；失败保留弹窗、目标、草稿和批量选择，显示明确错误后允许用户重试，成功才关闭、清理选择或刷新。已确认的目标和版本不能在重试中被静默替换。
- 启停、恢复、密码重置、会话撤销、身份调整、角色分配、权限修改和筛选或选择清空等非删除操作保留原交互；不因本规则增加密码二次确认或替代服务端授权。详细接入与验证要求见 `docs/architecture/admin-engineering-standard.md`。
- 登录安全事件、审计事件、请求元数据及产品需求明确登记的不可变历史记录属于只读日志列表，不提供选择列、人工删除或批量写操作。普通业务数据不得自行归类为日志以规避批量能力。
- 不使用营销页式巨型标题、装饰性卡片堆叠、夸张圆角、重阴影或花哨动效。

## 验证

- Admin 的默认自动门禁只有 `pnpm --filter @pinjie/admin typecheck` 和 `pnpm --filter @pinjie/admin lint`。日常开发、普通提交、`$git-sync`、Push 和 Pull Request 均遵守这一范围。
- Admin 采用 Vitest、React Testing Library、jsdom 和 MSW 作为单元与组件测试栈，并使用 Playwright 执行真实浏览器跨栈 E2E；关键页面通过 axe 自动扫描可访问性。详细分层遵守 `docs/architecture/testing-strategy.md`。
- 未经用户在当前任务中明确点名，禁止运行 Admin production build、定向或全量 Vitest、Playwright、axe 浏览器扫描及其他浏览器自动化。`$git-sync` 不提供隐式授权，GitHub Actions 的 Push、Pull Request 和定时触发也不得执行这些命令。
- 用户明确授权时只执行被点名的命令和范围，授权不延续到后续任务；测试或构建失败必须如实报告。未获授权的项目记录为“按项目策略未执行”，不能表述为通过或待 GitSync 执行。
- 测试、构建和 E2E 脚本继续保留，供用户本地人工检查或明确授权的专项验证使用。人工页面体验没有可核验证据时，不记为自动测试或完整跨栈通过。
- 应用出现入口但缺少测试脚本或必要测试时属于 `partial`，仓库门禁必须失败，禁止退回空骨架规避检查。
- 用户明确授权浏览器验证时，检查桌面与移动端视口、关键流程、文字和横向溢出，并只清理本次启动的服务、进程和标签。

## Umi 运行专项

- 路由、布局、运行时生命周期和客户端 Access 只通过 `@umijs/max`、Umi 配置与插件公开入口使用。禁止直接声明、接管或绕过 Umi 管理的 React Router、Bundler、Babel、esbuild 和运行时内部依赖，禁止通过 override 强制升级到 Umi 尚未支持的主版本；精确内部版本只属于当前锁文件事实，不写成永久规则。
- Admin Access 只负责路由、菜单和控件的客户端体验，不是安全边界；所有授权、CSRF、资源状态校验和审计仍由 Backend 最终执行。
- Admin 开发服务使用 `scripts/run-umi.mjs` 通过 `HOST=127.0.0.1`、`PORT=3001` 启动；底层 Umi Webpack host 补丁必须保留。不要使用 `max dev --port` 替代项目脚本；直接调用 Umi 时必须从 `apps/admin` 目录运行并显式绑定 `127.0.0.1`。
- Umi 的 `process.env.VITE_API_URL`、`initialState: {}` 和生成目录清理是运行时约束；不得在浏览器代码中直接使用 Vite 的 `import.meta.env`，不得提交 `src/.umi` 或 `src/.umi-production`。详细排障见 `docs/operations/admin-local-development-and-validation-troubleshooting.md`。

## 依赖准入

- Umi、React、Ant Design、ProComponents 和官方插件只能按官方兼容组合升级；所有升级继续遵守根锁文件、七天冷却、安装脚本白名单、专项计划和受影响范围验证。
- 安全 override 仅用于范围明确且有依赖链证据的兼容修复。默认运行 typecheck、lint 和依赖安全检查；完整 Admin 与跨栈回归需要用户明确授权，未执行时不得把风险表述为已完整验证。没有兼容修复版本的 Medium 或 Low 上游风险按 `SECURITY.md` 建立限时风险接受。
- 当前 Admin 只允许 Umi 默认 Webpack 构建链。移除 Vite 4 的精确 pnpm Hook、两个 Umi 补丁和依赖自检门禁必须同时保留；升级 Umi 或重新启用 Vite bundler 前必须创建专项计划，提供上游兼容证据，并在用户明确授权后执行计划内全量回归。
- 母版只接收跨业务复用且有明确需求的外围能力。图表、富文本、Excel 和其他具体业务依赖默认由派生仓库按真实需求引入，不以“业务依赖自由升级”为准入理由。

布局、列宽、筛选、开关等规则见 `docs/architecture/admin-engineering-standard.md`。
