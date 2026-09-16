# GitHub、CNB、TCR 与 1Panel 发布手册

## 1. 发布边界

本手册适用于 `pinjie-mall` 的 Backend 与 Admin。发布、部署和回滚均为独立授权动作。Web 不参与源码交接、构建、镜像发布、部署或验证。

| 链路 | 商城资源 | 作用 |
| --- | --- | --- |
| GitHub | `jinmozhe/pinjie-mall` | 代码、轻量门禁与源码交接 |
| CNB | `pjwl/pinjie-mall` | 构建 Backend、Admin 镜像 |
| TCR | `ccr.ccs.tencentyun.com/pinjie-mall` | 生产镜像唯一来源 |
| 1Panel | 商城独立编排 | 使用固定 digest 部署和回滚 |

## 2. 发布前检查

1. 确认目标 Commit 位于默认分支，且对应轻量门禁通过。
2. 在 GitHub 手动交接工作流选择 `strict` 或明确填写理由的 `fast` 模式。
3. 严格模式必须存在同一 Commit 的完整验证证据。快速模式不代表完整测试通过。
4. 确认 CNB 与 TCR 是商城专属资源。任何仓库、命名空间、来源标签或凭据不匹配都应停止发布。

## 3. 镜像发布

CNB 根据变更路径触发 `backend-image` 或 `admin-image`。首次发布、路径判断不可用或需要全量重建时，使用受控全量构建按钮。每个成功镜像必须具有：

- 完整 Commit SHA 对应的不可变标签和 digest
- SBOM、BuildKit provenance 和漏洞扫描证据
- 与当前 CNB Commit 一致的 OCI revision 与 source 标签

记录 Backend、Admin 各自的完整 digest。未受影响的应用可继续使用当前已验证 digest。

## 4. 1Panel 部署

将两张经核验的 digest 写入服务器根 `.env`，在项目目录运行：

```powershell
docker compose --env-file .env -f compose.prod.yml config --quiet
docker compose --env-file .env -f compose.prod.yml pull
docker compose --env-file .env -f compose.prod.yml up -d --wait
docker compose --env-file .env -f compose.prod.yml ps
```

部署后核对：

- Backend `/health/live` 和 `/health/ready`
- Admin `/healthz`
- 两个运行容器的镜像引用与批准 digest 完全一致
- OpenResty 仅代理 API 与 Admin，不存在 Web 服务或 3000 端口

将执行者、时间、Commit SHA、两张镜像 digest、迁移结果和健康检查结果记录到受控发布记录。实际生产操作不得由本地文档或脚本自动触发。

## 5. 回滚

选择上一组已核验的 Backend、Admin digest，重复部署前检查和 1Panel 部署步骤。数据库迁移不能自动回滚；存在结构变更时依据迁移计划、备份和恢复边界执行前向修复或受控恢复。
