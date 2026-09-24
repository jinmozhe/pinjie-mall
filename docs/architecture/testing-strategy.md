# 测试与质量策略

## 1. 目标

测试围绕风险、边界和用户结果设计。覆盖率用于发现空白，不能代替有效断言，也不能通过 Mock、SQLite 或假数据伪装 PostgreSQL 和真实契约行为。

## 2. 验证时机与测试层级

### 2.1 验证时机

本项目采用“默认轻量、重型验证显式授权”的分层策略：

1. **默认自动门禁**：Admin 与 Web 只运行 typecheck 和 lint；Backend 只运行 Ruff、格式、Mypy、导入边界、编译、应用导入和 OpenAPI 契约检查。公开 API 变化继续执行契约导出、API Client 生成、漂移与 Breaking Change 检查。
2. **统一触发边界**：日常开发、普通提交、`$git-sync`、Push 和 Pull Request 均使用默认轻量门禁。`$git-sync` 只扩展 Git 交付动作，不自动扩展测试范围。
3. **重型验证授权**：Admin/Web production build、任何 Vitest、任何 pytest、Playwright、浏览器自动化和测试数据库验证，只有用户在当前任务中明确点名后才能执行。授权只覆盖被点名的应用、命令和范围，不延续到后续任务。
4. **线上边界**：GitHub Actions 的 Push、Pull Request 和定时任务不得执行重型验证，也不得通过 Workflow 调用链间接触发。完整验证只保留人工 `workflow_dispatch`，并要求输入默认分支历史中的完整 Commit SHA。
5. **结果表达**：默认交付只说明轻量门禁结果。未获授权的重型验证记录为“按项目策略未执行”，不能表述为通过、待 GitSync 执行、完整跨栈验收完成或生产可用。

### 2.2 测试层级

| 层级 | 主要对象 | 依赖策略 | 必测内容 |
| --- | --- | --- | --- |
| 领域单元测试 | 纯规则、值对象、状态转换 | 无数据库和网络 | 边界值、不变量、非法转换 |
| Service 测试 | 用例编排、授权、事务 | Port、Fake 或 Stub | 成功、拒绝、失败、回滚和结果未知 |
| Repository 集成测试 | SQL、约束、加载、并发 | 真实 PostgreSQL `_test` 数据库 | 查询语义、约束、锁和时区 |
| API 测试 | Router 到持久化边界 | 真实应用入口和受控外部依赖 | 认证、授权、校验、错误与响应契约 |
| 跨栈 E2E | 关键用户旅程 | 已启动的完整测试环境 | 前后端集成、关键成功和失败路径 |

禁止 Mock 被测对象自己的内部方法来证明其行为。Fake 和 Stub 应实现稳定 Port，断言可观察结果，避免绑定不必要的调用顺序。

## 3. 数据库与迁移

- 自动化测试只允许连接名称以 `_test` 结尾的独立数据库。
- 测试启动时必须校验主机、数据库名和环境标识，任何不确定状态立即失败。
- 关键数据库行为使用 PostgreSQL，不使用 SQLite 替代。
- Model 变化必须验证空库升级、已有结构升级和重复升级。
- 数据迁移验证行数、约束和关键数据摘要，不能只检查命令退出码。
- 备份恢复演练必须在本机独立 `_test` 数据库执行，核对 Alembic revision、public 表清单、逐表行数、约束数量和未验证约束；`SELECT 1` 不能替代恢复校验。
- 不可逆迁移必须先验证备份和恢复路径，并取得专项授权。

## 4. 契约测试

Backend 进入 `ready` 后，CI 必须：

1. 从应用导出根 `openapi.json`。
2. 从根契约重新生成 `packages/api-client/src/`。
3. 检查工作区无生成差异。
4. 检查 Breaking Change 并关联消费者迁移计划。
5. 验证 Admin 和 Web 使用生成类型，没有复制 DTO。

当前根契约已包含阶段 C 认证、用户、管理员、RBAC 与安全日志端点，并由 `pnpm generate-api` 生成客户端；后续公开 API 变化继续遵循同一链路。

## 5. 架构和静态质量

