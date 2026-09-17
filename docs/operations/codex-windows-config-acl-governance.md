# Codex Windows 配置与 ACL 治理标准

## 1. 文档目的

本文是本项目在 Windows 原生 ChatGPT/Codex 桌面端中使用 `config.toml`、Windows 沙箱、网络与 Schannel、NTFS Owner/ACL、依赖缓存和 Git 受保护路径的唯一详细操作来源。

本文解决以下长期问题：

- `config.toml` 在哪里、何时生效，以及桌面端“自定义（`config.toml`）”与设置页选项的关系。
- 为什么长期基线采用 `elevated + Custom (config.toml)`。
- 同一电脑的多个项目是否需要重复配置。
- 换到另一台电脑时哪些内容可以迁移，哪些状态必须重新建立。
- 如何区分 Owner 差异、真实 NTFS ACL 失败、Codex 沙箱越界、缓存越界、网络边界和命令审批。
- 如何诊断沙箱内 Windows `curl.exe` 和 PowerShell HTTPS 的 Schannel `SEC_E_NO_CREDENTIALS`，并使用最小宿主升级兜底。
- 如何验证、诊断、最小修复和回滚，避免周期性执行全仓库 ACL 重置。

本项目使用 Windows 原生 Codex 和 PowerShell，不把 Docker、WSL2 或 Linux 容器的 UID/GID 问题作为默认解释。应用、数据库和依赖管理的完整本地基线仍见 [Windows 本地开发环境手册](local-dev-environment.md)。

## 2. 核心结论

1. 用户级配置位于 `$env:USERPROFILE\.codex\config.toml`。使用 `$env:USERPROFILE` 动态定位，不在仓库中固定具体 Windows 用户名。
2. 本项目长期采用 `sandbox_mode = "workspace-write"`、`network_access = true`、`[windows].sandbox = "elevated"`，并在任务权限菜单中选择“自定义（`config.toml`）”。本项目由当前用户个人使用，用户已明确接受沙箱命令默认联网风险。
3. `elevated` 创建的文件可能由 `CodexSandbox*` 账户持有。只要实际读写、重命名和删除正常，这不是 ACL 故障，不需要 Owner 归一。
4. 用户级配置默认适用于同一 Windows 用户下的其他项目。本仓库不需要项目级 `.codex/config.toml`。
5. 换电脑时不要直接复制整份个人 `config.toml`。只迁移本文中的脱敏片段，并在新电脑重新确定用户名、uv Cache、登录、沙箱初始化和仓库信任状态。
6. 拉取仓库代码不会迁移用户级 Codex 配置，也不能替代新电脑的 `elevated` 初始化和正反向验收。
7. `.git/`、`.agents/` 和 `.codex/` 在可写工作区中仍属于 Codex 受保护路径。对这些路径的拒绝或审批不是 NTFS 损坏。
8. 禁止使用 `danger-full-access`、全仓库 `icacls /reset /T` 或递归 `FullControl` 作为日常解决方案。
9. 网络开启只允许沙箱内命令建立网络连接，不扩大文件写入范围，也不构成提交、推送、发布、部署或其他外部副作用授权。
10. 沙箱内 Node 和 Python HTTPS 正常时，Windows `curl.exe` 或 PowerShell HTTPS 返回 `SEC_E_NO_CREDENTIALS` 应归类为当前 Schannel 兼容边界；需要这些系统客户端时，只对准确宿主命令申请升级执行。
11. 当前本机 Windows Keyring 凭据只能由宿主用户上下文中的 `gh` 稳定读取。依赖当前 `gh` 登录态的命令必须跳过沙箱认证探测，直接申请准确的宿主用户 PowerShell 执行；该升级不包含登录变更或其他远端副作用授权。

## 3. 事实与证据分层

### 3.1 OpenAI 官方语义

本文于 2026-08-22 至 2026-08-24 复核以下 OpenAI Docs：

