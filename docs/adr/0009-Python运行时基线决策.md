# ADR 0009: Python 运行时基线决策

- 状态：已确认
- 日期：2026-08-13
- 决策者：大仙
- 当前操作：[本地开发环境手册](../operations/local-dev-environment.md)

## 背景

本仓库是新建全栈母版，阶段 B 已将 Backend 推进到工程 `ready`，当前需要保持运行时、依赖锁、CI 和容器基线一致。原规划固定 Python 3.12，但截至 2026 年 8 月，Python 3.12 已进入仅安全修复阶段，Python 3.14 仍处于稳定 Bugfix 阶段。

截至本决策日期，Python 3.14 最新稳定补丁为 3.14.7。该版本是阶段 B 当前镜像候选，不作为永久静态值；实际实施和后续运行时更新都必须重新查询官方当前补丁与镜像 digest。

生产环境由 1Panel 管理基础设施和应用容器。1Panel 页面提供的宿主机 Python 版本不会决定 Backend 容器中的解释器版本，应用运行时应由仓库配置、锁文件、CI 和不可变镜像共同决定。

阶段 B 的运行依赖和开发工具已经针对标准 CPython 3.14 锁定并完成本地解析。FastAPI、Uvicorn、SQLAlchemy、asyncpg、Alembic、Pydantic、Redis、orjson、Loguru、pytest、Ruff、Mypy 和 import-linter 覆盖目标 Windows x64 与 Linux x86_64；认证和密码哈希依赖留到阶段 C。真实 PostgreSQL 集成测试仍需在提供隔离测试凭据的环境执行。

## 决策

1. Backend 统一使用标准 CPython 3.14，保留常规 GIL 构建，不采用实验性 free-threaded `3.14t` 构建。
2. `apps/backend/pyproject.toml` 在阶段 B 实施时设置 `requires-python = ">=3.14,<3.15"`，Ruff 设置 `target-version = "py314"`，Mypy 设置 `python_version = "3.14"`。
3. 本地 `.python-version` 使用 `3.14` 系列，由 uv 管理解释器和 `.venv`。开发者不得依赖系统 Python、Conda 或 1Panel 宿主机 Python 满足项目运行时。
4. `apps/backend/uv.lock` 锁定全部 Python 依赖及分发文件。阶段 B 必须通过 uv `required-environments` 要求锁文件覆盖 Windows x64 和生产 Linux x64；派生项目使用 Linux ARM64 时，必须在实施前把 ARM64 加入目标环境并完成镜像构建和测试。
5. CI 显式安装标准 CPython 3.14，并校验 `sys.version_info[:2] == (3, 14)`，随后执行 `uv sync --locked` 和完整 Backend 门禁。CI 不维护 3.13 与 3.14 双版本矩阵。
6. Backend 生产镜像使用官方标准 CPython 3.14 slim glibc 镜像。发布前必须选择受支持补丁版本并以完整镜像 digest 固定；当前 Dockerfile 已固定主版本和构建布局，完整 digest 仍待 Docker Hub 网络可用时核验。
7. Python 补丁版本属于运行时供应链更新。升级时重新生成或验证锁文件，完成 Windows 本地、Linux CI、镜像构建、原生扩展导入和 Backend 全质量门禁，再更新基础镜像 digest。
8. 1Panel 继续负责 OpenResty、Compose、PostgreSQL、Redis、环境变量和容器运维。Backend 只通过仓库构建的不可变镜像运行，忽略 1Panel 宿主机 Python 下拉选项。

阶段 B 的 uv 目标环境配置为：

```toml
[tool.uv]
required-environments = [
    "sys_platform == 'win32' and platform_machine == 'AMD64'",
    "sys_platform == 'linux' and platform_machine == 'x86_64'",
]
```

Linux ARM64 派生部署增加 `sys_platform == 'linux' and platform_machine == 'aarch64'`，不得用源码临时编译代替目标平台 Wheel 门禁。