- Backend 验证 Router、Service、Repository、Model 和领域依赖方向。
- Frontend 通过 TypeScript Compiler API 依赖图验证应用隔离、Feature 公共入口、静态导入、可解析的动态导入和循环依赖。
- 架构门禁必须有正反例，证明合法公开入口通过且动态越界、循环依赖和跨应用引用失败。
- Ruff、Mypy、ESLint 和 TypeScript 错误均为阻断项。
- `any`、无依据断言、忽略类型错误和跳过测试需要显式评审，不能靠全局关闭规则解决。

## 6. 前端验证

### 6.1 固定测试栈

Admin 与 Web 统一采用以下测试栈：

| 职责 | 工具 | 边界 |
| --- | --- | --- |
| 测试运行、断言与覆盖率 | Vitest、`@vitest/coverage-v8` | 纯 TypeScript 单元测试使用 `node` 环境，React 组件测试使用 `jsdom` 环境 |
| React 组件行为 | React Testing Library、`@testing-library/jest-dom`、`@testing-library/user-event` | 按角色、标签、名称和可见文本验证用户可观察行为，不读取 React 组件实例或内部状态 |
| HTTP 边界替身 | MSW 2 | 在单元和组件测试中拦截真实请求接口，集中表达加载、成功、空数据、业务失败和网络失败；未声明请求默认失败 |
| 真实浏览器跨栈 E2E | Playwright Test | 启动真实 Backend、Admin、Web 和隔离 PostgreSQL 测试库，验证关键用户旅程与前后端契约 |
| 自动化可访问性检查 | `@axe-core/playwright` | 在 Playwright 中扫描关键页面和关键状态；扫描结果不能替代键盘、焦点、语义和人工可用性检查 |

Jest、Cypress、Storybook 和 Vitest Browser Mode 不属于阶段 B 默认测试基础设施。只有现有栈无法可靠覆盖且有明确风险证据时，才通过后续计划评估引入，禁止为同一层级长期维护两套等价测试框架。

上述依赖已写入 Admin、Web 和根工作区的 `package.json` 与 `pnpm-lock.yaml`。当前两端的 Vitest 与 `@vitest/coverage-v8` 均固定为 4.1.11；升级后的单元、构建和 E2E 验证需要用户明确授权，未执行时必须记录风险。

### 6.2 单元与组件测试

- 纯函数、数据转换、状态机、Reducer、Store 和不依赖 DOM 的 Hook 优先在 Vitest `node` 环境测试。
- React Client Component、表单、路由交互、TanStack Query 状态和 DOM 行为使用 Vitest、React Testing Library 与 `jsdom`。
- Web 的同步 Server Component 可以在 Vitest 中测试；异步 Server Component、流式渲染和跨 Server、Client 边界行为由 Playwright E2E 覆盖，禁止用脆弱 Mock 伪造框架运行时。
- 交互使用 `user-event`，查询优先使用语义角色、可访问名称、标签和可见文本。只有缺少稳定语义入口时才使用 `data-testid`。
- HTTP 行为通过共享 MSW Handler 描述，Handler 使用生成 API Client 的契约类型；禁止在各测试中分散替换 `fetch`、Axios 或 TanStack Query 内部实现。
- 测试断言用户可观察结果和对外契约，避免快照整个页面、断言 CSS 类名、调用次数或无业务价值的实现顺序。
- 覆盖率用于暴露空白，不替代关键成功、拒绝、失败、恢复和边界断言；生成代码、声明文件和无逻辑入口胶水可以按计划明确排除。

### 6.3 Playwright 跨栈 E2E

