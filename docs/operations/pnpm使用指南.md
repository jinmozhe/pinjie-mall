# 为什么选择 pnpm 而不是 npm

> 文档归属：`docs/operations/pnpm使用指南.md`
> 本地开发主手册：[Windows 本地开发环境手册](local-dev-environment.md)
>
> 本文档说明本项目（pinjie-mall）选择 pnpm 的原因，
> 通过与 npm 的机制对比帮助开发者理解 pnpm 的核心优势。

## 背景

本项目是 Monorepo 结构，包含三个子应用和三个共享包：

```text
apps/
  admin/             (@pinjie/admin)
  web/               (@pinjie/web)
  backend/           (Python，不参与 Node 包管理)
packages/
  api-client/        (@pinjie/api-client)
  eslint-config/     (@pinjie/eslint-config)
  typescript-config/ (@pinjie/typescript-config)
```

在这种多包结构下，npm 的问题被放大，而 pnpm 的优势得到充分体现。

---

## 一、npm 的核心问题

### 问题 1：node_modules 体积灾难

npm 的设计是将每个包的依赖**就近复制**到各自的 `node_modules` 中：

```text
apps/admin/node_modules/
  react/              ← 完整副本
  react-dom/          ← 完整副本
  typescript/         ← 完整副本
  ...（数百个包）

apps/web/node_modules/
  react/              ← 又一份完整副本（版本相同！）
  react-dom/          ← 又一份完整副本
  typescript/         ← 又一份完整副本
  ...（数百个包）
```

两个子项目用的是同一个版本的 react，却在磁盘上存了两份。
一个普通 Monorepo 项目的 `node_modules` 轻松超过 1-2 GB。

### 问题 2：幽灵依赖（Phantom Dependencies）

npm 会把所有包平铺到顶层 `node_modules`，导致你可以在代码里使用
**没有在 `package.json` 里声明的包**：

```javascript
// admin/src/utils.ts
import dayjs from 'dayjs'   // 你的 package.json 里没有声明 dayjs
                             // 但 antd 依赖了它，npm 把它平铺出来了
                             // 代码能跑，但这是隐患：
                             // antd 升级后删掉 dayjs，你的代码就报错了
```

这类 bug 极难排查，因为本地能跑、CI 也能跑，直到某次依赖升级才爆发。

### 问题 3：安装速度慢

npm 每次安装都要把包从网络下载并完整复制到 `node_modules`，
即使这个包上次已经装过，也要重新复制一遍。

### 问题 4：lockfile 可靠性问题

npm 的 `package-lock.json` 在多人协作时经常产生大量无意义的 diff，
合并冲突后的 lockfile 有时会导致依赖版本不一致。

---

## 二、pnpm 的存储机制

pnpm 采用「全局内容寻址存储 + 虚拟 node_modules 硬链接」设计，
从根本上解决了上述问题。

### npm 的方式（复制模式）

```text
磁盘存储
├── 项目 A/node_modules/react/    ← 完整文件（10 MB）
├── 项目 B/node_modules/react/    ← 完整文件（10 MB，重复！）
└── 项目 C/node_modules/react/    ← 完整文件（10 MB，重复！）
共计：30 MB
```

### pnpm 的方式（硬链接模式）

```text
磁盘存储
├── 全局存储（~/.local/share/pnpm/store/）
│   └── react@19.0.0/             ← 真实文件，只存一份（10 MB）
│
├── 项目 A/node_modules/react/    → 硬链接（0 MB 额外占用）
├── 项目 B/node_modules/react/    → 硬链接（0 MB 额外占用）
└── 项目 C/node_modules/react/    → 硬链接（0 MB 额外占用）
共计：10 MB（节省 20 MB）
```

### pnpm 的隔离 node_modules 结构

pnpm 不会把依赖平铺到顶层，而是用符号链接构建**严格隔离**的结构：

```text
apps/admin/node_modules/
  react/              → 符号链接（指向 .pnpm 中的真实位置）
  antd/               → 符号链接
  .pnpm/              ← 真实的硬链接存放处
    react@19.0.0/
      node_modules/
        react/        → 硬链接到全局存储
    antd@5.21.0/
      node_modules/
        antd/         → 硬链接到全局存储
        dayjs/        → antd 的私有依赖（不暴露给上层！）
```

