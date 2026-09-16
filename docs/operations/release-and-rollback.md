# 发布与回滚手册

## 1. 适用范围

本手册适用于 Pinjie Mall 的 Backend 与 Admin 镜像发布、生产部署和应用回滚。任何真实发布、部署和回滚都需要用户分别授权。操作人员的完整界面和命令顺序见[GitHub 到 1Panel 端到端人工发布手册](github-cnb-tcr-1panel-release-runbook.md)，每个 GitHub Actions 工作流的机制和失败定位见[GitHub Actions 工作流说明](github-actions-workflows.md)。`apps/web` 已冻结，不参与发布、部署或回滚。

## 2. 职责分离

| 流程 | 输入 | 输出 | 是否接触生产 |
| --- | --- | --- | --- |
| CI | Pull Request 或提交 | 质量与安全验证结果 | 否 |
| 镜像发布 | 完整 40 位 Commit SHA 和路径影响集合 | 受影响应用各自的 digest、SBOM 和构建证明 | 否 |
| 生产部署 | 目标端已验证的镜像 digest | 1Panel 部署与版本记录 | 是 |
| 回滚 | 目标端上一个已验证 digest | 恢复后的部署记录 | 是 |

CI 通过不自动授权镜像发布，镜像发布完成不自动授权生产部署。

## 3. 发布前检查

1. 确认目标 Commit SHA 为完整 40 位十六进制值且存在于受保护分支。
2. 确认适用轻量 CI 全部通过，并选择源码交接验证模式。默认 `strict` 要求同一 Commit SHA 的完整验证 Artifact 仍在保留期内；`fast` 只用于已评估的低风险改动，必须记录原因并明确接受 pytest、Vitest、production build 和 Playwright 未验证的风险。
3. 确认 OpenAPI、生成客户端、迁移和文档不存在未提交漂移。
4. 确认安全扫描、依赖审查和容器扫描满足当前门禁。
5. 确认数据库迁移的前向、回滚或恢复策略已经评审。
6. 确认生产配置、Secret 名称和权限没有在日志中暴露。
7. 确认每个待部署端的当前 digest、目标 digest、回滚 digest 和数据库兼容范围。
8. 确认维护窗口、负责人、观察时长和停止条件。

任一关键证据缺失时停止，不使用 `latest`、重新构建旧版本或跳过检查替代。

## 4. 镜像发布

镜像发布分为 GitHub 源码交接和 CNB 构建发布两段，两段继续使用同一完整 Commit SHA：

1. 人工触发 GitHub `Handoff Source to CNB`，输入完整 40 位 Commit SHA，默认选择 `strict`；只有已评估的低风险改动才选择 `fast` 并填写不含敏感信息的单行原因。
2. GitHub 确认工作流从默认分支启动，检出指定提交并核对 `git rev-parse HEAD`。
3. GitHub 确认指定提交属于默认分支历史，且同一 SHA 的 Governance、Backend、Frontend 和 Security 四个 Push Run 全部成功。
4. `strict` 模式下载未过期的 `full-validation-<完整提交>` Artifact，核对 Full Validation Run、Commit SHA、pytest、Vitest、production build、Chromium Playwright、PostgreSQL 和 Redis 证据字段；`fast` 模式跳过该项，但在 Workflow Summary 中记录 Commit、操作者、模式、原因和未执行完整验证的事实。
5. GitHub 使用受 `cnb-source-handoff` Environment 保护的最小权限 Token，把批准提交以非强制、只能快进的方式更新到 CNB `main`；CNB 已有提交不是目标 SHA 的祖先时停止。
6. CNB `main` Push 自动触发 `.cnb.yml`，再次核对仓库、分支、工作区 `HEAD` 和 `CNB_COMMIT` 完全一致，并按 Docker 构建输入选择受影响的应用 Pipeline。
7. 每条受影响 Pipeline 使用固定 digest 的构建环境和 Trivy，只构建一个固定应用，不读取或更新 TCR 远程 Registry 缓存，以 `candidate-<CNB Build ID>` 唯一候选标签推送到 TCR。
8. 每条 Pipeline 对自己的候选 digest 执行 High、Critical 且已有修复的漏洞阻断，生成 CycloneDX JSON SBOM，验证 BuildKit 最大级别 provenance、TCR attestation manifest 和 OCI 来源标签。
9. 单端候选通过后检查该仓库的 `sha-<完整提交>` 标签；标签指向不同 digest 时立即失败，无冲突时创建标签并执行写后复核。
10. 每条 Pipeline 生成 `pinjie-cnb-tcr-image-v1` 单镜像清单，保存应用键、Build ID、Build URL、Git Commit 时间、完整 Commit SHA、TCR digest、扫描、SBOM、provenance 和 OCI 标签，并连同该端原始证据作为构建附件保留。

