# Admin 本地运行与验证排障手册

> 适用范围：`apps/admin` 的 Umi Max、Ant Design Pro v6 本地开发、单元测试、浏览器冒烟和跨栈验证。
> 相关标准：[Admin 工程标准](../architecture/admin-engineering-standard.md)

## 1. 标准运行基线

Admin 是 Umi Max 应用。日常命令从仓库根目录执行：

```powershell
pnpm --filter @pinjie/admin dev
```

开发服务默认只监听 `http://127.0.0.1:3001`。`apps/admin/scripts/run-umi.mjs` 注入 `HOST=127.0.0.1` 和 `PORT=3001`，Umi Webpack 精确补丁确保底层 `listen` 调用实际使用该 host。需要局域网访问时必须显式设置 `HOST`，并先评估开发服务暴露风险。直接调用 Umi 时，工作目录必须是 `apps/admin` 且显式设置 `HOST=127.0.0.1`，避免绕过端口和监听边界。

预览和构建使用仓库已有脚本：

```powershell
pnpm --filter @pinjie/admin typecheck
pnpm --filter @pinjie/admin lint
pnpm --filter @pinjie/admin test
pnpm --filter @pinjie/admin build
```

前端依赖只从仓库根目录安装，不能在 `apps/admin` 生成独立锁文件。

## 2. Umi 运行时注意事项

- 浏览器运行时代码不能直接依赖 Vite 专属的 `import.meta.env`。Admin 统一读取 `process.env.VITE_API_URL`，并由 `apps/admin/config/config.ts` 注入。
- Admin 当前固定使用 Umi 默认 Webpack。`@umijs/preset-umi@4.7.5` 支持的 Vite 4 存在 High 漏洞，根 `.pnpmfile.cjs`、`patchedDependencies` 和 `scripts/ci/check-umi-vite-security.mjs` 会移除未使用的 Vite bundler 并拒绝未经复核的 Umi 升级。只有上游稳定版支持安全 Vite 或新的框架迁移计划完成后才能删除补丁。
- 使用 Umi 的 `getInitialState` 时必须启用 `initialState: {}`。否则插件注册阶段会报 `register failed, invalid key getInitialState from plugin`。
- `src/.umi` 和 `src/.umi-production` 是 Umi 生成目录，不能提交，也不应纳入 ESLint 扫描。修改路由、插件或配置后如遇到旧缓存行为，停止服务后删除这两个目录，再重新运行命令。
- Ant Design 6 的弃用警告应在代码中处理。当前迁移中已将 Alert 的 `message` 调整为 `title`、Space 的 `direction` 调整为 `orientation`，Drawer 宽度使用 `styles.wrapper` 保留。

## 3. 单元和组件测试

Admin 使用 Vitest、React Testing Library、jsdom 和 MSW。测试运行在 jsdom 时不要触发真实浏览器导航：登录流程的 `window.location.reload()` 必须在测试模式下受保护，否则测试会挂起或输出导航未实现错误。

标准测试先运行 `run-umi.node-test.mjs`，再使用 Vitest threads 单 worker 执行组件测试和覆盖率，避免 Windows forks 子进程在 Codex 上下文中卡住。

覆盖率命令会比普通单元测试耗时更长。测试数量少不代表可以跳过覆盖率门禁，必须区分以下结果：

- `通过`：命令完整执行且退出码为零。
- `未执行`：依赖或服务前置条件不满足。
- `兜底验证`：只完成浏览器冒烟或局部检查，不能写成完整 E2E 通过。

## 4. 浏览器验证

只有用户在当前任务中明确授权浏览器验证时才启动相关工具。获授权后至少检查登录页在桌面 `1440x900` 和移动 `390x844` 视口下的可见性、登录表单、控制台错误、横向溢出和关键跳转。Playwright 标准项目仍需完整环境；仅使用本机 Chrome 或短会话脚本时，必须在结果中注明是兜底验证。