- [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)：用户级配置位于 `~/.codex/config.toml`；受信任项目可以通过 `.codex/config.toml` 提供项目级覆盖；`shell_environment_policy.filters` 是新配置推荐形式。
- [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)：`elevated` 是首选原生 Windows 沙箱，使用专用低权限账户、文件系统权限边界、防火墙规则和本地策略；`unelevated` 是隔离较弱的 fallback。
- [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)：沙箱决定技术边界，审批策略决定何时请求批准；默认网络关闭；`.git/`、`.agents/` 和 `.codex/` 在 writable root 内仍受保护。
- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：Codex 在任务开始时加载项目规则，适合保存稳定、长期、可执行的仓库行为约束。
- [Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)：`.rules` 通过准确命令参数前缀控制沙箱外执行的允许、提示或禁止；宽泛前缀会扩大后续宿主执行范围。
- [Sandbox](https://learn.chatgpt.com/docs/sandboxing)：`workspace-write + on-request` 保留工作区边界，并允许任务按需要申请越界；完整访问会移除文件系统和网络沙箱边界。
- [Permissions](https://learn.chatgpt.com/docs/permissions)：beta permission profiles 不能与 `sandbox_mode`、`sandbox_workspace_write` 混用。
- [Microsoft `LoadUserProfileW`](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-loaduserprofilew)：需要用户 Profile 的调用方必须显式加载并在完成后卸载；该文档支持 Profile 相关诊断，但不能单独证明 Codex 的具体实现根因。
- [Microsoft SSPI 状态码](https://learn.microsoft.com/en-us/windows/win32/secauthn/sspi-status-codes)：`SEC_E_NO_CREDENTIALS` 表示安全包中没有可用凭据，不能据此推导为普通 DNS、TCP 或证书错误。

官方文档更新后，以最新 OpenAI Docs 为准。任何升级复核都必须重新验证本文引用的字段和 UI 行为。

### 3.2 本机验证事实

2026-08-22 至 2026-08-24 在 Windows 原生 ChatGPT/Codex 桌面端完成的验证表明：

- `unelevated` 可以让新文件 Owner 保持当前用户，并能访问精确加入的 uv Cache，但 Node 子进程出现 `EPERM`。
- `elevated` 下 Node、uv、仓库文件操作和工作区外写入反例均正常，最终作为长期基线。
- 宿主机的回环代理曾让默认请求通过 `127.0.0.1` 转发出网；排除 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY` 后，默认请求和显式直连均被沙箱网络边界阻断。
- 桌面端预设权限模式不会自动采用用户配置中的额外 `writable_roots`；任务需要选择“自定义（`config.toml`）”。
- 用户随后明确接受个人开发机的沙箱命令联网风险，将 `network_access = true` 设为当前长期基线；代理变量继续排除，防止网络路径被宿主回环代理隐式改变。
- 当前 `CodexSandboxOnline` 身份下 DNS、TCP、HTTP 和 Node HTTPS 正常，Node HTTPS 访问公开测试站点返回 200。
- Windows `curl.exe` 和 PowerShell HTTPS 在相同沙箱身份下返回 `SEC_E_NO_CREDENTIALS`，宿主用户执行相同请求返回 200。现有证据表明它与 Schannel、沙箱账户 Profile 和受限 Token 有关，底层根因仍等待上游确认。
- 2026-08-24 重新完成 GitHub CLI OAuth 登录后，普通宿主 PowerShell 中的 `gh auth status`、`gh api user --jq .login` 和认证型 GitHub Actions 查询均成功；Codex 沙箱内的 `gh auth status` 与 `gh api user` 仍使用旧凭据并返回 `401`。
- 上述对照证明宿主用户的 GitHub CLI 登录有效，并将当前失败收窄为 Windows Keyring 的执行上下文隔离。公开仓库的 `gh run list/view` 可能在沙箱中无需有效登录也能成功，不能单独作为认证有效证据。

相关上游问题跟踪包括 [openai/codex#17458](https://github.com/openai/codex/issues/17458)、[openai/codex#17459](https://github.com/openai/codex/issues/17459) 和 [openai/codex#31073](https://github.com/openai/codex/issues/31073)。这些 Issue 用于升级复核和删除兜底，不能替代本机复现。

这些是本机和当前桌面端版本的验证事实，不应替代未来升级后的复验。

### 3.3 项目约束

- 本项目不提交个人 `config.toml`、认证状态、Token、Provider 秘密或本机绝对路径配置。
- 不通过 `GH_TOKEN`、仓库文件、`config.toml`、命令参数或日志明文保存 GitHub Token 来绕过 Windows Keyring 隔离。
- 本项目的个人开发机默认允许沙箱命令联网；网络目标、参数和输出仍不得泄露凭据、内网地址或生产数据。
- 提交、推送、发布、部署和生产操作继续分别取得用户明确授权。
- 只有可复现的真实 NTFS 失败才能触发 ACL 修复；沙箱审批和 Owner 差异不能触发递归权限修改。

## 4. `config.toml` 的位置与作用域

### 4.1 用户级配置

Windows 下使用以下命令定位配置：

```powershell
$codexConfig = Join-Path $env:USERPROFILE ".codex\config.toml"
$codexConfig
Test-Path -LiteralPath $codexConfig
```

用户级配置属于当前 Windows 用户，默认适用于该用户打开的所有 Codex 项目。它适合保存：

- 默认审批策略和审批审查方。
- 默认沙箱模式和 Windows 沙箱实现。
- 当前用户机器上的最小额外可写根。
- shell 环境变量过滤。
- 其他确实属于当前用户或当前机器的 Codex 设置。

用户级配置不属于 Git 仓库。不要把完整内容粘贴到对话、日志或 Issue，也不要提交到项目。

### 4.2 项目级配置

项目级配置路径是：

```text
<repo>/.codex/config.toml
```

Codex 只在项目被信任后加载项目级配置。项目级配置适合保存经过当前用户审查、确实只对该仓库生效的最小覆盖，不适合保存机器秘密、认证状态或个人路径。

根据官方配置参考，Provider、认证、通知、Profile 选择和遥测路由等机器本地字段不能通过项目级配置覆盖。即便字段允许项目覆盖，也必须评估它是否会扩大工作区、网络或命令权限。

### 4.3 本项目是否需要项目级配置

当前不需要，原因如下：

- `elevated`、审批策略和代理过滤属于当前用户的通用安全基线。
- 默认联网是当前用户已经明确接受风险的个人开发机基线。
- uv Cache 是当前用户机器上的路径，不应写入仓库。
- pnpm Store 位于各工作区内被 Git 忽略的 `.pnpm-store/`，不需要额外机器路径。
- 本仓库已经通过 `AGENTS.md`、计划和运维文档管理项目规则，不依赖项目级 Codex 配置扩大权限。

只有未来出现可证明的仓库专属需求时，才评估新增 `.codex/config.toml`。该变更属于项目配置修改，必须创建或续接计划、进行安全评审并验证信任边界。

### 4.4 配置优先级与实际生效

不能只凭文件文本判断当前任务使用了什么权限。实际结果还受以下因素影响：

- 管理员下发的 managed configuration 或 `requirements.toml`。
- 用户级配置和选择的配置 Profile。
- 受信任项目的项目级覆盖。
- 启动参数或当前任务权限菜单。
- 桌面端版本和当前任务创建时的运行上下文。

修改配置后必须完全退出并重启桌面端，再创建新任务验证。旧任务不能证明新配置已经生效。

## 5. 标准方案：`elevated + Custom (config.toml)`

### 5.1 推荐配置片段

以下片段不包含秘密。尖括号必须替换为新电脑上的实际值，不能原样使用：

```toml
approval_policy = "on-request"
approvals_reviewer = "auto_review"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true
writable_roots = [
  "C:\\Users\\<current-user>\\AppData\\Local\\uv\\cache",
]

[shell_environment_policy.filters]
HTTP_PROXY = "exclude"
HTTPS_PROXY = "exclude"
ALL_PROXY = "exclude"

[windows]
sandbox = "elevated"
```

### 5.2 每个字段解决什么问题

| 字段 | 作用 | 不能解决的问题 |
| --- | --- | --- |
| `approval_policy = "on-request"` | 越过既定边界前请求批准 | 不扩大沙箱文件或网络权限 |
| `approvals_reviewer = "auto_review"` | 将符合条件的审批交给自动审查 | 不等于用户已授权提交、推送或发布 |
| `sandbox_mode = "workspace-write"` | 默认只写工作区和额外可写根 | 不允许写 `.git/` 等受保护路径 |
| `network_access = true` | 允许沙箱内命令默认联网 | 不扩大文件权限，不授权提交、推送、发布、部署或其他外部副作用 |
| `writable_roots` | 精确放行工作区外的稳定缓存 | 不应放行整个用户目录或 `AppData` |
| `shell_environment_policy.filters` | 阻止子进程继承指定代理变量 | 不修改宿主 Windows 代理设置 |
| `windows.sandbox = "elevated"` | 使用官方首选的强 Windows 沙箱 | 不保证所有文件 Owner 都是当前用户 |

### 5.3 为什么不长期使用 `unelevated`

`unelevated` 使用当前用户派生的受限 Token，能够减少 Owner 混杂，但官方明确将其定位为较弱 fallback。本机还验证到 Node 子进程 `EPERM`。因此：

- 不能只为让 Owner 显示为当前用户而切换。
- 只有管理员批准的 `elevated` 初始化受企业策略阻断时，才把它作为临时兼容方案。
- 任何临时评估都必须验证 Node、uv、工作区外写入和网络正例；任一失败即回滚。

### 5.4 为什么任务必须选择 Custom

当前桌面端权限菜单中的“自定义（`config.toml`）”表示任务采用用户配置定义的沙箱边界。其他权限预设有自己的边界，不保证采用额外 `writable_roots`。

“设置 -> 常规”中的权限开关控制哪些模式可以出现在任务菜单中，不代表当前任务已经选择该模式。项目基线是：

- 保留默认权限模式。
- 关闭“完整访问权限”入口。
- 每个需要按本文配置运行的新任务选择“自定义（`config.toml`）”。
- 智能体环境保持“Windows 原生”，集成终端使用 PowerShell。

UI 文案可能随版本变化。升级后以“任务实际采用自定义配置且保持工作区边界”为验收条件，不只依赖按钮名称。

### 5.5 不要混用 beta 权限配置

本文继续使用已经验证的 `sandbox_mode` 与 `[sandbox_workspace_write]`。不要同时添加 beta `default_permissions` 或 `[permissions.*]`；官方说明两套权限系统不能在同一会话中组合。

未来迁移 permission profiles 必须单独建立计划，删除旧沙箱字段并重新执行完整正反向验证，不能增量叠加。

## 6. 首次配置标准链路

### 6.1 前置检查

1. 安装并登录 ChatGPT/Codex 桌面端。
2. 确认项目位于预期 Windows 路径，并从仓库根目录打开任务。
3. 确认智能体环境为 Windows 原生，Shell 为 PowerShell。
4. 运行以下命令获取真实缓存路径：

```powershell
uv cache dir
pnpm store path
```

只有 uv Cache 确实位于工作区外并反复触发沙箱拒绝时，才加入 `writable_roots`。pnpm Store 位于当前仓库 `.pnpm-store/` 时不增加额外根。

### 6.2 合并配置

1. 定位 `$env:USERPROFILE\.codex\config.toml`。
2. 在本机编辑器中打开，不把完整内容输出到终端日志或对话。
3. 只合并第 5.1 节中的沙箱相关字段。
4. 用 `uv cache dir` 的实际结果替换模板路径。
5. 保留既有模型、插件、MCP、Provider、通知和其他无关字段。
6. 检查同一个 TOML table 或 key 没有重复定义。

如果配置可能包含 Token 或私有端点，不创建仓库内备份。需要回滚时只记录本次变更字段的旧值，不复制整份文件。

### 6.3 初始化和生效

1. 完全退出并重启桌面端。
2. 首次启用 `elevated` 时，按桌面端提示完成管理员批准的本机沙箱初始化。
3. 重新打开仓库并确认信任状态。
4. 在任务权限菜单选择“自定义（`config.toml`）”。
5. 创建新任务执行第 10 节正反向验收。

管理员批准只用于建立官方沙箱所需的本机账户、权限和策略，不表示后续命令获得管理员权限。

## 7. 同一电脑的多项目复用

### 7.1 默认行为

同一 Windows 用户下，用户级配置自动成为所有项目的默认基线。新拉取另一个普通仓库后，通常只需要：

1. 从该仓库根目录打开 Codex。
2. 审查并信任仓库。
3. 选择“自定义（`config.toml`）”。
4. 运行一次项目内写入和项目外写入反例。

不需要为每个项目复制 `config.toml`，也不需要在每个仓库创建 `.codex/config.toml`。

### 7.2 需要单独评估的例外

以下情况可能需要项目级覆盖或用户级最小可写根调整：

- 项目使用稳定的工作区外构建缓存。
- Monorepo 工作区根与启动目录不一致，导致预期目录未进入 writable root。
- 项目必须调用本机特定 SDK 或工具目录，并且写入是必要行为。
- 当前用户需要对该仓库单独限制某些 Codex 配置。

遇到例外时先证明准确路径和失败行为，再选择配置层级。不得为了省去审批把整个父目录加入 `writable_roots`。

## 8. 不同电脑迁移

### 8.1 默认迁移策略

不要把旧电脑的整份 `C:\Users\<old-user>\.codex\config.toml` 直接覆盖到新电脑。标准方式是从本文复制脱敏片段，在新电脑按实际路径重新生成。

| 内容 | 是否迁移 | 处理方式 |
| --- | --- | --- |
| `approval_policy`、`approvals_reviewer` | 可以 | 从脱敏模板重新写入 |
| `sandbox_mode`、`network_access`、`windows.sandbox` | 可以 | 从脱敏模板重新写入并复验 |
| 代理变量过滤 | 可以 | 仅迁移字段名和 `exclude` 策略 |
| uv Cache 路径 | 不直接复制 | 在新电脑运行 `uv cache dir` 后生成 |
| pnpm Store 路径 | 不直接复制 | 在新仓库运行 `pnpm store path` 后判断 |
| Token、密码、私有端点 | 禁止 | 在新电脑通过正式登录或秘密管理重新建立 |
| Provider、MCP、插件配置 | 默认不迁移 | 按新电脑实际需求逐项审查和安装 |
| `notify` 命令 | 默认不迁移 | 可能包含旧路径或本机脚本，重新配置 |
| `projects.<path>.trust_level` | 不迁移 | 新电脑逐仓库审查并重新信任 |
| 沙箱账户、ACL、防火墙和本地策略 | 不能迁移 | 由新电脑的 `elevated` 初始化重新建立 |
| 桌面端登录和认证状态 | 不能迁移 | 在新电脑重新登录 |

### 8.2 新电脑完整步骤

1. 安装 Git、ChatGPT/Codex、PowerShell、uv、Node.js 和 pnpm 等项目依赖。
2. 登录桌面端，在设置中保持 Windows 原生智能体环境并关闭完整访问权限入口。
3. 拉取项目仓库；不要从旧电脑复制 `.git`、缓存、依赖目录或个人配置目录。
4. 运行 `uv cache dir` 和 `pnpm store path` 获取新电脑路径。
5. 在新电脑的 `$env:USERPROFILE\.codex\config.toml` 中合并脱敏配置片段。
6. 完全重启桌面端，完成管理员批准的 `elevated` 初始化。
7. 审查并信任新拉取的仓库。
8. 在新任务中选择“自定义（`config.toml`）”。
9. 执行第 10 节完整正反向验收。
10. 验收通过后再进行正常开发；不能只验证 `git status` 或文件创建成功。

### 8.3 仓库代码能带走什么

仓库会带走本文、项目规则、计划、源码和可公开配置模板，但不会带走：

- 用户级 Codex 配置。
- 登录凭据和认证状态。
- Windows 沙箱本地账户与策略。
- 当前任务的权限菜单选择。
- 新电脑的仓库信任状态。
- uv、pnpm 和其他工具的本机缓存事实。

因此，“复制配置并拉取仓库后无需额外设置”不是可靠结论。新电脑至少需要重新初始化和验收一次。

## 9. ACL 与权限问题分类

| 类别 | 典型证据 | 标准处理 |
| --- | --- | --- |
| Owner 差异 | Owner 为 `CodexSandbox*`，但读写、重命名和删除正常 | 记录为 `elevated` 预期现象，不修复 |
| 真实 NTFS ACL 失败 | 准确路径返回 `Access is denied`、`UnauthorizedAccessException` 或 `os error 5`，DACL 或继承能解释失败 | 只诊断和修复准确路径 |
| Codex 工作区边界 | 写入工作区外路径被拒绝 | 调整工作流；必要时增加最小可写根 |
| Codex 受保护路径 | 写 `.git/`、`.agents/` 或 `.codex/` 被拒绝或要求升级 | 按产品边界和动作授权处理，不改 ACL |
| 缓存越界 | uv、pnpm 或工具只在工作区外 Cache 失败 | 先定位实际 Cache，再精确配置 |
| 网络配置边界 | Node 或 Python HTTPS 也无法访问公开测试站点，或者当前上下文显示网络关闭 | 核对 `network_access = true`、Custom 模式和新任务运行上下文 |
| Schannel 兼容边界 | Node/Python HTTPS 正常，但 Windows `curl.exe` 或 PowerShell HTTPS 返回 `SEC_E_NO_CREDENTIALS` | 记录客户端和错误；确需系统客户端时只升级准确宿主命令，不改 ACL、Profile、证书或 TLS 校验 |
| GitHub CLI Keyring 边界 | 宿主 PowerShell 的认证型 `gh` 命令成功，沙箱内 `gh auth status` 或 `gh api user` 返回旧凭据 `401` | 将宿主结果作为登录事实；后续依赖登录态的 `gh` 命令直接申请准确宿主执行，不重复沙箱认证探测 |
| 回环代理绕过 | 默认请求成功，显式直连失败，命令环境存在代理变量 | 排除代理变量并重启复验 |
| 命令审批 | Git 写入、网络、外部副作用或高风险命令请求批准 | 审批该动作；不能表述为 ACL 失败 |

### 9.1 诊断决策树

```text
发生拒绝或 EPERM
  |
  +-- 是否有准确失败路径和 Windows 错误码？
  |     +-- 否 -> 先复现并记录，不修改权限
  |     +-- 是
  |
  +-- 路径是否为 .git/.agents/.codex 或工作区外？
  |     +-- 是 -> 判断受保护路径、沙箱越界或缓存越界
  |     +-- 否
  |
  +-- 当前用户能否创建、覆盖、重命名和删除？
  |     +-- 能 -> Owner 差异不是故障，继续检查具体工具
  |     +-- 不能
  |
  +-- DACL、继承或父目录 Delete 权限能否解释失败？
        +-- 否 -> 检查占用进程、只读属性、杀毒软件和工具锁
        +-- 是 -> 生成准确清单，取得授权后最小修复
```

### 9.2 Schannel 分类

`SEC_E_NO_CREDENTIALS` 不能按普通断网或 NTFS ACL 失败处理。按以下顺序分类：

1. 确认当前任务使用 `elevated + Custom` 且 `network_access = true`。
2. 使用公开测试站点验证 DNS、TCP 和 Node 或 Python HTTPS。
3. 只有 Node 或 Python HTTPS 正常，而 Windows `curl.exe` 或 PowerShell HTTPS 失败时，才归类为当前 Schannel 兼容边界。
4. 记录沙箱身份、客户端、目标站点类别和完整错误码，不记录包含凭据的 URL、Header 或响应正文。
5. 任务确实依赖 Windows 系统客户端时，通过 Codex 审批机制只在宿主身份下重跑准确失败命令，不附加其他命令段，也不申请长期完整访问。

当前底层原因尚未由 OpenAI 或 Microsoft 最终确认。文档只记录可复现行为和处理边界，不把 Profile 缺失或受限 Token 单独写成确定根因。

### 9.3 GitHub CLI 与 Windows Keyring 分类

当前本机已经完成以下对照：

```powershell
gh auth status
gh api user --jq .login
gh run view <run-id> --repo jinmozhe/pinjie-mall
```

普通宿主 PowerShell 中三条命令可以读取有效登录态；沙箱内前两条命令仍返回旧凭据 `401`。后续按以下流程处理：

1. 任务依赖当前 `gh` 登录态或 Windows Keyring 时，不先在沙箱运行 `gh auth status` 或其他认证探测。
2. 保留原命令、仓库、资源编号和只读参数，通过 Codex 审批机制直接申请宿主用户 PowerShell 执行。
3. 每次只升级一条准确命令，不拼接其他命令段，不附加重定向、Token 环境变量或凭据输出。
4. 只读查询可以在原任务授权范围内执行；`gh auth login/logout` 和任何远端写操作继续按项目规则取得独立明确授权。
5. 宿主命令仍返回 `401` 时，才把问题重新归类为真实 GitHub CLI 登录失效，并在普通 PowerShell 中重新登录。

Codex 工具调用中的准确宿主升级示例如下。该 JSON 是执行元数据示例，不是需要用户复制到 `config.toml` 的配置：

```json
{
  "cmd": "gh auth status",
  "sandbox_permissions": "require_escalated",
  "justification": "允许在宿主 PowerShell 上下文读取 Windows Keyring，并验证 GitHub CLI 登录状态吗？",
  "prefix_rule": ["gh", "auth", "status"]
}
```

- `AGENTS.md` 决定 Codex 遇到认证型 `gh` 时应直接申请宿主执行。
- `sandbox_permissions = "require_escalated"` 是单次工具调用参数，实际把准确命令切换到宿主用户上下文；用户不需要把它写入配置文件。
- `approval_policy = "on-request"` 决定越过沙箱边界时发起审批。
- `approvals_reviewer = "auto_review"` 只决定符合条件的审批由自动审查处理，不扩大命令权限，也不替代远端副作用授权。
- `.rules` 只控制已发起的宿主执行请求如何审批，不能单独保证 Codex 跳过第一次沙箱尝试。

确需减少重复的只读审批时，可在用户级 `$env:USERPROFILE\.codex\rules\default.rules` 中使用窄范围规则，并在重启 Codex 后生效：

```python
prefix_rule(
    pattern = ["gh", "auth", "status"],
    decision = "allow",
    justification = "允许在宿主上下文只读检查 GitHub CLI 登录状态",
    match = [
        "gh auth status",
    ],
)

prefix_rule(
    pattern = ["gh", "run", "list"],
    decision = "allow",
    justification = "允许在宿主上下文只读列出 GitHub Actions 运行记录",
    match = [
        "gh run list --repo jinmozhe/pinjie-mall",
    ],
)

prefix_rule(
    pattern = ["gh", "run", "view"],
    decision = "allow",
    justification = "允许在宿主上下文只读查看 GitHub Actions 运行详情",
    match = [
        "gh run view <run-id> --repo jinmozhe/pinjie-mall",
    ],
)
```

使用以下命令检查规则匹配结果，确认没有意外覆盖其他 `gh` 子命令：

```powershell
codex execpolicy check --pretty `
  --rules "$env:USERPROFILE\.codex\rules\default.rules" `
  -- gh auth status
```

禁止配置 `pattern = ["gh"]`、宽泛 `pattern = ["gh", "api"]`，也不为 `gh auth login/logout`、`gh workflow run`、`gh release`、删除或权限修改命令建立长期自动放行规则。`gh api` 可以发送 `POST`、`PATCH` 和 `DELETE` 请求，必须按完整命令和实际副作用单独判断。

## 10. 配置生效验收

### 10.1 工作区内正向验证

在仓库根目录执行以下可回收探针：

```powershell
$probeRoot = Join-Path (Get-Location) ".codex-acl-probe"
New-Item -ItemType Directory -Path $probeRoot
$probeFile = Join-Path $probeRoot "owner.txt"
Set-Content -LiteralPath $probeFile -Value "create" -Encoding utf8NoBOM
Set-Content -LiteralPath $probeFile -Value "overwrite" -Encoding utf8NoBOM
Rename-Item -LiteralPath $probeFile -NewName "renamed.txt"
Get-Acl -LiteralPath (Join-Path $probeRoot "renamed.txt") |
  Select-Object Owner, AreAccessRulesProtected
Remove-Item -LiteralPath $probeRoot -Recurse -Force
```

验收重点是四种文件操作成功，不是 Owner 必须等于当前用户。

继续验证项目工具和子进程：

```powershell
git status --short
git diff --check
pnpm store path
node -e "console.log(process.version)"
uv cache dir
uv run --project apps/backend python -c "import sys; print(sys.executable)"
```

### 10.2 代理环境检查

在 Codex 沙箱命令中只输出变量是否存在，不输出可能包含凭据的代理 URL：

```powershell
"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY" | ForEach-Object {
  [PSCustomObject]@{
    Name = $_
    Present = Test-Path -LiteralPath "Env:$_"
  }
}
```

三个变量都应为 `Present = False`。宿主 PowerShell 中仍可保留用户自己的代理配置。

### 10.3 工作区外写入反例

选择一个明确位于工作区和 `writable_roots` 之外、且不存在的专用测试文件。未申请升级授权时，创建操作应被拒绝。如果意外成功，立即删除该测试文件并判定配置失败，不能继续开发。

不要用现有文件、用户目录根、系统目录或其他项目作为反例目标。

### 10.4 网络与 HTTPS 客户端验收

先验证代理变量未进入命令环境，再使用公开测试站点验证 Node HTTPS。当前基线下 Node 请求应成功：

```powershell
node -e "fetch('https://example.com').then(r => console.log(r.status)).catch(e => { console.error(e); process.exit(1) })"
```

然后分别验证 Windows 系统 HTTPS 客户端：

```powershell
curl.exe --noproxy "*" --head --max-time 10 "https://example.com"
Invoke-WebRequest -Uri "https://example.com" -TimeoutSec 10
```

当前桌面端中，这两个 Schannel 客户端可能返回 `SEC_E_NO_CREDENTIALS`。该结果只表示已知兼容边界，不表示 `network_access = true` 未生效。确需它们完成任务时，对准确命令申请宿主升级执行；能够使用 Node、Python、pnpm 或 uv 完成时，继续在沙箱内执行。

只验证公开测试站点，不使用内网、生产或带参数的敏感 URL。浏览器、连接器、MCP 和 Codex 客户端网络不受 `sandbox_workspace_write.network_access` 直接控制，不能用它们替代 shell 网络验收。

### 10.5 Git 和受保护路径

- 验证阶段只运行 `git status`、`git diff`、`git log` 和 `git show` 等只读命令。
- 不把 `.git/`、`.agents/` 或 `.codex/` 加入 `writable_roots`。
- 修改 `.agents/` 或 `.codex/` 等受保护项目文件时，按准确文件申请一次性升级授权。
- `git add`、`git commit` 和 `git push` 只在任务交付阶段按用户授权执行。

## 11. 只读诊断标准

### 11.1 收集最小证据

每次问题至少记录：

- 失败命令和退出码。
- 准确失败路径。
- Windows 错误消息或错误码。
- 当前任务权限模式是否为 Custom。
- 最近是否修改配置并完整重启。
- 路径属于工作区、额外可写根、受保护路径还是其他位置。

### 11.2 检查 Owner、DACL 和继承

```powershell
$targetPath = Resolve-Path -LiteralPath "path-to-failed-file"
Get-Acl -LiteralPath $targetPath |
  Format-List Owner, AreAccessRulesProtected, AccessToString
icacls $targetPath
```

文件删除或重命名失败时还要检查父目录，因为 Windows 的 Delete 和 Delete Child 权限会共同影响结果：

```powershell
$parentPath = Split-Path -Parent $targetPath
Get-Acl -LiteralPath $parentPath |
  Format-List Owner, AreAccessRulesProtected, AccessToString
```

### 11.3 审计 Git 已跟踪文件 Owner

```powershell
$repoRoot = (Get-Location).Path
$sandboxOwned = foreach ($relativePath in git ls-files) {
  $fullPath = Join-Path $repoRoot $relativePath
  if (Test-Path -LiteralPath $fullPath) {
    $owner = (Get-Acl -LiteralPath $fullPath).Owner
    if ($owner -like "*\CodexSandbox*") {
      [PSCustomObject]@{ Path = $fullPath; Owner = $owner }
    }
  }
}
$sandboxOwned | Format-Table -AutoSize
```

该清单只说明 Owner 分布，不能单独证明 ACL 损坏。

### 11.4 排除非 ACL 原因

在修改权限前继续检查：

- 文件是否带只读属性。
- 是否有编辑器、Node、Python、测试、索引器或杀毒软件占用文件。
- 是否是 Windows 路径长度、符号链接或工具自己的锁文件错误。
- 失败是否只发生在特定 Cache、临时目录或受保护路径。
- HTTPS 失败是否只发生在使用 Schannel 的 Windows 系统客户端，并返回 `SEC_E_NO_CREDENTIALS`。
- 相同路径能否由当前用户 PowerShell 完成四种文件操作。

## 12. 最小修复边界

### 12.1 何时不修复

以下情况不修改 Owner 或 DACL：

- 只有 Owner 显示为 `CodexSandbox*`，没有实际操作失败。
- 失败来自 `.git/`、`.agents/`、`.codex/` 或工作区外沙箱边界。
- 失败来自命令审批、网络审批或用户未授权的 Git 写入。
- 失败是 Windows 系统 HTTPS 客户端返回 `SEC_E_NO_CREDENTIALS`，而 Node 或 Python HTTPS 正常。
- 失败只发生在 Codex 沙箱内的认证型 `gh`，而相同命令在宿主 PowerShell 中可以读取有效 Windows Keyring 凭据。
- 尚未取得准确失败路径、错误码和 DACL 证据。
- 文件正被进程占用或工具锁定。

### 12.2 允许修复的前置条件

只有同时满足以下条件才允许修复：

1. 准确路径稳定复现真实 NTFS 访问失败。
2. `Get-Acl`、`icacls` 和父目录证据能解释失败。
3. 已排除进程占用、只读属性和 Codex 产品边界。
4. 已生成具体路径清单，不使用递归通配符。
5. 用户再次明确授权该清单和管理员操作。
6. 已记录原 Owner、DACL、继承状态和回滚方法。

### 12.3 Owner 的单路径修复

只有证据证明 Owner 是必要条件时，才对准确路径执行：

```powershell
$targetPath = Resolve-Path -LiteralPath "exact-failed-path"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Get-Acl -LiteralPath $targetPath |
  Format-List Owner, AreAccessRulesProtected, AccessToString
icacls $targetPath /setowner $currentUser
```

不要附加 `/T`。修复后立即重跑原失败命令和四种文件操作，并检查 `git status --short` 与 `git diff`。

### 12.4 DACL 修复

DACL 没有适用于所有故障的通用写命令。应根据证据选择以下最小动作之一：

- 恢复本应存在的父目录继承。
- 给当前用户补充准确路径所缺少的 Modify、Delete 或父目录 Delete Child 权限。
- 移除已经确认来源、目标和影响范围的错误显式 Deny。

每个动作都必须先导出或记录原 ACL，且不能删除 `CodexSandboxUsers`、未知 SID ACE 或其他正常继承条目。无法证明最小规则时停止并重新诊断，不运行递归重置。

## 13. 禁止操作

- 禁止把 `danger-full-access` 或“完整访问权限”作为长期开发模式。
- 禁止对仓库、用户目录、`AppData` 或磁盘执行递归 `FullControl`。
- 禁止把 `icacls /reset /T` 作为未分类问题的第一步。
- 禁止删除 `CodexSandboxUsers`、`CodexSandboxOffline`、`CodexSandboxOnline` 或未知 SID ACE。
- 禁止把 `.git/`、`.agents/` 或 `.codex/` 加入额外可写根来绕过保护。
- 禁止因为 Owner 不同就周期性执行 Owner 归一。
- 禁止把真实个人 `config.toml`、凭据或本机路径提交到仓库。
- 禁止在另一台电脑直接覆盖整份个人配置并跳过初始化和验收。
- 禁止同时使用 beta permission profiles 与 `sandbox_mode` 配置。
- 禁止把 Auto-review 当作提交、推送、发布或部署授权。
- 禁止把 `pattern = ["gh"]`、宽泛 `pattern = ["gh", "api"]` 或其他可以覆盖远端写操作的 `gh` 前缀配置为长期自动放行。
- 禁止使用 `GH_TOKEN`、仓库文件、`config.toml`、命令参数或日志明文保存 GitHub Token 来绕过 Windows Keyring 隔离。
- 禁止因为沙箱内 `gh` 返回旧凭据 `401` 就重复登录、退出登录或覆盖宿主 Keyring；必须先用准确宿主命令核对真实登录状态。
- 禁止为修复 `SEC_E_NO_CREDENTIALS` 而加载或常驻挂载沙箱账户 Profile、注册表 Hive。
- 禁止读取、复制或导出沙箱秘密、用户证书私钥、`.sandbox-secrets` 或其他凭据材料。
- 禁止关闭 TLS 证书校验、使用不安全协议或修改系统信任库来绕过当前 Schannel 边界。
- 禁止为系统 HTTPS 客户端创建常驻计划任务、代理服务或长期宿主命令放行。

## 14. 回滚与升级复核

### 14.1 配置回滚

配置变更失败时：

1. 只恢复本次修改字段的旧值。
2. 保留 `workspace-write` 和 `network_access = true`，不回退到完整访问。
3. 完全重启桌面端并创建新任务。
4. 重跑第 10 节完整验收。

如果 `unelevated` 兼容评估失败，将 `[windows].sandbox` 恢复为 `elevated`，不要保留双轨或自动猜测逻辑。

### 14.2 桌面端升级后复核

以下任一情况触发复核：

- Codex 桌面端升级后 UI 权限模式、配置 Schema 或沙箱行为变化。
- OpenAI Docs 修改 `windows.sandbox`、权限 Profiles、受保护路径或网络语义。
- Node、uv 或 pnpm 更新后重新出现 `EPERM` 或 Cache 越界。
- 更换电脑、Windows 用户、仓库路径或企业安全策略。
- Node 或 Python HTTPS 正例失败。
- Windows `curl.exe` 或 PowerShell HTTPS 不再出现 `SEC_E_NO_CREDENTIALS`，或者错误行为发生变化。
- GitHub CLI、Codex 桌面端或 Windows 凭据管理行为升级后，沙箱内 `gh auth status` 不再返回旧凭据 `401`，或者宿主与沙箱结果发生其他变化。

复核时先查 OpenAI Docs，再运行配置解析、工作区正例、Cache、Node 子进程、工作区外写入、Node HTTPS、两个 Windows 系统 HTTPS 客户端和 GitHub CLI Keyring 对照验收。两个系统客户端或 GitHub CLI 在沙箱内连续通过对应验收后，删除各自的宿主升级兜底说明；不能为了保留旧流程而维持双轨。

## 15. 日常检查清单

### 新电脑或首次配置

- [ ] 已重新登录桌面端并完成 `elevated` 初始化。
- [ ] 已通过 `uv cache dir` 获取本机准确路径。
- [ ] 只合并脱敏配置片段，没有复制秘密和旧机器路径。
- [ ] 已关闭完整访问权限入口。
- [ ] 已信任当前仓库并选择 Custom。
- [ ] 工作区内文件、Node、uv 和 pnpm 正例通过。
- [ ] 工作区外写入反例通过。
- [ ] 代理变量不存在，Node HTTPS 正例通过。
- [ ] 已记录 Windows `curl.exe` 和 PowerShell HTTPS 的实际结果；出现 `SEC_E_NO_CREDENTIALS` 时按 Schannel 边界处理。
- [ ] 已在宿主 PowerShell 验证 GitHub CLI 登录；沙箱与宿主结果不一致时按 Windows Keyring 边界处理。

### 日常任务

- [ ] 从正确仓库根目录打开任务。
- [ ] 当前任务使用 Custom。
- [ ] 依赖失败先检查实际 Store/Cache 路径。
- [ ] 权限失败先分类，不直接改 Owner 或 ACL。
- [ ] 系统 HTTPS 客户端失败先与 Node/Python 对照，不直接修改 Profile、证书或 TLS。
- [ ] 依赖当前 `gh` 登录态的命令直接申请准确宿主执行，不先运行沙箱认证探测。
- [ ] Git 写入只在交付阶段按授权集中执行。

### ACL 修复前

- [ ] 已记录准确路径、命令、错误码和可复现步骤。
- [ ] 已检查文件和父目录 DACL、继承与 Delete 权限。
- [ ] 已排除进程占用、只读属性、Cache 和受保护路径。
- [ ] 已生成无通配符的准确修复清单。
- [ ] 已取得该清单的再次明确授权和回滚证据。

## 16. 项目内关联入口

- [AI 助手开发与文档读取指南](ai-assisted-development-workflow.md)：说明何时读取本文以及任务、计划和独立授权流程。
- [Windows 本地开发环境手册](local-dev-environment.md)：说明 uv、pnpm、本机 PostgreSQL、Docker Desktop Redis 和 Windows 原生开发基线。
- 上述历史 ACL 治理计划文件未纳入当前仓库；本手册保留当前可执行的配置、权限、联网、Schannel 和 GitHub CLI 宿主执行边界。
