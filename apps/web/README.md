# apps/web（已停用废弃）

> 状态：全面停用与代码冻结。
> 说明：本项目定位为微信小程序商城，应用层完全不需要 Web 端，C 端交互唯一形态为小程序端。
> 约束：前阶段集中实现后端及管理后台，小程序端前阶段先不开发。完全禁止启动本目录开发服务，完全禁止监听或暴露 3000 及任何 WEB 端口。

C 端用户前端（历史母版骨架，本项目不使用）。

## 技术栈

- Next.js（App Router，`output: standalone`）
- React 19 + TypeScript + Tailwind CSS
- lucide-react
- TanStack Query v5 + Zustand
- @pinjie/api-client（自动生成 SDK）

## 本地启动

```powershell
pnpm install
pnpm --filter @pinjie/web dev   # http://localhost:3000
```

浏览器请求使用同域 `/api/v1`，Next.js Route Handler 在服务端转发到 `BACKEND_INTERNAL_URL`。

## 生产部署模式

使用 `output: standalone` 容器模式。容器部署默认不依赖进程内 ISR 缓存；派生项目需要增量缓存时，必须先设计共享缓存、失效和恢复策略。

## 当前范围

当前已实现业务中立首页和系统状态、注册、登录、SSR 用户中心、资料、密码、会话、退出和注销流程，并覆盖加载、错误和不可用状态。商品、购物车、结算等具体业务 Feature 由派生仓库按计划添加。

## 质量检查

```powershell
pnpm --filter @pinjie/web lint
pnpm --filter @pinjie/web typecheck
pnpm --filter @pinjie/web test
pnpm --filter @pinjie/web build
```
