# Python 包管理工具 uv 使用指南

> 文档归属：`docs/operations/uv使用指南.md`
> 本地开发主手册：[Windows 本地开发环境手册](local-dev-environment.md)
>
> 本文档说明本项目（pinjie-mall）为何选择「纯 uv 模式」，
> 并通过与 conda 的对比、机制解析、使用场景示例帮助开发者快速理解和上手。

## 背景：为什么不用 conda

本项目后端基于 FastAPI + SQLAlchemy 2.0，`pyproject.toml` 中已采用 `[tool.uv]`
配置节定义开发依赖，这是 uv 的原生格式。项目在架构设计阶段已以 uv 为唯一包管理工具，
conda 从未被纳入技术栈。

历史遗留的 `conda activate fastapi_env` 命令存在于早期 README 中，经核实为无效操作——
`uv sync` 和 `uv run` 会自动创建并使用项目根目录的 `.venv`，与 conda 激活的环境无关。

---

## 一、conda 与 uv 的本质区别

两者定位完全不同，不是同类工具的竞争关系。

| 维度 | conda | uv |
| --- | --- | --- |
| **本质** | 环境管理器（隔离运行环境） | 包管理器 + 环境管理器（二合一） |
| **管理对象** | Python 解释器 + 环境隔离 | Python 包安装、依赖解析、虚拟环境 |
| **Python 版本管理** | 支持（通过 conda 频道） | 支持（`uv python install`） |
| **包安装速度** | 慢（conda solver 复杂） | 极快（Rust 编写，比 pip 快 10-100 倍） |
| **依赖锁文件** | `environment.yml`（不够精确） | `uv.lock`（精确锁定全部传递依赖） |
| **是否需要手动激活** | 需要（`conda activate`） | 不需要（`uv run` 自动激活） |
| **与 pyproject.toml 集成** | 无原生支持 | 原生支持，是第一公民 |
| **适合场景** | 数据科学（CUDA、C 库等非 Python 包） | 纯 Python Web 后端项目 |

### conda 在本项目中造成的误解

```powershell
# 开发者执行以下命令
conda activate fastapi_env    # 激活 conda 环境（Python = conda 的 Python）
uv sync                       # uv 在项目目录创建 .venv/，使用 .venv 的 Python
uv run uvicorn app.main:app   # 实际使用 .venv 的 Python，conda activate 被架空
```

`conda activate` 在这套流程中没有实际作用。继续保留会造成文档误导，增加新成员理解成本。

---

## 二、三种模式对比

### 模式 A：纯 conda（传统）

```powershell
conda create -n fastapi_env python=3.14
conda activate fastapi_env
pip install -r requirements.txt
python main.py
```

- Python 版本隔离可靠
- 没有精确锁文件，`pip freeze` 不够可靠
- 环境创建慢，依赖安装慢
- 每次都要手动 `conda activate`
- 不支持 `pyproject.toml` 的标准 `[dependency-groups]` 分组

### 模式 B：conda 环境 + uv 包管理（混合）

```powershell
conda activate fastapi_env
uv pip install -r requirements.txt   # 注意：必须是 uv pip，不是 uv sync
python main.py
```

- 安装速度快于纯 conda
- 仍需手动激活 conda
- `uv pip` 不更新 `pyproject.toml` 和 `uv.lock`，依赖管理碎片化
- 与 `uv sync` / `uv run` 混用会产生环境冲突
- 配置复杂，两套工具职责重叠

### 模式 C：纯 uv（本项目采用）

```powershell
uv sync                           # 初始化环境并安装依赖
uv run uvicorn app.main:app       # 直接运行
```

- 零配置，clone 后一条命令即可运行
- `uv.lock` 精确锁定全部传递依赖，团队环境完全一致
- 不需要手动激活任何环境
- Python 版本由 `pyproject.toml` 的 `requires-python` 自动约束
- 速度极快（全局缓存 + 硬链接机制）
- 与本项目 `pyproject.toml` 的 `[tool.uv]` 配置原生契合

---

## 三、uv 的存储机制

uv 采用「全局缓存 + 项目虚拟环境」两层设计。

