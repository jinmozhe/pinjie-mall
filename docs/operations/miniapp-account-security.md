# 小程序账户设置、会话管理与注销前置核对

## 1. 入口与运行

个人中心新增账户设置入口。账户分包包含 settings、sessions、closure 三页；设置、隐私、注销说明及公开帮助无需登录，登录会话和本人交易权益核对经 AuthGate 展示。AppID 保留 touristappid，服务端微信登录默认关闭，未登录时不生成私有示例数据。

本地开发仍从根目录运行 `pnpm --filter @pinjie/miniapp dev:weapp`，微信开发者工具加载 apps/miniapp/dist，watch 持续增量编译，无需每次手工完整构建。配置或依赖改变时重启 watch。取得实际 AppID 后按[身份手册](miniapp-identity-and-content.md)和[本地开发手册](local-dev-environment.md)配置平台、域名及服务端秘密。小程序不启动 HTTP/Web 服务。

## 2. 本人会话接口

所有接口位于 ConsumerBearer 边界，拒绝 Cookie 凭据，响应 no-store；不接受前端指定用户身份。

| 操作 | 接口 | 边界 |
| --- | --- | --- |
| 分页列表 | `GET /api/v1/users/me/sessions` | page 至少 1，page_size 默认 10、最多 100；ID 倒序，只包含本人 miniapp_bearer、pinjie-miniapp 会话 |
| 明确集合撤销 | `POST /api/v1/users/me/sessions/revoke` | session_ids 为 1 至 100 个唯一 UUID；拒绝当前、他人、Browser 或缺失目标，整批事务回滚 |
| 原目标查询 | `POST /api/v1/users/me/sessions/revocation-status` | 同一集合，只读返回 active、expired、revoked 或 not_found，不执行撤销 |
| 注销咨询核对 | `GET /api/v1/users/me/closure-precheck` | 只读本人事项，self_service_enabled 恒为 false |

列表仅展示会话标识、展示名称、登录/活动/闲置截止/最长有效时间、撤销时间、当前标记与遮掩网络段。原始 IP、UA、Token、族标识及微信身份不公开。名称与网络段不能证明物理设备身份，同一设备重复登录可产生多个会话。

列表额外返回其他有效会话总数与最多 100 个 ID。用户确认的撤销目标是当时读取的明确集合，后来登录的会话不会被加入；超过 100 个需刷新后另行确认下一批。当前会话使用退出登录，不能通过此接口撤销。

应用服务锁本人用户、复核当前会话与凭据版本，按固定 ID 顺序锁原目标。撤销、安全登录事件和成功审计在同一事务完成，独立审计意图写入失败则不执行。重复原集合保持幂等，不改写既有 revoked_at。Access 与 Refresh 均检查父 Session 的撤销事实，后续认证立即拒绝；不额外锁 Refresh 行，保持既有 Refresh 的 token 到 session 锁顺序。已开始的请求不保证回滚，交易结果需查询。撤销本身没有恢复登录能力。

## 3. 未知结果与恢复

发送前按本人用户命名空间 pinjie.session-revocation 保存 version=1、userId 与原 session_ids，不保存凭据；存储失败则不发送。初次挂载及页面再显示都会读取原记录，重启或重新登录原账户后可继续查询。

网络或响应失败保留原记录，页面提供查询原目标结果。只有响应目标与原集合完整一致且全部 revoked 或 expired，才能声明原目标均失效并清除记录；not_found 不能代替撤销成功。已确认失效但本机清理或列表刷新失败单独提示，不改写为未知结果。

原目标仍有效时，用户可再次确认后主动恢复同一集合；不自动重放，也不把新会话加入原记录。损坏的记录或本机读取失败阻止新的撤销并提供帮助。旧账户响应通过 session.epoch 隔离，退出清除私有缓存，原恢复记录只供本人后续核对。

## 4. 注销核对及关闭边界

核对通过单条 PostgreSQL SELECT 的同一语句快照读取以下事项，返回布尔线索与查询时间，不返回金额或他人记录，也不创建钱包或积分账户。

| 事项 | 本次需要进一步核对的事实 |
| --- | --- |
| 订单与履约 | pending_payment，或 paid 且未完成/取消履约 |
| 付款 | created、pending 或 unknown |
| 售后申请 | requested 或 approved |
| 退款执行 | 未 succeeded/closed，或 succeeded 缺 confirmed_at；通过本人订单确定归属 |
| 提现 | 未 succeeded/rejected，或 succeeded 缺 confirmed_at |
| 佣金 | 本人作为受益人的 frozen 记录 |
| 钱包 | 任一轨道可用、冻结或欠款不为零 |
| 积分 | 可用、冻结或欠款不为零 |

未开通钱包/积分账户与已开通零余额分别展示。查询失败不显示“无待处理事项”；全部 false 也不表示符合最终注销资格。核对结果仅用于咨询，交易仍可能变化。

实际注销关闭，不提供注销申请提交、删除账户、身份解绑、余额/积分放弃或交易终结操作。联系运营不表示申请已受理。后续必须先确定重新确认身份、未结清交易、权益处置及历史保留规则；订单、资金流水与审计不能承诺立即物理删除。

帮助入口复用服务端公开电话/邮箱；未配置时明确显示未配置，不伪造联系渠道。平台服务隐私保护指引与必要授权须在真实能力开放前完成，页面阅读及本机确认记录不能替代平台授权。

## 5. 验证与后续验收

轻量门禁按 Backend、Miniapp、生成客户端消费者及仓库文档规则执行。回归源码覆盖安全投影、目标限制、身份边界、原集合确认、本机账户隔离，以及真实 PostgreSQL 下的本人/Browser/他人过滤、整批拒绝、同集合重复、新会话保留、当前会话复核与只读权益核对；测试资产存在不表示动态测试已执行。

本阶段未执行 pytest、Vitest、微信编译、工具/真机、数据库动态验证和资金渠道验收。后续需独立授权核验双端登录、撤销后 Access/Refresh 拒绝、并发撤销与刷新、审计故障回滚、未知结果重启/同集合恢复、账户切换、全部核对来源与平台隐私流程，以及窄屏、长文本和安全区。

官方核验依据：2026-10-09 查询[微信确认弹窗](https://developers.weixin.qq.com/miniprogram/dev/api/ui/interaction/wx.showModal.html)、[微信分包页面导航](https://developers.weixin.qq.com/miniprogram/dev/api/route/wx.navigateTo.html)与[微信隐私授权](https://developers.weixin.qq.com/miniprogram/dev/framework/user-privacy/PrivacyAuthorize.html)。确认按钮使用最多四字文案，三个账户页面采用非 TabBar 分包导航，平台授权与本机阅读记录分别处理。
