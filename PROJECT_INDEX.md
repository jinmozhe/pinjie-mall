# pinjie-mall 项目索引

本文件是项目身份、当前阶段、活动计划和权威入口。全部实施计划的永久登记见 [plans/INDEX.md](plans/INDEX.md)。

## 项目身份

| 字段 | 当前值 |
| --- | --- |
| 项目角色 | 高可用标准电商与多级分销全栈商城平台 |
| 项目类型 | 独立商城仓库 |
| 当前阶段 | 商城后端 M1 至 M4、Admin 电商 A0 至 A4 已完成本地实现；Backend 适用轻量门禁通过，最新安全并发回归用例补充后 pytest 未重跑，Admin 动态验收未执行；小程序工程留待后续，Web 永久冻结 |
| 业务范围 | SPU/SKU 商品、购物车、订单状态机、库存防超卖、微信/支付宝支付、多级分销裂变与双轨佣金钱包 |

## 权威入口

| 事项 | 唯一来源 | 用途 |
| --- | --- | --- |
| 全仓库长期规则 | [AGENTS.md](AGENTS.md) 与三个应用级 `AGENTS.md` | 任务读取、工程边界、验证和交付规则 |
| 项目身份与阶段导航 | [PROJECT_INDEX.md](PROJECT_INDEX.md) | 项目身份、当前阶段、活动计划和权威入口 |
| 详细实现状态 | 实际源码、配置、迁移、生成契约与对应架构文档 | 判断具体能力、接口和运行机制是否已经实现 |
| 产品需求基线 | [docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md) | 商城目标用户、能力、非目标和验收边界 |
| 全域目标数据库字典 | [docs/architecture/database-schema-guide.md](docs/architecture/database-schema-guide.md) | 长期目标物理模型、字段约束、配置、事务与迁移差异；现有代码尚未迁移 |
| 小程序详细需求 | [docs/MINIAPP_PRD.md](docs/MINIAPP_PRD.md) | 小程序用户流程、交付分组与专项验收；不代表工程已启动 |
| 小程序工程设计 | [docs/architecture/miniapp-architecture.md](docs/architecture/miniapp-architecture.md) | 待实施的目录、分层、调用链与状态归属 |
| 计划规则 | [plans/README.md](plans/README.md) | 计划创建、格式、状态、完成和保护规则 |
| 计划永久登记 | [plans/INDEX.md](plans/INDEX.md) | 全部实施计划的路径、状态、结果、范围和用途 |
| 项目文档清单 | [docs/README.md](docs/README.md) | `docs/` 下全部项目文档导航 |
| 架构决策 | [docs/adr/](docs/adr/) | 长期技术取舍及其理由 |
| 架构机制 | [docs/architecture/](docs/architecture/) | 当前系统边界、认证、错误、测试和可靠性机制 |
| 开发与运维步骤 | [docs/operations/](docs/operations/) | 本地开发、发布、部署、恢复和故障处理 |
| 已交付变化 | [CHANGELOG.md](CHANGELOG.md) | 已交付能力和版本变化 |
| 安全治理 | [SECURITY.md](SECURITY.md) | 漏洞报告、安全响应和安全开发要求 |
| OpenAPI 契约 | [openapi.json](openapi.json) | 后端导出的唯一机器契约，禁止手工修改 |

## 活动计划

当前没有活动实施计划；最近完成的[全域数据库字典整合计划](plans/2026-09-21_全域数据库字典整合计划.md)已建立 67 表长期目标字典并同步需求，当前源码与数据库尚未迁移。小程序工程留待后续专项实施，已结束计划继续保留在[计划永久登记](plans/INDEX.md)。
