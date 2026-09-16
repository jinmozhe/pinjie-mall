# 腾讯云 CAM 子账号与 TCR 个人版最小权限操作手册

## 1. 适用范围

本文负责 TCR 发布账号、生产拉取账号、权限和凭证生命周期。已经完成账号初始化的操作人员执行日常发布时，直接使用[GitHub 到 1Panel 端到端人工发布手册](github-cnb-tcr-1panel-release-runbook.md)。

本手册适用于以下当前项目环境：

- 腾讯云主账号已经完成企业认证。
- 使用免费的腾讯云 TCR 个人版。
- TCR 个人版命名空间为 `pinjie-mall`。
- 需要创建两个私有镜像仓库：
  - `pinjie-mall-backend`
  - `pinjie-mall-admin`
- CNB 使用 `tcr-publisher` 发布镜像。
- 腾讯云生产服务器通过 1Panel 和 Docker Compose 拉取镜像。

本手册只处理 CAM 身份、TCR 个人版 Registry 凭证和镜像拉取权限。镜像发布、生产环境变量、数据库迁移、OpenResty、备份和回滚继续分别参考[容器构建与运行手册](container-build-and-run.md)和[1Panel 单机生产运行手册](1panel-production-runbook.md)。

官方控制台入口：

- [访问管理 CAM 控制台](https://console.cloud.tencent.com/cam)
- [腾讯云 TCR 控制台](https://console.cloud.tencent.com/tcr)

## 2. 先给结论

生产服务器应创建独立 CAM 子用户 `tcr-puller`，只允许拉取指定的两个商城仓库。生产服务器不得复用 `tcr-publisher`。

企业认证描述主账号的认证主体，不限制主账号使用 TCR 个人版。当前主账号已经成功创建个人版命名空间和私有仓库，可以继续为 CAM 子用户配置个人版权限。

一个 CAM 子用户可以通过同一份策略访问多个命名空间和仓库。是否拆分账号取决于职责、环境、责任人和泄露影响范围，不取决于命名空间数量。

当前推荐账号边界：

| 身份 | 使用位置 | 必要权限 | 禁止用途 |
| --- | --- | --- | --- |
| 腾讯云主账号 | 账号治理和紧急恢复 | 主账号固有权限 | 日常 Docker 登录、CNB 发布、生产拉取 |
| `tcr-publisher` | CNB 密钥仓库 | 当前命名空间内候选镜像推送和正式标签发布所需权限 | 生产服务器拉取、日常人工登录 |
| `tcr-puller` | 生产服务器部署用户 | 指定两个商城仓库的查看和拉取权限 | 推送、删除、创建仓库、修改仓库属性 |
| 后续测试环境拉取账号 | 测试服务器 | 仅测试环境实际需要的仓库 | 生产环境拉取和发布 |

## 3. 为什么要区分两个账号

`tcr-publisher` 向 TCR 写入候选标签和最终 SHA 标签；当前发布脚本不读取或更新远程构建缓存。它的凭证泄露后，攻击者可能推送或覆盖镜像标签，影响后续发布。

`tcr-puller` 只负责生产服务器拉取已经批准的固定 digest。它的凭证泄露后，影响范围被限制在读取三张镜像，不能向生产仓库写入内容。

区分两个账号可以实现：

1. 最小权限。生产服务器没有任何镜像写权限。
2. 独立轮换。CNB 发布凭证轮换不影响生产拉取，生产凭证轮换不影响 CNB 构建。
3. 独立撤销。服务器失陷时可以立即禁用 `tcr-puller`，不阻断新镜像发布。
4. 清晰定位。Pull 失败检查 `tcr-puller`，Push 失败检查 `tcr-publisher`。
5. 降低误操作。生产服务器即使误执行 `docker push`，CAM 也应拒绝。

CAM 权限采用允许策略叠加。只读策略无法抵消用户组或其他策略中的写权限。因此，`tcr-puller` 不得同时加入带有 TCR 写权限的用户组，也不得附加 `AdministratorAccess`、`QcloudTCRFullAccess` 或类似全量策略。

## 4. 个人版账号类型怎么选

### 4.1 CAM 子用户

当前项目选择 CAM **子用户**。它由主账号创建并归属于主账号，可以绑定自定义 CAM 策略。

在“自定义创建”页面选择：

请选择 **可访问资源并接收消息**。

“仅用于接收消息”只能接收通知，不能访问 TCR，也不能用于 Docker 登录。

### 4.2 用户级账号

TCR Registry 登录界面所说的用户级账号与腾讯云账号身份关联。个人版登录用户名通常显示为当前腾讯云账号对应的数字账号标识，实际值以子用户登录 TCR 控制台后展示的 `docker login` 命令为准。

不要自行使用主账号 ID、CAM 用户名或邮箱猜测 Registry 用户名。

### 4.3 服务级账号

腾讯云官方当前文档明确说明，服务级账号用于 **TCR 企业版实例**，支持自定义用户名、有效期和命名空间级权限。

当前项目使用 TCR 个人版，控制台没有企业版服务级账号入口属于正常情况。不要购买企业版，也不要为了寻找服务级账号扩大本次范围。

### 4.4 CAM 角色

本流程不需要创建 CAM 角色。将自定义策略直接关联到 `tcr-puller` 子用户即可。

只有未来采用 CVM 实例角色或其他无长期凭证方案，并且 TCR 个人版明确支持对应认证链路时，才单独评估 CAM 角色。本手册不假设该能力已经存在。

## 5. 多个命名空间是否需要多个子账号

不需要按命名空间机械创建多个 CAM 子账号。同一策略的 `resource` 数组可以列出多个命名空间和仓库。

适合复用同一 `tcr-puller` 的条件：

- 仓库属于同一生产环境。
- 由同一运维责任人管理。
- 使用相同轮换周期。
- 任一仓库凭证泄露后的处置范围相同。

应拆分账号的情况：

- 生产和测试环境需要隔离。
- 不同业务团队需要独立撤销和审计。
- 不同服务器集群由不同责任人维护。
- 某个命名空间包含更高敏感级别的镜像。
- 凭证需要不同有效期或轮换窗口。

账号数量按安全边界确定。当前两个商城仓库属于同一应用、同一生产部署，可以共用一个 `tcr-puller`。

## 6. 凭证类型必须分清

| 凭证 | 用途 | 本流程是否需要 | 保存位置 |
| --- | --- | --- | --- |
| CAM 控制台登录密码 | 登录腾讯云子账号控制台 | 需要，用于首次初始化和后续轮换 TCR 密码 | 受控密码管理器 |
| CAM `SecretId` / `SecretKey` | 调用腾讯云 API | 默认不需要 | 不创建 |
| TCR 个人版固定密码 | `docker login ccr.ccs.tencentyun.com` | 需要 | 生产部署用户的 Docker 凭据或受控 Secret |
| SSH 私钥 | 后续 GitHub 连接生产服务器 | 本次人工部署不需要新增 | GitHub `production` Environment Secret |

创建结果中显示 `SecretId -`、`SecretKey -`，表示没有为该子用户创建 CAM API 密钥。这符合当前最小权限设计，不影响 Docker Registry 登录。

CAM 控制台登录密码不能用作 Docker 密码。TCR 固定密码也不能用来登录腾讯云控制台或调用 CAM API。

腾讯云官方说明，TCR 个人版登录密码是固定密码并且全地域一致。重置该密码会影响该 CAM 身份在所有地域和服务器上的 Registry 登录。轮换前必须先盘点全部使用位置。

## 7. 权限策略设计

### 7.0 本商城与命名空间共享范围

先决定账号服务范围，再选择策略模板：本商城按实际仓库授权；同一维护者管理的可信项目可以按受控命名空间共享发布账号和拉取账号，两种身份继续分离。共享 namespace 范围要覆盖现有及未来仓库，并使用 TCR 官方支持的资源匹配语法；固定列举两个商城仓库不会自动覆盖其他项目。

仓库级操作的资源不默认扩大为全账户 `*`；不支持资源级授权的查询或凭据初始化操作，继续保留原模板所需的 `resource: ["*"]`，不能因为收窄仓库权限就机械删除。`cam:GetRole` 仅在已证实依赖时保留对应角色资源。下面两仓策略是单项目模板，共享账号修改时保留其他项目的有效授权，不直接覆盖整份策略。

派生时逐项核对资源所属主账号、Registry、namespace、真实镜像名和子用户身份。CAM 策略匹配的是实际推送或拉取目标，不是 GitHub 仓库名。配置后验证目标仓库操作，登录成功或控制台存在仓库不能代替资源授权验收。权限语法与支持范围以本手册末尾官方资料为准。

### 7.1 `tcr-publisher` 参考边界

当前已验证的 `TCRPersonalPublisherPinjieFullstackBase` 使用以下资源结构管理指定命名空间。文档使用 `<主账号UIN>` 占位，实际策略填写主账号的数字 UIN：

```json
{
  "version": "2.0",
  "statement": [
    {
      "action": [
        "tcr:*"
      ],
      "resource": [
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall",
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall/*"
      ],
      "effect": "allow"
    }
  ]
}
```

该 JSON 只用于解释资源格式和 `tcr-publisher` 为什么具备写入能力。实际发布策略还包含个人版控制台初始化和仓库级 Pull、Push 动作，以 CAM 控制台中的当前策略为准。

严禁把这份 `tcr:*` 策略关联给 `tcr-puller`。

### 7.2 `tcr-puller` 两仓只读策略

建议策略名称：

```text
TCRPersonalPullerPinjieFullstackBase
```

使用以下完整 JSON：

```json
{
  "version": "2.0",
  "statement": [
    {
      "action": [
        "tcr:DescribeRegions",
        "tcr:DescribeInstances",
        "tcr:ValidateUserPersonal",
        "tcr:CreateUserPersonal",
        "tcr:DescribeUserPersonal",
        "tcr:DescribeUserQuotaPersonal",
        "tcr:ModifyUserPasswordPersonal",
        "tcr:DescribeNamespacePersonal",
        "tcr:DescribeRepositoryAllPersonal",
        "tcr:DescribeRepositoryFilterPersonal",
        "tcr:DescribeRepositoryOwnerPersonal",
        "tcr:DescribeRepositoryPersonal",
        "tcr:ValidateNamespaceExistPersonal",
        "tcr:ValidateRepositoryExistPersonal",
        "tcr:DescribeImageConfigPersonal",
        "tcr:DescribeImageFilterPersonal",
        "tcr:DescribeImageLifecyclePersonal",
        "tcr:DescribeImageLifecycleGlobalPersonal"
      ],
      "effect": "allow",
      "resource": [
        "*"
      ]
    },
    {
      "action": [
        "tcr:DescribeImagePersonal",
        "tcr:PullRepositoryPersonal"
      ],
      "effect": "allow",
      "resource": [
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall",
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall/pinjie-mall-backend",
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall/pinjie-mall-backend/*",
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall/pinjie-mall-admin",
        "qcs::tcr::uin/<主账号UIN>:repo/pinjie-mall/pinjie-mall-admin/*"
      ]
    }
  ]
}
```

创建策略前，将全部 `<主账号UIN>` 替换为 CAM 控制台显示的主账号数字 UIN。当前项目应与已验证 `tcr-publisher` 策略中的 UIN 完全一致。

这份策略直接以已验证的 Publisher 策略为基准：第一段完整保留 TCR 个人版控制台、用户初始化、密码管理和只读元数据动作；第二段删除 `tcr:PushRepositoryPersonal`，只保留镜像查看和拉取。命名空间资源让资源检查识别上级范围，仓库资源允许拉取，仓库下级资源覆盖镜像版本或标签。

策略没有以下权限：

- `tcr:PushRepositoryPersonal`
- `tcr:CreateRepositoryPersonal`
- `tcr:DeleteRepositoryPersonal`
- `tcr:DeleteImagePersonal`
- `tcr:ModifyRepositoryAccessPersonal`
- `tcr:*`
- `qcs::tcr::uin/<主账号UIN>:repo/*`

第一段使用 `resource: ["*"]` 是必要配置。`tcr:ValidateUserPersonal`、`tcr:CreateUserPersonal`、`tcr:ModifyUserPasswordPersonal` 和多项控制台查询接口属于操作级接口，无法限定到具体镜像仓库。缺少第一段时，子用户会在进入个人版或初始化密码前收到 `not authorized to perform operation (tcr:ValidateUserPersonal)`。

第一段会读取主账号个人版 TCR 的全局元数据，但不包含仓库 Push、Delete、创建仓库或修改仓库属性权限。对于需要登录控制台、初始化和轮换固定密码的 `tcr-puller`，这是当前已验证的实用最小权限边界。

### 7.3 为什么不能只保留仓库级 Pull

Docker 拉取本身由第二段控制，但首次建立可用凭证还需要完成以下前置调用：

- 验证当前个人版用户：`tcr:ValidateUserPersonal`。
- 首次创建个人版登录身份：`tcr:CreateUserPersonal`。
- 查询当前身份和配额：`tcr:DescribeUserPersonal`、`tcr:DescribeUserQuotaPersonal`。
- 初始化或轮换固定密码：`tcr:ModifyUserPasswordPersonal`。
- 进入统一 TCR 控制台并定位个人版资源所需的地域、实例、命名空间和仓库查询动作。

因此，本项目不再把第一段拆成默认解除的 Bootstrap 策略。保留第一段可以保证 `tcr-puller` 后续自行轮换 TCR 固定密码，同时仍然没有镜像写权限。

如果未来把该身份改成完全不登录控制台、也不负责密码轮换的纯运行时账号，可以单独评估移除第一段。移除后会失去个人版初始化、校验和密码管理能力，必须先准备另一条受控轮换路径并完成真实验证。

## 8. 创建 `tcr-puller` 的完整步骤

### 8.1 先创建两仓只读策略

1. 使用主账号或具有 CAM 管理权限的管理员登录[访问管理 CAM 控制台](https://console.cloud.tencent.com/cam)。
2. 进入“策略”。
3. 单击“新建自定义策略”。
4. 选择“按策略语法创建”。控制台若显示可视化策略生成器，切换到“JSON”。
5. 选择空白模板。
6. 粘贴“7.2 `tcr-puller` 两仓只读策略”中的 JSON。
7. 策略名称填写 `TCRPersonalPullerPinjieFullstackBase`。
8. 描述填写“生产服务器只读拉取 pinjie-mall 两个应用仓库”。
9. 不添加条件，不关联其他服务。
10. 检查 JSON 中没有真实密码、账号 ID 或服务器信息。
11. 完成创建。

### 8.2 自定义创建子用户

1. 在 CAM 左侧进入“用户 > 用户列表”。
2. 单击“新建用户”。
3. 选择“自定义创建”。
4. 用户类型选择“可访问资源并接收消息”。
5. 单击“下一步”填写用户信息。

### 8.3 用户信息如何填写

建议填写：

| 字段 | 建议值 | 说明 |
| --- | --- | --- |
| 用户名 | `tcr-puller` | 只描述用途，不使用个人姓名 |
| 备注 | `pinjie-mall 生产服务器 TCR 只读拉取` | 便于后续审计和轮换 |
| 手机号 | 留空 | 机器用途不需要接收个人短信 |
| 邮箱 | 留空或受控运维邮箱 | 只在组织要求通知时填写 |
| 所属部门 | 按企业现有规范 | 没有组织目录时不强行设置 |

不要把 TCR 密码、服务器 IP、SSH 密钥或数据库信息写入备注。

### 8.4 访问方式如何选择

首次需要使用子用户登录 TCR 控制台并初始化个人版 Registry 密码，因此保留控制台访问能力。

推荐配置：

- 控制台登录：开启。
- 控制台密码：使用随机高强度密码。
- 下次登录重置密码：开启，首次登录后设置独立密码。
- 多因素认证：账号创建后按企业安全规范启用。
- 编程访问或 API 密钥：关闭。

Docker Registry 登录不需要 `SecretId` 和 `SecretKey`。不要因为创建结果显示两项为空而重新开启编程访问。

完成 TCR 初始化后，可以评估关闭 CAM 控制台登录能力，但不能禁用或删除整个子用户。任何调整后必须重新执行服务器 `docker login` 和两仓拉取验证；无法确认影响时保留控制台登录并使用 MFA 保护。

### 8.5 设置用户权限

只关联：

- `TCRPersonalPullerPinjieFullstackBase`

不要选择：

- `AdministratorAccess`
- `QcloudCamFullAccess`
- TCR 或 CCR 全读写预设策略
- `tcr-publisher` 使用的命名空间写策略
- CVM、TKE、COS、VPC 或其他无关产品策略

检查用户是否自动加入用户组。任何用户组中的允许权限都会与直接策略叠加。

### 8.6 设置标签

标签不产生权限，也不会代替 CAM 策略。

处理原则：

- 企业已有统一标签规范时，填写环境、系统、责任人或成本中心标签。
- 没有标签规范时留空。
- 不要临时创造只有本账号使用的标签。
- 标签值不得包含密码、Token、服务器 IP 或其他敏感信息。

### 8.7 审阅并创建

创建前逐项确认：

- 用户名是 `tcr-puller`。
- 用户类型可以访问资源。
- 没有 API 密钥。
- 只关联 `TCRPersonalPullerPinjieFullstackBase` 一份项目专用策略。
- 没有管理员策略和 TCR 写权限。
- 标签不承载授权或秘密。

完成创建后，将 CAM 子用户登录入口和控制台密码保存到受控密码管理器。不要粘贴到仓库、聊天、Issue、工单正文或服务器脚本。

## 9. 初始化 TCR 个人版登录凭证

1. 退出主账号控制台，或使用独立浏览器会话打开新建子用户的快捷登录地址。
2. 使用 `tcr-puller` 登录并完成首次密码重置和 MFA。
3. 打开[TCR 控制台](https://console.cloud.tencent.com/tcr)。
4. 进入个人版实例。
5. 如果页面显示“登录实例”，按页面提示初始化。
6. 如果已经初始化，选择个人版实例的“更多 > 重置登录密码”。
7. 设置独立、高强度的 TCR 固定密码。
8. 记录控制台展示的完整 `docker login` 命令中的实际用户名。
9. 将 TCR 用户名和固定密码保存到受控密码管理器。

控制台展示形式类似：

```bash
docker login ccr.ccs.tencentyun.com --username=<TCR登录用户名>
```

不要把 `<TCR登录用户名>` 替换成 CAM 用户名 `tcr-puller`，也不要自行使用主账号 ID。以当前子用户控制台显示的值为准。

如果页面提示无权限：

1. 确认当前登录身份是 `tcr-puller`。
2. 确认完整 `TCRPersonalPullerPinjieFullstackBase` 策略已经关联，第一段包含 `tcr:ValidateUserPersonal` 且资源为 `*`。
3. 等待 CAM 策略短暂生效后刷新。
4. 记录错误提示中的准确 API 名称。
5. 只针对该 API 查询腾讯云官方 CAM 接口清单。
6. 无法确定时提交腾讯云工单，禁止直接附加管理员权限。

## 10. 在腾讯云服务器登录 TCR

### 10.1 使用正确的 Linux 用户

Docker 凭据默认保存在执行命令用户的 `~/.docker/config.json`。人工登录和后续部署必须使用同一个 Linux 部署用户。

如果当前在 1Panel 终端中使用 `root` 登录，而后续 GitHub SSH 使用 `pinjie-deploy`，两个用户不会自动共享 Docker 凭据。推荐最终使用独立部署用户执行登录和 Compose。

先确认当前用户：

```bash
whoami
id
```

### 10.2 交互式登录

执行：

```bash
docker login ccr.ccs.tencentyun.com --username=<TCR登录用户名>
```

出现 `Password:` 后再粘贴 TCR 固定密码。不要把密码直接写进命令行，否则可能进入 Shell 历史、1Panel 终端记录或进程参数。

登录成功后收紧凭据文件权限：

```bash
test -f "$HOME/.docker/config.json"
chmod 600 "$HOME/.docker/config.json"
```

Docker 默认配置文件通常只对凭据做 Base64 编码，不等同于加密。生产部署用户的主目录必须限制访问。条件允许时配置 Docker Credential Helper；未配置时至少保证文件权限和主机访问边界。

### 10.3 按固定 digest 拉取两张镜像

新发布从 Backend 与 Admin 各自成功 CNB Build 生成的
`pinjie-cnb-tcr-image-v1` 单镜像证据中取得完整 digest。两个应用来自同一
Commit 时，必须等待预期触发的 Pipeline 全部成功，并核对三份证据中的
`source.commit_sha` 一致。历史发布的 `pinjie-cnb-tcr-release-v1` 三镜像清单
只用于读取已有附件和回滚基线。两种证据都必须使用完整 digest，不使用
`latest`、`candidate-*`、`buildcache-main` 或只写 SHA 标签。

```bash
docker pull ccr.ccs.tencentyun.com/pinjie-mall/pinjie-mall-backend@sha256:<backend-digest>
docker pull ccr.ccs.tencentyun.com/pinjie-mall/pinjie-mall-admin@sha256:<admin-digest>
```

每条命令必须显示拉取成功，最终 digest 必须与对应发布证据一致。

### 10.4 可选的 Windows 本机镜像核验

本机 Docker 登录仅服务于本机私有镜像查询，不是 GitHub → CNB → TCR 的发布前置条件。已有 CNB 发布证据，并能在已认证 TCR 控制台或服务器核对完整镜像引用和 digest 时，可以跳过本机登录。浏览器、CNB、本机 CLI 和服务器的凭据互不自动同步。

1. 已有 Docker CLI 时，先用每个应用各自的正式 SHA 标签执行 `docker buildx imagetools inspect <仓库>:sha-<完整源码SHA>`。查询成功就复用现有登录态；记录最上层完整 `Digest:`，不要误用平台子清单或 attestation digest。
2. 鉴权失败时核对当前 Windows 用户、Registry、实际 TCR 用户名及该身份的固定密码。使用本商城目标仓库的只读账号，不把 CAM 网页密码、CNB Token 或 API SecretKey 用作 Registry 密码。
3. 需要登录时执行下面的交互命令；只在密码提示中输入固定密码，禁止输出 Docker 配置文件或 Credential Helper 内容。

   ```powershell
   $tcrReadOnlyUsername = Read-Host '请输入 TCR 控制台展示的 Registry 用户名'
   docker login ccr.ccs.tencentyun.com --username "$tcrReadOnlyUsername"
   ```

4. 只有确认旧身份或旧凭据需要清除，且已取得正确凭据时，才执行 `docker logout ccr.ccs.tencentyun.com` 后重新登录。此操作不会重置 TCR 密码，也不会更新 CNB 或服务器凭据，不作为每次发布的固定步骤。
5. 登录成功后再次查询目标仓库。Registry 接受身份不证明具备资源权限；`denied` 检查目标仓库授权，`not found` 在身份权限确认后检查仓库名及正式标签是否生成，网络错误不直接归为密码错误。
6. 两端独立发布时分别记录各自源码 SHA 和 digest。确认无跨端变化后保留未变化端的已验证版本；不要为了让两个标签相同而重建。无需执行本机容器启动来证明镜像清单存在。

选择其他核验入口时记录该入口和每端结果，本机查询失败不等于云端发布失败。CLI 凭据范围参见 [Docker login 官方文档](https://docs.docker.com/reference/cli/docker/login/)。

## 11. 权限验收

### 11.1 正向验收

- `docker login` 成功。
- Backend 固定 digest 拉取成功。
- Admin 固定 digest 拉取成功。
- `docker image inspect` 可以查询三张本地镜像。
- 重新登录子账号后仍能进入个人版并管理自身 TCR 固定密码。

### 11.2 权限配置复核

在 CAM 用户详情中确认：

- 直接策略只有 `TCRPersonalPullerPinjieFullstackBase`。
- 用户组没有 TCR 写权限。
- 没有管理员或其他产品策略。
- 没有 `SecretId` 和 `SecretKey`。

### 11.3 负向验收

必须确认以下能力没有授权：

- 推送镜像。
- 创建或删除仓库。
- 删除镜像版本或标签。
- 修改仓库公开或私有属性。
- 拉取未列入策略的其他仓库。
- 访问其他腾讯云产品资源。

不要在两个生产仓库中实际执行写入或删除命令来测试拒绝。CAM 策略复核已经可以证明没有对应允许动作。

确需实测 Push 拒绝时，先专项授权创建独立的临时验证仓库和无业务标签。测试必须保证即使权限错误地放宽，也不会覆盖生产内容；验证后删除仓库属于另一个破坏性操作，需要单独授权。

可以安全测试一个明确存在但未授权的只读测试仓库：拉取必须返回无权限。不要通过猜测其他项目仓库名称进行测试。

## 12. 常见问题和处理顺序

### 12.1 `SecretId` 和 `SecretKey` 显示为 `-`

这是预期结果。当前 Docker 拉取流程不需要 CAM API 密钥。

### 12.2 TCR 控制台提示没有权限

依次检查：

1. 登录的是主账号下正确的 `tcr-puller`。
2. 完整 Puller 策略是否已经直接关联，不能只粘贴第二段仓库权限。
3. 第一段是否包含报错中的 `tcr:ValidateUserPersonal`，资源是否为 `*`。
4. JSON 的产品前缀是否为 `tcr`，不能继续使用旧 `ccr` 写法。
5. 第二段资源路径是否准确包含主账号 UIN、命名空间和仓库名称。
6. 保存策略后是否重新登录子账号并等待 CAM 权限生效。

统一 TCR 控制台可能查询与拉取无关的全局接口。无关页面提示不构成扩大权限的理由，以两个固定 digest 能否拉取作为生产验收事实。

### 12.3 `cam:GetRole` 没有权限

该错误表示当前控制台页面正在读取一个 CAM 角色，不代表两仓镜像拉取权限不足。TCR 个人版通过 CAM 子用户和个人版固定密码完成 Docker 登录，`tcr-puller` 不需要扮演 CAM 角色。

处理顺序：

1. 确认没有把“CAM 角色”“服务级账号”或企业版实例流程当作个人版子用户流程。
2. 返回 TCR 个人版的凭证或仓库页面，继续使用 CAM 子用户入口。
3. 不要直接添加 `cam:GetRole` 的 `resource: ["*"]`，也不要附加 CAM 只读或管理员预设策略。
4. 如果个人版初始化或密码管理的必经页面仍因该调用完全阻塞，记录报错中的准确角色资源、页面路径和 Request ID，由主账号核对角色用途及腾讯云当前官方要求。
5. 只有确认该角色读取是当前必需依赖后，才建立独立策略，仅允许 `cam:GetRole` 读取报错中的准确角色资源，并重新执行两仓 Pull 和无 Push 权限验收。

`cam:GetRole` 不能写入 TCR 两仓只读策略的仓库级权限段。无法证明必需时不授权，避免生产拉取身份获得无关 CAM 资源可见性。

### 12.4 `unauthorized: authentication required`

常见原因：

- Registry 用户名错误。
- 使用了 CAM 控制台密码或 `SecretKey`。
- TCR 个人版登录实例尚未初始化。
- TCR 固定密码已经重置。
- Docker 凭据保存在另一个 Linux 用户的主目录。

先重新执行交互式 `docker login`，不要直接修改策略。

### 12.5 `denied: requested access to the resource is denied`

这通常说明身份认证成功，但资源权限或镜像路径不匹配。检查：

- 是否缺少 `tcr:PullRepositoryPersonal`。
- 仓库名称是否完全一致。
- 命名空间是否为 `pinjie-mall`。
- 策略是否关联到当前子用户。
- 当前执行 Docker 的 Linux 用户是否正确。

### 12.6 `manifest unknown`

这通常说明标签或 digest 不存在。回到 CNB 发布清单核对完整 digest。不要改用 `latest` 规避错误。

### 12.7 可以拉取，但意外可以推送

立即停止使用该凭证并检查：

- 用户是否附加了 `tcr:*`。
- 用户是否加入了带写权限的用户组。
- 是否复用了 `tcr-publisher` 的密码。
- 是否存在 TCR 全读写预设策略。

移除多余策略后重置 TCR 固定密码，并更新全部服务器凭据。不要继续部署。

### 12.8 找不到服务级账号

当前使用个人版，服务级账号属于企业版功能。这是产品版本差异，不是 CAM 权限缺失。

### 12.9 多个地域密码同时失效

个人版固定密码全地域一致。任一地域重置后，使用该 CAM 身份的其他地域和服务器都需要重新登录。

### 12.10 企业认证是否阻止使用个人版

不会因为企业认证自动失去个人版资格。是否可用以当前账号的 TCR 控制台、个人版实例和已创建资源为准。企业认证也不会把个人版自动升级为企业版。

## 13. 轮换、禁用和泄露处理

### 13.1 正常轮换

1. 盘点 `tcr-puller` 在哪些服务器和地域使用。
2. 确认当前两个运行镜像 digest 和回滚镜像均已记录。
3. 使用子用户登录 TCR 控制台重置个人版固定密码。
4. 在每台服务器使用正确 Linux 部署用户重新执行 `docker login`。
5. 逐台拉取一个已存在的固定 digest。
6. 确认旧密码无法再登录。
7. 更新凭证轮换记录，不记录明文密码。

### 13.2 服务器下线

1. 确认服务器不再承担部署或回滚。
2. 在该服务器执行 `docker logout ccr.ccs.tencentyun.com`。
3. 删除服务器或用户主目录属于外部破坏性操作，按基础设施流程单独授权。
4. 如果凭证曾被多台服务器共享，评估是否立即轮换固定密码。

### 13.3 凭证疑似泄露

1. 立即停止新的生产部署。
2. 在 CAM 禁用 `tcr-puller`，阻断后续访问。
3. 检查账号是否被增加其他策略或加入用户组。
4. 重置 TCR 固定密码。
5. 移除泄露来源中的旧凭证。
6. 重新启用前恢复两仓只读策略并完成正向、负向验收。
7. 核对 TCR 和 CAM 可用日志。个人版审计能力有限时，应明确记录证据缺口。

禁用 `tcr-puller` 不影响已经运行的容器，但会阻止后续拉取、重建和回滚。处置前必须保存当前运行版本和本地镜像状态。

## 14. 最终检查清单

- [ ] 主账号未用于 Docker 登录。
- [ ] `tcr-publisher` 只保存在 CNB 密钥仓库。
- [ ] `tcr-puller` 已创建为可访问资源的 CAM 子用户。
- [ ] 未创建 CAM API 密钥。
- [ ] 只关联完整的 `TCRPersonalPullerPinjieFullstackBase` 策略。
- [ ] 第一段包含 `tcr:ValidateUserPersonal`、初始化和密码管理动作，资源为 `*`。
- [ ] 没有管理员、TCR 全读写或其他产品策略。
- [ ] 用户组没有叠加写权限。
- [ ] TCR 用户名来自子用户控制台实际命令。
- [ ] TCR 固定密码只保存在受控密码管理器和目标服务器。
- [ ] 登录操作使用后续运行 Compose 的同一 Linux 用户。
- [ ] 三张镜像均按 CNB 发布清单中的完整 digest 拉取成功。
- [ ] 未使用 `latest`、候选标签或缓存标签。
- [ ] 已记录轮换、禁用和泄露处理责任人。

## 15. 腾讯云官方依据

以下官方文档于 2026-09-01 复核：

- [TCR 个人版授权方案示例](https://cloud.tencent.com/document/product/1141/41409)
- [TCR 个人版接入 CAM 的 API 列表](https://cloud.tencent.com/document/product/1141/41415)
- [TCR 个人版资源级 API 接口及授权方案变更指南](https://cloud.tencent.com/document/product/1141/41412)
- [TCR 个人版更新登录密码](https://cloud.tencent.com/document/product/1141/63912)
- [TCR 服务级账号管理](https://cloud.tencent.com/document/product/1141/89137)
- [CAM 新建子用户](https://cloud.tencent.com/document/product/598/13674)
- [CAM 创建子账号并授权](https://cloud.tencent.com/document/product/598/54458)
- [CAM 通过策略生成器创建自定义策略](https://cloud.tencent.com/document/product/598/37739)
- [CAM 容器镜像服务接口授权粒度](https://intl.cloud.tencent.com/document/product/598/57160)

腾讯云控制台按钮和接口清单可能变化。后续执行时，如果官方当前页面与本手册冲突，以官方当前权限模型为准，并先更新本手册再扩大权限。