GitHub 源码交接成功只说明 CNB 已接收批准提交，不能表述为镜像发布成功。`candidate-<CNB Build ID>` 标签只用于本次构建、扫描和证据核对，禁止部署。单端变化时可以独立发布该端，未改动端保留既有已验证 digest；多端变化时必须等待预期 Pipeline 全部成功并核对相同 Commit SHA，同时评估共享契约和数据库兼容性。任一预期端失败、缺失或错误跳过时部署停止。生产始终使用完整 digest，人工核验后直接由 1Panel 拉取部署，不重新构建镜像。

当前单维护者生产流程不要求 `Validate Candidate Images`、部署组合 JSON 或自动变量预检，操作顺序与发布记录统一见[端到端人工发布手册](github-cnb-tcr-1panel-release-runbook.md)。新版严格源码门禁使用 `pinjie-full-validation-v2`；CNB 扫描保留完整包与漏洞 JSON，通过离线转换生成表格和 CycloneDX，再以结构化检查阻断已有修复的 High/Critical。未修复漏洞继续出现在完整报告中，不能表述为没有任何已知高危漏洞。

首次运行、变更文件超过 CNB 的 300 文件统计上限、Git 对比不可用或影响范围存疑时，在 CNB `main` 分支详情页人工触发“Backend 与 Admin 全量镜像构建”。该操作属于独立镜像发布授权，不能由源码交接成功自动替代。

候选镜像因基础镜像中的可修复 High 或 Critical 漏洞失败时，先核对固定基础镜像摘要和上游修复版本。需要更新摘要时必须形成新提交，重新取得轻量 Push 工作流，并按重新选择的 `strict` 或 `fast` 模式完成源码交接；禁止移动既有 Tag、覆盖既有不可变标签、跳过扫描或把失败候选 digest 用于部署。

## 5. 生产部署

当前生产通过 1Panel 人工从 TCR 拉取固定 digest 并更新编排。仓库中的 `Deploy Production` 仍核对旧 GHCR 镜像源，必须保持 `PRODUCTION_DEPLOYMENT_ENABLED=false`，不能用于当前 TCR 生产链路。

部署前：

1. 取得每个受影响端的 `pinjie-cnb-tcr-image-v1` 清单，核对 Commit SHA、CNB Build ID 和完整 TCR `image.reference`。
2. 记录 Backend 与 Admin 当前 digest 和上一组已验证 digest。
3. 确认部署目录的 `apps/backend/.env` 已配置共享 PostgreSQL、Redis 连接及其他生产运行变量且未进入仓库，根 `.env` 只保存 Compose 镜像引用。
4. 确认当前数据库 Revision、目标 Revision 和备份恢复点。
5. 确认服务器 `compose.prod.yml` 与目标 Commit 中的文件一致。
6. 验证 `compose.prod.yml` 展开结果只包含固定 digest。
7. 在 1Panel 镜像页使用生产只读 TCR 账号拉取每个目标 digest。

部署时：

1. 保证同一环境同一时间只有一个发布或回滚操作。
2. 只更新受影响端的根 `.env` 镜像变量，并同步到 1Panel 编排环境变量页面。
3. 首次部署或包含迁移时，先完成备份，再执行 Alembic 和权限同步。
4. 保存或更新 1Panel 编排，等待 Backend 健康后再确认 Admin。
5. 逐个确认运行容器记录的镜像引用与批准 digest 完全一致。
6. 达到停止条件时立即中止后续步骤，不自动选择其他版本。

部署后：

1. 查询实际运行容器 digest，并与输入逐一比较。
2. 分别记录 Backend 与 Admin 的 Commit SHA、CNB Build ID、镜像 digest、数据库 Revision、执行者、时间和验证结果。
3. 在观察窗口检查错误率、关键延迟和日志异常。
4. 未完成真实核验时不能标记部署成功。

## 6. 回滚决策

满足以下任一条件时评估回滚：

- Readiness 持续失败。
- 关键用户流程不可用或错误预算快速消耗。
- 数据校验失败或出现不可接受的不一致。
- 安全控制失效或发现高危暴露。
- 实际运行 digest 与批准输入不一致。

回滚使用上一个已验证 digest，禁止从旧源码临时重建。数据库已经执行向前迁移时，先判断旧应用是否仍兼容当前结构；无法证明兼容时按数据库恢复方案执行，不能只回滚应用。

## 7. 回滚步骤

1. 宣布进入回滚，暂停新的部署和高风险写操作。
2. 核对目标环境、当前 digest、回滚 digest 和数据库 Revision。
3. 确认回滚版本仍在镜像仓库且签名、SBOM 和来源证明可验证。
4. 执行数据库降级或恢复时再次取得专项授权。
5. 部署固定回滚 digest。
6. 验证探针、关键用户流程、数据摘要和审计链。
7. 记录原因、实际恢复时间、数据损失窗口和遗留风险。

## 8. 禁止事项

- 禁止 `latest`、分支标签和缺失版本默认值。
- 禁止在 CI 工作流中保存生产 SSH 密钥或执行生产部署。
- 禁止因应用回滚方便而执行未验证的数据库降级。
- 禁止通过删除健康检查、关闭安全扫描或扩大权限使部署变绿。
- 禁止把 Workflow 启动成功表述为生产部署成功。
