# pinjie-mall 项目索引

本文件是项目身份、当前阶段、活动计划和权威入口。全部实施计划的永久登记见 [plans/INDEX.md](plans/INDEX.md)。

## 项目身份

| 字段 | 当前值 |
| --- | --- |
| 项目角色 | 高可用标准电商与多级分销全栈商城平台 |
| 项目类型 | 独立商城仓库 |
| 当前阶段 | 客户端形态确立为微信小程序，不需要 Web 端；商城后端 M1 商品基础本地实现已落地，后续按四阶段计划推进；管理后台页面与小程序端不在本轮实现范围 |
| 业务范围 | SPU/SKU 商品、购物车、订单状态机、库存防超卖、微信/支付宝支付、多级分销裂变与双轨佣金钱包 |

## 权威入口

| 事项 | 唯一来源 | 用途 |
| --- | --- | --- |
| 全仓库长期规则 | [AGENTS.md](AGENTS.md) 与三个应用级 `AGENTS.md` | 任务读取、工程边界、验证和交付规则 |
| 项目身份与阶段导航 | [PROJECT_INDEX.md](PROJECT_INDEX.md) | 项目身份、当前阶段、活动计划和权威入口 |
| 详细实现状态 | 实际源码、配置、迁移、生成契约与对应架构文档 | 判断具体能力、接口和运行机制是否已经实现 |
| 产品需求基线 | [docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md) | 商城目标用户、能力、非目标和验收边界 |
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

| 计划 | 状态 | 当前工作 |
| --- | --- | --- |
| [商城后端四阶段建设计划](plans/2026-09-17_商城后端四阶段建设计划.md) | 实施中 | M0 文档与 M1 本地实现已完成，M2 至 M4 尚未实施 |
