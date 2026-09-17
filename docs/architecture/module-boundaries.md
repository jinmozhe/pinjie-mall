# 模块与依赖边界

## 1. 目标

本文件定义 Backend 领域、Admin Feature、后续小程序与共享包之间的依赖方向。详细技术取舍见 [ADR 0006](../adr/0006-模块化单体与领域依赖边界决策.md)。

## 2. Backend 分层

```text
Router
-> Application Service
-> Domain Rule / Repository Port
-> Repository Adapter
-> Database Model
```

| 层 | 允许职责 | 禁止职责 |
| --- | --- | --- |
| Router | 协议参数、依赖声明、响应模型 | SQL、事务、业务编排、资源授权决策 |
| Application Service | 用例编排、事务、资源授权、领域协作 | HTTP 响应、直接依赖其他领域内部实现 |
| Domain | 业务规则、状态和不变量 | 框架、HTTP、数据库适配细节 |
| Repository Port | 领域所需的持久化能力接口 | SQLAlchemy 实现和事务提交 |
| Repository Adapter | 查询、写入、加载策略和 `flush` | 业务规则、权限、`commit`、吞错 |
| Model | 本领域数据库结构和关系 | API 输入输出契约 |
| Schema/DTO | 边界输入输出和公开数据结构 | ORM 行为和隐式数据库访问 |

事务由 Application Service 控制。Repository 可以 `add`、`delete`、查询和 `flush`，不得自行 `commit` 或回滚后继续返回成功。

## 3. 领域所有权

每个领域拥有：

- 自己的写模型和数据表。
- 自己的 Repository 和内部 Service。
- 自己的公开 Application Service、Port、DTO 或领域事件。
- 自己的业务规则和对应测试。

其他领域不得导入其 `repository`、`models`、内部 `service` 或未公开模块。跨领域写流程进入 `app/services/`，通过公开 Port 调用各领域，并由编排层确定事务和失败策略。

数据库外键不等于代码写权限。一个领域可以保存另一个领域公开标识，但不能直接更新对方表。跨领域级联删除默认禁止，生命周期联动必须显式编排。

## 4. 查询边界

普通写模型不得为了方便直接 JOIN 其他领域内部表并据此修改状态。

以下只读场景可以使用独立 Query Service 或 Read Model：

- 管理报表。
- 搜索索引。
- 列表聚合和导出。
- 不参与业务决策的展示视图。

只读模型必须标明来源、刷新方式、一致性预期和权限过滤。不得把只读聚合对象传回领域写流程充当权威状态。

## 5. Admin Feature 边界

Admin 与后续小程序是独立消费者，彼此不得引用源码。每个 Admin Feature 只能通过自己的公开入口向外暴露稳定能力。

```text
Route / Page
-> Feature Public API
-> Feature UI / Hook / Query
-> Shared API Client
```

约束如下：

- 页面负责路由和页面级编排，不直接拼接底层请求。
- Feature A 不得导入 Feature B 的内部组件、Hook、Store 或请求实现。
- 跨 Feature 复用首先判断是否属于公共 UI、公共基础设施或后端契约。
- 服务端数据由 TanStack Query 管理，不复制到 Zustand。
- Zustand 只保存非敏感客户端状态，认证 Token 不进入客户端可读持久化存储。
- `packages/` 只接受业务中立、边界明确且确有跨应用复用的能力。

### 5.1 后续小程序接入

小程序沿用应用隔离、Feature 公开入口、服务端状态单一来源与共享包准入原则。目标目录、层级职责和调用链以[小程序目录与应用架构](miniapp-architecture.md)为准；页面经 Feature 的 `index.ts` 组合能力，不穿透其他 Feature 的内部文件，领域 API 封装与业务组件就近内聚。

小程序请求运行时独立使用平台能力，继续通过既有 API Client 公共入口消费生成类型。认证模块隔离凭据，购物车角标从 Query 派生；纯领域逻辑不依赖 UI 和平台框架。该设计尚未创建工程，不能以本文登记视为边界扫描已经覆盖。

## 6. 共享包准入

新增共享包必须同时满足：

1. 至少两个应用存在已确认的复用需求，或它是全仓库生成契约和工具配置的唯一来源。
2. 职责单一且业务中立。
3. 具有公开导出入口，消费者不访问内部文件。
4. 不依赖 `apps/` 中的任何源码。
5. 在计划中列出所有消费者、版本影响和验证命令。

涉及长期依赖方向或发布方式变化时新增 ADR。轻量、明确的共享配置扩展可以在已确认计划中完成，不要求为每次小改动单独创建 ADR。

### 共享包退出策略

已在 `packages/` 中的能力满足以下条件之一时可以退出：

1. 所有已确认消费者均已删除或合并了对该包的依赖。
2. 该包的职责已被更合适的单一消费者内联覆盖，不再跨应用复用。
3. 该包长期无维护活动且被所有消费者标记为废弃。

退出步骤必须：

- 在全栈计划中列出消费者迁移步骤、删除日期和验证命令。
- 消费者完成迁移并通过质量门禁后才能从 `packages/` 删除代码。
- 同步更新 `pnpm-workspace.yaml`、根 `package.json`、`docs/README.md` 和 `PROJECT_INDEX.md` 中的相关引用。
- 退出操作只能由用户明确授权后执行，不得由 AI 自主触发。

## 7. 自动门禁

仓库使用两层机械门禁：

- `scripts/ci/check-module-boundaries.ps1` 检查目录、依赖声明和可由文本路径确认的违规。
- `scripts/ci/check-typescript-boundaries.mjs` 使用 Web 已安装的 TypeScript 5.9 Compiler API 构建 Admin、Web 静态依赖图。

当前门禁检查：

- 应用之间的直接源码引用。
- Frontend Feature 之间的内部路径引用。
- Backend 领域之间对 Repository、Model 和内部 Service 的直接引用。
- `packages/` 反向依赖 `apps/`。
- Frontend Feature 只能通过目标 Feature 的 `index` 公开入口协作。
- 静态 `import`、`export`、可解析的 `import()` 和 `require()` 不能绕过应用或 Feature 边界。
- Admin 和 Web 依赖图不得形成循环。

Backend 继续由 import-linter 合同验证 Python 依赖方向。`pnpm check:boundaries` 顺序运行两层仓库门禁，`pnpm check:guards` 使用合法公开入口、动态越界、循环依赖和跨应用引用正反例验证门禁本身。运行时拼接路径、远程模块和业务语义仍由测试与评审承担。

当前脚本尚未登记 miniapp。小程序初始化时必须在同一全栈计划中接入状态检测、两层依赖门禁及正反例验证；现有检查通过不代表小程序具备完整治理覆盖。