`dayjs` 是 antd 的依赖，只出现在 antd 的私有 `node_modules` 里，
**你的代码无法直接 `import dayjs`**，彻底消灭幽灵依赖。

---

## 三、Monorepo Workspace 对比

### npm workspaces（存在问题）

```text
项目根/
└── node_modules/
    ├── react/           ← 所有子项目的 react 都在这里
    ├── @pinjie/
    │   └── api-client/  → 符号链接到 packages/api-client/
    └── ...
```

npm workspaces 把所有依赖提升（hoist）到根目录 `node_modules`，
子项目之间的依赖边界模糊，幽灵依赖问题更严重。

### pnpm workspaces（本项目方式）

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

pnpm 为每个子包维护**独立且严格**的依赖树，同时通过 `workspace:*`
协议让子包之间安全地互相引用：

```json
// apps/admin/package.json
{
  "dependencies": {
    "@pinjie/api-client": "workspace:*"
  }
}
```

`workspace:*` 表示：直接引用本仓库 `packages/api-client` 的源码，
不通过 npm registry，无需发布，改动即时生效。

### 对比表

| 维度 | npm workspaces | pnpm workspaces |
| --- | --- | --- |
| **磁盘占用** | 每个子包独立复制 | 全局存储 + 硬链接，大幅节省 |
| **安装速度** | 慢（全量复制） | 快（已缓存则直接硬链接） |
| **幽灵依赖** | 有（依赖提升导致） | 无（严格隔离） |
| **子包互引** | 支持，但配置繁琐 | `workspace:*` 协议，简洁可靠 |
| **lockfile 质量** | `package-lock.json`（冲突多） | `pnpm-lock.yaml`（结构清晰） |
| **Monorepo 适配** | 勉强可用 | 原生设计，深度支持 |

---

## 四、本项目选择 pnpm 的五大理由

### 理由 1：项目本身就是 Monorepo，pnpm 是最优选

本项目有 2 个前端子应用 + 3 个共享包，正是 pnpm workspace 的最佳使用场景。
npm 在 Monorepo 下的幽灵依赖和磁盘浪费问题会被显著放大。

### 理由 2：`workspace:*` 协议让共享包开发体验极佳

```json
// apps/admin/package.json
"@pinjie/api-client": "workspace:*"

// apps/web/package.json
"@pinjie/api-client": "workspace:*"
```

修改 `packages/api-client/` 的代码后，`admin` 和 `web` 无需重新安装，
直接可以使用最新版本。这对 OpenAPI 自动生成客户端的工作流至关重要：

```powershell
# 后端接口变更后的完整同步流程
pnpm generate-api      # 重新生成 api-client（根目录命令）
# admin 和 web 立即获得最新的 API 类型，无需任何额外操作
```

### 理由 3：与 Turborepo 的组合是行业标准

本项目使用 Turborepo 作为构建加速工具。Turborepo 官方推荐 pnpm 作为包管理器，
两者组合是当前 Monorepo 的最佳实践：

```powershell
# 根目录统一运行所有子项目的开发服务器
pnpm dev

# Turborepo 读取 pnpm-workspace.yaml，识别所有子包并并行启动
# admin → Umi Max dev server（Ant Design Pro v6）
# web   → next dev
```

### 理由 4：严格依赖隔离保障类型安全

`admin` 引用了 `@pinjie/api-client`，但没有声明 `axios`（api-client 的内部依赖）。
pnpm 的严格模式保证 `admin` 的代码**无法**直接 `import axios`，
避免了"能用但不应该用"的依赖污染。

### 理由 5：单一 lockfile，全仓库依赖一致

整个 Monorepo 只有一个 `pnpm-lock.yaml`（在根目录），
所有子项目的依赖版本都锁定在同一个文件里：

```text
项目根/
├── pnpm-lock.yaml      ← 全仓库唯一 lockfile（必须提交到版本控制）
└── node_modules/       ← 根目录的全局节点（pnpm 管理）
```

对比 npm：每个子包可能有自己的 `package-lock.json`，版本管理混乱。

---

## 五、日常开发命令速查

### 全局操作（在项目根目录执行）

| 操作 | 命令 |
| --- | --- |
| 安装所有子包依赖 | `pnpm install` |
| 启动所有前端开发服务器 | `pnpm dev` |
| 构建所有子包 | `pnpm build` |
| 全局代码检查 | `pnpm lint` |
| 全仓库 Markdown 检查 | `pnpm lint:md` |
| 全局类型检查 | `pnpm typecheck` |
| 重新生成 API 客户端 | `pnpm generate-api` |

