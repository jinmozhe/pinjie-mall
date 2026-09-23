# pinjie-mall 项目索引

本文件是项目身份、当前阶段、活动计划和权威入口。全部实施计划的永久登记见 [plans/INDEX.md](plans/INDEX.md)。

## 项目身份

| 字段 | 当前值 |
| --- | --- |
| 项目角色 | 高可用标准电商与多级分销全栈商城平台 |
| 项目类型 | 独立商城仓库 |
| 当前阶段 | 后端目标模型本机动态验证已完成：阶段 1 至 6、会员资格与积分、开发库和隔离测试库迁移、静态模型核对与单轮任务恢复入口均已完成；真实外部渠道、小程序 Bearer 会话及 Admin 交易页面尚未实施，Web 永久冻结 |
| 业务范围 | SPU/SKU 商品、品牌与属性、库存管理、会员价格与平台运费报价、会员资格与积分账本、三级分佣政策、钱包、购物车、结算、订单、可信成交、履约及售后资金退出已有本地后端实现，并已通过本机 PostgreSQL 与 Redis 动态验证及 90% Backend 覆盖率门禁；真实渠道、常驻 Worker 部署，以及积分兑换、到期和抵扣政策仍未完成 |

## 权威入口

| 事项 | 唯一来源 | 用途 |
| --- | --- | --- |
| 全仓库长期规则 | [AGENTS.md](AGENTS.md) 与三个应用级 `AGENTS.md` | 任务读取、工程边界、验证和交付规则 |
| 项目身份与阶段导航 | [PROJECT_INDEX.md](PROJECT_INDEX.md) | 项目身份、当前阶段、活动计划和权威入口 |
| 详细实现状态 | 实际源码、配置、迁移、生成契约与对应架构文档 | 判断具体能力、接口和运行机制是否已经实现 |
| 产品需求基线 | [docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md) | 商城目标用户、能力、非目标和验收边界 |
| 全域目标数据库字典 | [docs/architecture/database-schema-guide.md](docs/architecture/database-schema-guide.md) | 长期目标物理模型、字段约束、配置、事务与迁移差异；23 张目标新增运行表已迁移至本机开发库和隔离测试库 |
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

| 计划 | 状态 | 当前进度 |
| --- | --- | --- |
| [后端数据规划符合性分阶段修复计划](plans/2026-09-23_后端数据规划符合性分阶段修复计划.md) | 实施中 | 阶段 A 至 F 已完成本地实现；阶段 F 已接入成交消费资格贡献和整单退款冲销，后端与治理轻量门禁通过；实际迁移和动态验证未执行；有效邀请触发规则未定义 |

此前目标模型及动态验证计划继续保留原结果。后续阶段依次处理接单售后、分佣快照、资金恢复、约束审计和资格来源；小程序工程和真实渠道留待后续专项实施，全部记录见[计划永久登记](plans/INDEX.md)。