Windows 环境下，Playwright CLI 包装器可能因依赖 bash 不可用，可使用仓库已锁定的 Playwright Test 或 `npx --yes --package @playwright/cli playwright-cli` 做局部检查。验证结束后只清理本次启动的服务、进程和测试标签，禁止调用会结束整个 Browser Use 会话的 finalize 操作。

## 5. 跨栈验证前置条件

完整 Admin E2E、axe 扫描、运行时 `/api/v1` 代理、`/healthz` 和非 Root 容器验证需要同时具备：

1. Docker Desktop Linux engine 已启动。
2. 本机 PostgreSQL 已启动，且使用独立 `_test` 数据库。
3. Redis 容器已启动并可通过 `redis-cli ping` 返回 `PONG`。
4. Backend 已完成迁移并监听 `18168`。

Admin 默认只自动执行 typecheck 和 lint。Vitest、production build、局部浏览器冒烟和完整跨栈验证都需要用户在当前任务中明确授权；缺少完整环境时必须列出未执行项，不能用 MSW 或假数据替代真实 Backend、PostgreSQL 和 Redis 的跨栈测试。

## 6. 本次迁移中出现的故障

| 现象 | 根因 | 处理方式 |
| --- | --- | --- |
| `max dev --port 3001` 未按预期固定端口 | Umi Max 读取 `PORT` 环境变量，CLI 参数不能作为本项目端口契约 | 统一通过 `run-umi.mjs` 设置 `PORT=3001` |
| 登录页读取到空 API 地址 | Umi 浏览器运行时没有 Vite 的 `import.meta.env` | 改用 `process.env.VITE_API_URL` 并在 Umi 配置中注入 |
| 启动时报 `invalid key getInitialState` | Umi initial-state 插件未启用 | 在配置中启用 `initialState: {}` |
| jsdom 测试在登录后挂起 | 测试环境执行了真实 `window.location.reload()` | 测试模式下跳过真实 reload，浏览器 E2E 仍覆盖真实跳转 |
| ESLint 扫描生成文件 | Umi 生成目录不在忽略列表 | 忽略 `src/.umi` 和 `src/.umi-production` |
| Ant Design 6 控制台出现弃用警告 | 使用了 v6 已迁移的组件属性 | 按 v6 API 替换属性并复测 |

## 7. Windows 重启与蓝屏记录

本次电脑重启对应 Windows 事件 `0x00000139 KERNEL_SECURITY_CHECK_FAILURE`，同时出现 `LiveKernelEvent 141`、`Kernel-Power 41`、`EventLog 6008` 和 `volmgr 161`。事件记录没有 WHEA 硬件错误，也没有 Node、Umi 或 Codex 应用崩溃证据。系统转储因页面文件只配置在 `D:` 且未成功生成 `MEMORY.DMP` 或 Minidump，无法进一步锁定具体驱动。

当时设备列表包含 Intel UHD、NVIDIA MX350、OrayIddDriver 和 GameViewer Virtual Display Adapter，另有较旧的 Intel Wireless-AC 9560 驱动及 `Netwtw10 6062` 记录。现有证据更支持显示驱动或虚拟显示适配器链路问题，置信度为中等，不能据此认定 Admin 代码导致系统崩溃。

后续遇到系统级重启时，先分别检查事件查看器、可靠性监视器、WER、页面文件和转储文件，再将系统故障与应用测试结果分开记录。没有转储或明确应用崩溃证据时，不应把蓝屏直接归因于 Node、Umi、Playwright 或 Codex。

## 8. 长期规则与一次性记录的边界

以下长期规则已同步到根 `AGENTS.md` 和 `apps/admin/AGENTS.md`：Admin 的 Umi 端口契约、生成目录清理、完整跨栈验证的环境前置条件、测试结果分级，以及 Windows 服务和进程的归属清理。

本节第 7 节的错误码、驱动名称、页面文件盘符和本次日期属于事故证据，只用于复盘，不作为所有开发者必须满足的固定版本要求。