```text
你的电脑
│
├── 全局缓存（所有项目共享，只存一份）
│   ├── ~/.cache/uv/python/              ← Python 解释器
│   │   ├── cpython-3.14.x/
│   │   └── cpython-3.11.9/
│   └── ~/.cache/uv/packages/            ← 下载的包文件（wheel）
│       ├── fastapi-0.115.0.whl
│       ├── sqlalchemy-2.0.36.whl
│       └── ...
│
├── pinjie-mall/apps/backend/
│   └── .venv/                           ← 项目私有虚拟环境
│       └── lib/python3.14/site-packages/
│           ├── fastapi/    →  硬链接到全局缓存（不占额外空间）
│           └── sqlalchemy/ →  硬链接到全局缓存
│
└── 另一个 FastAPI 项目/
    └── .venv/
        └── lib/python3.14/site-packages/
            ├── fastapi/    →  同一份全局缓存（不重复下载）
            └── ...
```

关键结论：

- **包文件**：全局缓存，跨项目共享，只下载一次
- **虚拟环境**：项目私有，`.venv/` 里的内容是硬链接（快捷方式），几乎不占磁盘
- **Python 解释器**：全局缓存，多个项目可使用同一个解释器副本

---

## 四、使用场景示例

### 场景 1：首次初始化项目

```powershell
# clone 项目后，进入后端目录
cd apps/backend

# 一条命令完成所有初始化
uv sync
```

uv 自动完成：

1. 读取 `pyproject.toml` → `requires-python = ">=3.14,<3.15"`
2. 检查全局缓存是否有标准 CPython 3.14，没有则自动下载
3. 创建 `.venv/` 虚拟环境
4. 安装所有依赖（缓存中有的包直接硬链接，无需下载）
5. 生成 `uv.lock` 锁文件

### 场景 2：日常开发运行

```powershell
# 启动开发服务器
uv run uvicorn app.main:app --reload --port 8000

# 执行数据库迁移
uv run alembic upgrade head

# 代码格式检查
uv run ruff check .
uv run ruff format --check .

# 类型检查
uv run mypy app/
```

所有命令无需手动激活环境，`uv run` 自动定位并激活最近的 `.venv`。

### VS Code Ruff 与虚拟环境隔离

Windows 本机可在被 `.gitignore` 忽略的 `.vscode/settings.json` 中设置 `"ruff.importStrategy": "useBundled"`，让 VS Code Ruff 扩展使用扩展内置的 Ruff，避免编辑器 Ruff Server 锁定 `apps/backend/.venv/Scripts/ruff.exe` 并阻断 `uv sync --locked`。该设置属于个人工作区配置，不会提交或强制覆盖其他开发者的编辑器偏好。

编辑器诊断只用于开发反馈。项目质量检查和 CI 仍以 `uv.lock` 锁定版本为准：

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
```

首次应用或修改工作区设置后，在 VS Code 中执行 `Developer: Reload Window`。依赖同步使用 `uv sync --locked`；只有经过评审的依赖升级才使用 `uv lock --upgrade`。

### 场景 3：新增依赖

```powershell
# 添加生产依赖（自动更新 pyproject.toml 和 uv.lock）
uv add httpx

# 添加开发依赖
uv add --dev pytest-cov

# 移除依赖
uv remove httpx
```

项目在 `[tool.uv]` 中同时设置 `exclude-newer = "7 days"` 和 `required-version = "==0.11.32"`。生成或更新锁文件时，uv 默认不选择发布时间不足七天的版本，为社区发现撤包、恶意发布和严重回归保留观察窗口；运行版本不符合精确约束时 uv 会直接退出。已有锁文件首次纳入相对冷却策略或升级 uv 时必须重新解析，窗口内版本会回退到满足约束的最近版本；后续 `uv sync --locked` 不会自行改变锁定结果。升级 uv 或紧急安全更新需要先评审，在专项变更中同步 `pyproject.toml`、三个使用 uv 的 GitHub Actions 工作流和 `uv.lock`。

对比 pip 的方式：

```powershell
# pip 需要三步，且依赖版本不精确
pip install httpx
pip freeze > requirements.txt   # 包含所有间接依赖，版本不可控
# 还没有 lock 文件...
```

### 场景 4：团队成员同步环境

```powershell
# 同事 clone 项目后，只需一条命令
uv sync