- E2E 默认针对生产构建运行：Web 使用 `next build` 后的 standalone server，Admin 使用 `max build`，开发/预览通过 `apps/admin/scripts/run-umi.mjs` 设置 `PORT=3001`。Web 构建脚本同时把静态资源准备到 standalone 目录。
- Windows 和 CI 统一通过 `scripts/e2e/run-e2e.mjs` 启动并回收本次拥有的 Web、Admin 进程，再调用 Playwright。脚本会复用已经存在的受管服务，退出时只终止自己启动的进程，避免 Playwright `webServer` 在 Windows 上回收挂起。
- 关键跨栈测试连接真实 Backend 和独立 `_test` PostgreSQL，不使用 MSW 替代本项目 API。不可控第三方服务在边界处使用可审计替身。
- 每个测试拥有独立浏览器上下文和可准确归属的测试数据，禁止依赖其他测试的执行顺序、Cookie、存储或数据库残留。
- Locator 优先使用 `getByRole()`、`getByLabel()` 和其他用户可见契约；断言使用 Playwright 自动等待能力，禁止固定时长 `sleep` 和无限重试。
- Playwright 不由日常开发、`$git-sync`、Push、Pull Request 或定时任务自动运行。需要本地标准 Chromium E2E 时由用户明确授权；需要干净 Ubuntu 环境时由用户人工触发 GitHub 完整验证。Firefox 与 WebKit 也只在用户明确要求或商城验收计划明确授权时执行。单独的本地浏览器结果不能满足严格源码交接门禁；GitHub 完整验证只有在 pytest、Vitest、production build 和 Chromium Playwright 全部成功并生成同 SHA Artifact 后，才形成发布可核验的重型验证证据。快速源码交接模式明确表示未取得该证据，不能表述为完整验证通过。
- CI 失败只上传白名单阶段耗时、退出状态和浏览器文件位置、项目、状态、重试结果，不上传 Cookie、HAR、Trace、Video、HTML 或截图。CI 禁用 Trace/Video，`failOnFlakyTests` 阻断重试后才成功的套件；本地已授权专项复现可保留现有诊断能力，但敏感报告不得进入 Git 或发布附件。
- 手动 `CI - Full Validation` 支持默认 `full` 和显式 `smoke`。full 并行执行 Backend pytest 和 Admin/Web Vitest、生产构建，最后消费同一 Run 的产物执行 Web standalone、Admin 生产 Nginx dist E2E，并输出 v2 成功证据。smoke 跳过 Admin/Web Vitest 和 coverage，继续执行 Backend pytest、两端生产构建、四个 Chromium 项目的入口页面质量检查及桌面 Stage C；移动端 Stage C 不在 smoke 范围内。`E2E_PROFILE` 未设置时默认 full，非法值直接失败。两种模式均为人工授权的重型验证，不进入日常自动门禁。
- smoke 入口页面基线覆盖 Web 首页、Admin 登录页的可用性、横向溢出、键盘焦点、axe、Token 持久化及 Console error 检查；不代表移动端登录后的账户、管理、上传或权限流程已验收。认证授权、移动端业务交互等高风险修改使用 full。smoke 仅生成独立 `pinjie-smoke-validation-v1`，记录前端测试跳过及 `all-quality-pages,desktop-stage-c` 范围，不能满足 strict 交接；完整模式继续使用 `pinjie-full-validation-v2`。
- 当前单维护者、1Panel 人工部署不要求再运行候选镜像 E2E，使用 CNB/TCR 来源、digest 与扫描核验及部署后健康和关键业务检查，步骤见[端到端人工发布手册](../operations/github-cnb-tcr-1panel-release-runbook.md)。两种验证模式消费的构建产物与最终 TCR 镜像仍有边界，不能表述为最终镜像组合已通过自动 E2E。
- 视觉回归只覆盖少量稳定且高价值的页面或组件状态，固定操作系统、浏览器、字体和视口；普通布局断言优先使用语义和尺寸检查。

### 6.4 UI 与可访问性验收

用户明确授权 UI 或浏览器验收时至少验证：

- 桌面和移动端关键视口。
- 加载、空数据、失败、无权限、成功和危险操作确认。
- 键盘、焦点、标签和对比度。
- 长文本、窄屏、横向溢出和遮挡。
- 关键浏览器流程和控制台错误。

用户明确授权可访问性自动验证时，关键页面和关键状态运行 axe 扫描。自动扫描未发现问题只能说明已配置规则没有命中，不能宣称符合完整 WCAG；键盘操作、焦点顺序、动态反馈、语义和实际可理解性仍需人工或经授权的组件与浏览器验证。