### 针对特定子包操作（Filter 语法）

```powershell
# 只在 admin 子项目执行命令
pnpm --filter @pinjie/admin dev
pnpm --filter @pinjie/admin add axios

# 只在 web 子项目添加依赖
pnpm --filter @pinjie/web add framer-motion

# 在 api-client 包执行命令
pnpm --filter @pinjie/api-client build
```

### 依赖管理

```powershell
# 为某个子项目添加依赖（在根目录执行，用 --filter 指定目标）
pnpm --filter @pinjie/admin add dayjs
pnpm --filter @pinjie/admin add -D @types/node

# 移除依赖
pnpm --filter @pinjie/admin remove dayjs

# 升级所有依赖到最新版本
pnpm update --recursive
```

根 `pnpm-workspace.yaml` 同时执行以下供应链约束：

- `minimumReleaseAge: 10080`：新发布版本经过 10080 分钟，即七天冷却期后，才可进入新的依赖解析结果。
- `blockExoticSubdeps: true`：拒绝传递依赖从未信任的 Git 仓库、压缩包 URL 等来源拉取代码；Registry、本地路径、Workspace 链接和 pnpm 明确信任的官方 GitHub 仓库仍可使用。
- `trustPolicy: no-downgrade`：拒绝包的发布来源信任等级相对已有记录下降。
- `trustPolicyExclude`：只为已审查且当前依赖链无法替换的 `semver@6.3.1` 和 `undici-types@6.21.0` 保留精确版本例外，不放行同名包的其他版本。
- `allowBuilds`：只有显式白名单中的包可以执行安装构建脚本。

这些策略不会在 frozen install 中静默改写锁文件，不符合策略的既有锁文件会直接失败。新增、升级或首次启用策略时遇到拒绝，先核对包来源、发布时间和信任变化，再重新解析锁文件；紧急安全修复通过专项评审调整具体边界，不关闭整套策略。

### 安全补丁与缓存实例验证

`node_modules/.pnpm` 是 pnpm 根据锁文件生成的安装目录。安装、补丁生成或重试失败后，其中可能保留旧实例；目录名称、数量和枚举顺序不构成当前依赖图或安全修复的证据。

验证 `patchedDependencies` 时，先核对根 `pnpm-lock.yaml` 的解析版本与补丁校验，再执行 `pnpm install --frozen-lockfile`，最后从实际消费者的模块解析路径验证补丁和行为。排障不得无差别删除 `node_modules/.pnpm`；只可清理本次确认归属的临时补丁目录或实例，且不能将缓存残留当作安装成功。

> **注意**：不要在子项目目录里单独运行 `pnpm install`，
> 始终在根目录统一管理，确保 `pnpm-lock.yaml` 唯一且完整。

---

## 六、常见问题

**Q：pnpm 和 npm 的命令兼容吗？**

大部分命令语法相同，主要区别：

```powershell
npm install       →  pnpm install
npm install axios →  pnpm add axios
npm run dev       →  pnpm dev（pnpm 可省略 run）
npx some-tool     →  pnpm dlx some-tool
```

**Q：全局缓存在哪里，如何清理？**

```powershell
# 查看存储位置
pnpm store path

# 清理未使用的包（安全，不影响已安装项目）
pnpm store prune
```

**Q：为什么不选 yarn？**

yarn（尤其是 yarn berry/PnP 模式）也解决了部分 npm 问题，
但其 Plug'n'Play 模式与很多工具（Vite、Jest 等）兼容性存在问题，
配置复杂度高。pnpm 在解决同等问题的同时，与现有工具链完全兼容，
配置更简单，是目前社区最推荐的 Monorepo 包管理方案。

**Q：`pnpm-lock.yaml` 可以忽略提交吗？**

不可以。`pnpm-lock.yaml` 是团队环境一致性的唯一保障，
**必须提交到版本控制**。`.gitignore` 只排除 `node_modules/`，
不排除 lockfile。

**Q：新成员加入项目，如何快速初始化？**

```powershell
# 1. clone 仓库
git clone <repo-url>
cd pinjie-mall

# 2. 安装 pnpm（如果没有）
npm install -g pnpm

# 3. 一条命令安装所有前端依赖
pnpm install

# 4. 启动前端开发服务器
pnpm dev
```