# uv.lock 保证版本与你完全一致
# 不需要关心 Python 版本、conda 环境名等任何额外信息
```

### 场景 5：本机有多个 Python 项目

```text
项目 A：pinjie-mall  → 标准 CPython 3.14，依赖版本由 uv.lock 决定
项目 B：旧项目                 → Python 3.10，fastapi 0.110.0
```

```powershell
# 两个项目各有独立的 .venv，互不干扰
# 不需要切换任何环境，直接在对应目录运行 uv run 即可
cd 项目A; uv run uvicorn ...   # 自动使用标准 CPython 3.14 环境
cd 项目B; uv run uvicorn ...   # 自动使用 Python 3.10 环境
```

### 场景 6：切换 Python 版本

```powershell
# 安装项目要求的 Python（存入全局缓存，不影响其他项目）
uv python install 3.14

# 固定系列并重建当前项目环境
uv python pin 3.14
uv sync --python 3.14

# 查看已安装的 Python 版本
uv python list
```

### 场景 7：CI/CD 环境（GitHub Actions）

```yaml
# .github/workflows/ci-backend.yml
- name: Install uv
  uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78 # v7
  with:
    enable-cache: true
    python-version: "3.14"
    version: "0.11.32"

- name: Install CPython 3.14
  run: uv python install 3.14

- name: Sync locked dependencies
  run: uv sync --locked --python 3.14
  working-directory: apps/backend

- name: Verify Python runtime
  run: uv run python -c "import sys; assert sys.version_info[:2] == (3, 14); print(sys.version)"
  working-directory: apps/backend

- name: Run Ruff
  run: uv run ruff check . && uv run ruff format --check .
  working-directory: apps/backend

- name: Run Mypy
  run: uv run mypy app
  working-directory: apps/backend
```

CI 必须显式安装 `pyproject.toml` 要求的 uv `0.11.32` 和标准 CPython 3.14，并在 `uv sync --locked` 后校验解释器版本。默认 CI 只运行项目规定的轻量门禁，不运行 pytest；人工完整验证工作流只有在用户明确授权并输入目标 Commit SHA 后才执行 pytest。生产运行时由固定 digest 的 Backend 镜像提供，1Panel 宿主机 Python 不参与版本选择。

---

## 五、本项目的规范命令速查

| 操作 | 命令 | 执行目录 |
| --- | --- | --- |
| 初始化环境 | `uv sync` | `apps/backend/` |
| 启动开发服务器 | `uv run uvicorn app.main:app --reload --port 8000` | `apps/backend/` |
| 数据库迁移 | `uv run alembic upgrade head` | `apps/backend/` |
| 生成迁移文件 | `uv run alembic revision --autogenerate -m "描述"` | `apps/backend/` |
| 运行测试（需用户明确授权） | `uv run pytest` | `apps/backend/` |
| 代码检查 | `uv run ruff check .` | `apps/backend/` |
| 代码格式化 | `uv run ruff format .` | `apps/backend/` |
| 类型检查 | `uv run mypy app/` | `apps/backend/` |
| 新增生产依赖 | `uv add <package>` | `apps/backend/` |
| 新增开发依赖 | `uv add --dev <package>` | `apps/backend/` |
| 移除依赖 | `uv remove <package>` | `apps/backend/` |

> **注意**：`uv.lock` 文件必须提交到版本控制，它是团队环境一致性的唯一保障。
> `.venv/` 目录已在 `.gitignore` 中排除，不提交。

---

## 六、常见问题

**Q：`.venv` 目录可以删除吗？**

可以。删除后重新运行 `uv sync` 即可完整恢复，因为所有依赖信息都记录在
`pyproject.toml` 和 `uv.lock` 中，实际包文件在全局缓存中也还存在。

**Q：换了电脑需要重新安装 uv 吗？**

是的，uv 本身需要安装一次。安装方式：

```powershell
# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装 uv 之后，所有项目只需 `uv sync` 即可。

**Q：如果同事用的是 pip/conda，会有问题吗？**

`pyproject.toml` 是标准格式，pip 也能读取（`pip install -e .`）。
但建议团队统一使用 uv，确保 `uv.lock` 的版本锁定能真正发挥作用。

**Q：uv 的全局缓存在哪里，如何清理？**

```powershell
# 查看缓存位置
uv cache dir

# 清理全部缓存（释放磁盘空间）
uv cache clean

# 只清理某个包的缓存
uv cache clean fastapi
```
