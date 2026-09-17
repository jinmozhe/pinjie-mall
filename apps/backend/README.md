# apps/backend

FastAPI 商城后端，提供认证、授权、审计、运行基础设施和按阶段建设的电商领域。

## 技术栈

- FastAPI + SQLAlchemy 2.0 async + Alembic
- PostgreSQL + Redis
- Pydantic v2 + Loguru
- uv 包管理

## 本地启动

```powershell
uv python install 3.14
uv python pin 3.14
uv sync --locked
uv run python -c "import sys; assert sys.version_info[:2] == (3, 14); print(sys.version)"
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

本项目使用 uv 管理 Python 版本、项目 `.venv`、依赖和命令运行，不要求激活 Conda 环境。环境变量职责、VS Code 工作区和后端启动顺序见[环境变量分层与 Backend 本地运行手册](../../docs/operations/environment-variables-and-backend-local-run.md)，完整的 Windows 环境、PostgreSQL 和 Docker Desktop Redis 初始化见[本地开发环境手册](../../docs/operations/local-dev-environment.md)。

## 环境变量

复制 `apps/backend/.env.example` 为 `apps/backend/.env` 并填入本地配置。真实 `.env` 不得提交到仓库。

## 当前范围

当前已实现配置、请求上下文、统一错误响应、数据库会话与事务、Redis 生命周期、Alembic、健康探针和 `system` 状态接口，以及 Browser Cookie 认证、用户、管理员、RBAC、Session/Refresh、CSRF、限流、安全事件、审计和可选请求元数据管道。

商城 M1 已增加商品分类、SPU/稳定 SKU、图片资产关联、独立库存账户与幂等人工调整、本人收货地址、运费模板和报价。M2 已增加购物车、服务端结算预览、幂等待付款订单、订单快照、库存占用及取消或超时释放；创建订单时锁定运费模板和库存，支付确认只提供后续支付领域使用的内部入口，达到订单到期点的确认会被拒绝。M3 已增加支付意图、履约、退款、评价和对账基础；未配置微信或支付宝时支付意图明确显示不可用，真实渠道确认仍仅能由后续内部适配器调用。M4 已增加会员档案、首次两级推荐、佣金规则快照、交付后结算、退款追佣、双轨钱包、幂等提现申请和审核解冻。自动确认收货使用 `uv run python -m scripts.auto_confirm_fulfillments --confirm-database <数据库名>` 预览，显式追加 `--apply` 才会写入。M1 至 M4 已完成本地实现，新增迁移文件尚未执行到数据库，新增权限尚未同步到目标环境；地址暂用现有用户 Cookie 认证，小程序登录和真实支付渠道尚未实现。详细边界见[商城后端设计](../../docs/architecture/commerce-backend.md)，建设记录见[四阶段计划](../../plans/2026-09-17_商城后端四阶段建设计划.md)；小程序产品与工程边界见[小程序 PRD](../../docs/MINIAPP_PRD.md)和[小程序架构文档](../../docs/architecture/miniapp-architecture.md)。

## 质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports
uv run python -m compileall -q app alembic scripts
uv run python -c "from app.main import app; app.openapi()"
```

公开接口变化后运行 `uv run python -m scripts.export_openapi`，再在仓库根运行 `pnpm generate-api`。待付款超时处理使用 `uv run python -m scripts.expire_pending_orders --confirm-database <数据库名>` 预览，只有显式追加 `--apply` 才修改订单与库存。任何 pytest 与真实数据库迁移仅在当前任务明确点名授权后执行；数据库集成测试必须显式配置独立的 `TEST_DATABASE_URL` 和 `TEST_REDIS_URL`，数据库名以 `_test` 结尾。