浏览器冒烟不能替代已经配置的单元、组件或 E2E 测试。兜底验证必须明确标为未完整通过。

官方依据：[Next.js Vitest 指南](https://nextjs.org/docs/app/guides/testing/vitest)、[Next.js Playwright 指南](https://nextjs.org/docs/app/guides/testing/playwright)、[Playwright 最佳实践](https://playwright.dev/docs/best-practices)、[Testing Library 原则](https://testing-library.com/docs/guiding-principles)、[Vitest Browser Mode](https://vitest.dev/guide/browser/)和 [MSW 文档](https://mswjs.io/docs/)。

## 7. Backend 覆盖率门禁

- `apps/backend/pyproject.toml` 是 Backend 覆盖率配置的唯一来源，统计范围为 `app`，同时启用行覆盖率和分支覆盖率。
- 用户明确授权运行 `uv run pytest` 时，命令继承 `--cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`，低于 90% 时退出码非零；日常 CI 不自动运行 pytest。
- 经授权的 Backend 全量测试包含真实 PostgreSQL 18.4 与 Redis 8.10.0 集成测试，不允许用 SQLite、跳过 integration marker 或只运行单元测试代替。
- 覆盖率只用于暴露测试空白。关键成功、拒绝、冲突、依赖失败、配置失败和恢复路径仍需具备可观察行为断言。

## 8. 跳过和不稳定测试

- 已明确授权的测试和已配置的轻量自动门禁不得因缺少依赖而静默跳过。
- 临时 `skip`、`xfail` 和隔离测试必须包含原因、负责人和清理日期。按明确的应用项目或 full/smoke 验证范围排除的用例须注明范围原因，并记录为跳过，不能计为通过；这种长期范围选择不属于临时测试债务。
- 不稳定测试先定位原因，不能通过无限重试掩盖。
- CI Summary 必须区分通过、失败、跳过和未适用。

## 9. 完成条件

一项实现通过默认轻量门禁、完成计划内文档同步并如实记录未执行项后，可以提交和完成 Git 交付。只有用户明确授权对应重型验证且实际通过时，才能宣称测试、构建或完整跨栈验收通过。Backend pytest 保持 90% 覆盖率阈值，Admin 与 Web 的 Vitest 保持语句、分支、函数和行覆盖率 80% 阈值；这些阈值只在对应测试获授权并实际运行时生效。

镜像发布属于独立的跨系统交付边界。候选 Commit SHA 必须通过四个自动轻量 Push 工作流，并由操作人员显式选择源码交接验证模式。默认 `strict` 要求存在由默认分支人工触发、成功完成且未过期的 full Artifact；Artifact 中的 Commit SHA、Workflow Run 和验证集合必须与发布输入一致，本地测试结果、smoke 或普通文本说明不能替代。`fast` 只适用于已评估的低风险改动，必须填写原因并记录未取得或未使用完整验证证据的事实；它允许继续构建制品，但不产生完整重型验证通过的结论。操作人员可以先对同一 SHA 运行 smoke，再独立触发 fast；fast 不主动核验 smoke Artifact，也不要求先运行 smoke。具体选择和执行链路以[端到端人工发布手册](../operations/github-cnb-tcr-1panel-release-runbook.md)为准。

前端覆盖率必须纳入承担 Cookie、CSRF、Refresh、权限启动和 BFF 转发的高风险入口。当前 Admin 统计 `src/features/**`、`src/lib/api/**`、`src/access.ts` 与 `src/app.tsx`；Web 统计 `src/features/**`、`src/lib/api/**` 与 BFF Route Handler。不得通过只统计页面组件排除传输和认证生命周期代码来满足 80% 门禁。

最近一次已记录的 Backend 动态验证基线为 2026-09-23 的 441 项自动化测试通过，行与分支综合覆盖率 `90.06%`；同次验证确认本机开发库和隔离测试库已升级至 `20260923_02`，并通过空库、重复升级、恢复和 Alembic 漂移检查。Admin 当前完成 typecheck、lint 及治理轻量门禁，Vitest、production build、Playwright 和真实跨栈验收仍需当前任务明确授权；Web 永久冻结，不作为运行或生产验证目标。