## UUID v7 影响

Python 3.14 标准库已经提供符合 RFC 9562 的 `uuid.uuid7()`。阶段 B 保持“应用层统一生成”的已确认决策，并按以下方式实施：

- `app/core/identifiers.py` 是唯一生成入口，`new_uuid7()` 调用标准库 `uuid.uuid7()` 并返回 `uuid.UUID`。
- Model 使用 `sqlalchemy.Uuid(as_uuid=True)` 和 `default=new_uuid7`。
- PostgreSQL 只保存原生 `uuid` 类型，不要求 PostgreSQL 18，也不设置 `server_default=uuidv7()`。
- 不添加 `uuid-utils`、`uuid6` 或其他 UUID v7 第三方运行依赖。
- 调用方不得绕过 `new_uuid7()` 分散调用标准库或第三方 UUID v7 实现。

## 备选方案

### Python 3.13

Python 3.13 仍处于稳定维护阶段，生态风险较低。它会缩短母版后续维护周期，并继续需要第三方 UUID v7 实现，因此不作为新母版默认基线。

### Python 3.12

Python 3.12 已进入仅安全修复阶段。继续使用可以减少一次基线调整，但会把升级成本推迟到业务实现之后，因此不采用。

### 1Panel 宿主机 Python

直接使用 1Panel 提供的 Python 会让运行时版本脱离仓库、CI、锁文件和镜像追溯链。当前生产架构已经采用 Backend 容器，因此不采用。

## 影响与验证

阶段 B 已同步以下位置，后续运行时升级继续按同一清单验证：

- `apps/backend/pyproject.toml`、`.python-version` 和 `uv.lock`。
- Ruff、Mypy、Backend CI 和 Dockerfile。
- UUID v7 适配器、Model、架构检查和真实 PostgreSQL 往返测试。
- Backend README、本地开发手册和相关项目规则。

至少验证：

```powershell
uv run python -c "import sys; assert sys.version_info[:2] == (3, 14); print(sys.version)"
uv sync --locked
uv run python -c "import uuid; value = uuid.uuid7(); assert type(value) is uuid.UUID and value.version == 7"
```

生产镜像还必须验证标准 CPython 构建、非 Root 用户、目标 Linux 架构、原生扩展导入、健康探针和固定基础镜像 digest。

Dockerfile 发布前的基础镜像格式为：

```dockerfile
FROM python:3.14.<当前受支持补丁>-slim-trixie@sha256:<核验后的完整摘要>
```

占位值不得进入生产发布配置。更新 Python 基础镜像时必须查询官方 registry，填入真实补丁版本和完整 manifest digest，并重新执行镜像构建、架构、非 Root、原生扩展和健康探针验证。

## 实施记录

2026-08-15 已完成原决策中的待办：官方 `python:3.14.7-slim-trixie` 经 Docker Hub 拉取并在本机核验为标准 CPython 3.14.7、Linux x86_64，RepoDigest 为 `sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4`。Backend Dockerfile 的 builder 与 runtime 已同时固定该完整 digest，镜像构建、原生扩展安装、非 Root 运行和健康探针均通过。此前“完整 digest 仍待核验”和“本地构建未完成”的实施状态到此关闭，运行时升级仍按本 ADR 的受控更新流程执行。

## 官方依据

- [Python 版本状态](https://devguide.python.org/versions/)
- [Python 3.14 uuid 文档](https://docs.python.org/3.14/library/uuid.html#uuid.uuid7)
- [uv Python 版本管理](https://docs.astral.sh/uv/concepts/python-versions/)
- [uv required-environments 配置](https://docs.astral.sh/uv/reference/settings/#required-environments)
- [Docker 官方 Python 镜像](https://hub.docker.com/_/python)
- [PostgreSQL 18 UUID 函数](https://www.postgresql.org/docs/18/functions-uuid.html)
- [SQLAlchemy Uuid 类型](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Uuid)
