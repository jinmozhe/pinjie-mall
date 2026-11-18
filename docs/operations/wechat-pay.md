# 小程序微信支付配置与恢复

## 1. 当前能力与启用边界

源码支持普通商户直连、微信支付 APIv3、公钥验签模式。包含下单、本人支付查询、持久通知接收、查单关单、退款恢复、日账单核对、微信发货上报和平台收货查询。默认关闭支付及发货管理，服务商、子商户、平台证书模式和多商户未实现。

迁移文件为 `apps/backend/alembic/versions/20261118_01_wechat_pay.py`，前序版本 `20261013_01`。本次未执行数据库升级、真实微信调用、真实资金验收或部署。仅填写配置不能证明可以正式收款。

## 2. 商户及平台准备

1. 核实普通商户 JSAPI/小程序支付权限、小程序认证及商户号与 AppID 双向绑定。
2. 小程序后台配置实际 API 的请求合法域名。小程序无需 JSAPI 支付授权目录，不用 API 根地址代填。
3. 获取商户 API 证书序列号、对应商户私钥、APIv3 密钥、微信支付公钥及公钥 ID。AppSecret 只用于小程序接口。
4. 核实商户当前公钥模式及共用商户号的其他系统。当前只加载一个明确公钥 ID，未知 ID 拒绝；配置版本记录用于追溯，不提供历史多密钥自动选择。轮换先确认微信通知签名切换窗口和其他系统，安排受控更新及补查，不能删除未结清商户的恢复配置。
5. 核实订单发货管理权限、运力 ID、实物/虚拟交付和确认收货组件可用性。
6. 配置公网 HTTPS、正确 Host、证书及反向代理。通知路径不做登录跳转、验证码或正文改写；保留微信签名头并同步服务器时钟。

## 3. 配置项

公开模板位于 `apps/backend/.env.example`。实际秘密通过宿主机受控环境或秘密管理设施注入，私钥以只读文件挂载给 API 和 Worker，禁止放入镜像、仓库、uploads 或 settings-media。

| 配置 | 设置要求 |
| --- | --- |
| `WECHAT_PAY_ENABLED` | 默认 false；只控制创建新支付及返回收银台参数 |
| `WECHAT_PAY_RECOVERY_ENABLED` | 默认 false；启用后加载渠道客户端，保留通知、查关单、退款和账单能力 |
| `WECHAT_APP_ID` | 已绑定的小程序 AppID，与可信身份及实际客户端一致 |
| `WECHAT_PAY_MCH_ID` | 普通商户号 |
| `WECHAT_PAY_MERCHANT_SERIAL_NO` | 与商户私钥对应的 API 证书序列号 |
| `WECHAT_PAY_PRIVATE_KEY_PATH` | 服务端可读的 RSA 2048 商户私钥绝对路径 |
| `WECHAT_PAY_API_V3_KEY` | 32 字节 ASCII 密钥，用于通知解密 |
| `WECHAT_PAY_PUBLIC_KEY_ID` | 微信支付公钥 ID，以 PUB_KEY_ID_ 开头 |
| `WECHAT_PAY_PUBLIC_KEY_PATH` | RSA 2048 微信支付公钥文件绝对路径 |
| `WECHAT_PAY_NOTIFY_URL` | 支付通知完整 HTTPS 地址 |
| `WECHAT_PAY_REFUND_NOTIFY_URL` | 退款通知完整 HTTPS 地址，每笔退款显式传入 |
| `WECHAT_PAY_CONFIG_VERSION` | 运维维护的非秘密版本标识 |
| `WECHAT_SHIPPING_ENABLED` | 默认 false，启用须同时保留支付恢复及正确 AppSecret |
| `WECHAT_SHIPPING_CARRIERS` | JSON 对象，将商城承运人名称精确映射为微信运力 ID |

候选通知地址如下，仍需目标环境核验：

```text
https://api.guizhouzhongying.com/api/v1/payments/wechat/notify
https://api.guizhouzhongying.com/api/v1/refunds/wechat/notify
```

使用自定义 `API_V1_STR` 时两条 URL 路径必须同步。地址不允许认证信息、查询串或片段。启用但缺少材料时启动失败；所有开关为 false 时可保持空配置。

## 4. 部署准备顺序

1. 按现有备份及发布手册确认目标库、备份、恢复方式和固定镜像 digest。新迁移执行前检查是否有同订单多个 created/pending/unknown 微信意图；存在时人工核对，不删除旧资金事实。
2. 经独立授权升级目标库到 `20261118_01`。Readiness 的迁移版本检查会拒绝旧结构；代码不能直接部署到未迁移的库。
3. 在 API 和 Worker 注入相同商户配置，挂载相同只读密钥文件。沿用生产受控配置及进程托管；本次未更改生产 Compose 或启用任何服务。
4. 先设置恢复开关为 true、新支付为 false，检查客户端加载、通知公网路径、数据库连接、Worker 和任务告警。
5. 为 Worker 配置重启策略、日志采集及单实例或多实例租约执行。不要在每个 API 请求中启动后台循环。
6. 完成已授权的协议、并发、真实支付、退款、发货及真机验收，再开启新支付。

## 5. Worker 与异常任务接续

以下命令从 `apps/backend` 执行，替换目标库名。没有 `--apply` 的 Worker 命令只统计到期任务；不执行渠道调用。命令列示不代表已执行。

```powershell
uv run python -m scripts.run_durable_tasks --confirm-database YOUR_DATABASE
uv run python -m scripts.run_durable_tasks --confirm-database YOUR_DATABASE --apply --watch --limit 25 --lease-seconds 60 --retry-delay-seconds 60 --poll-seconds 5
```

每次仅领取一个任务再执行，`limit` 为每轮上限。渠道 Worker 租约至少 45 秒，默认 60 秒。正常等待用 `TaskDeferred` 延后，不增加失败次数；异常使用持久失败计数，到阈值进入 attention。支付任务阈值为 10，其他既有任务沿用创建时阈值。查单正常等待每 15 秒，退款处理中每 60 秒；支付未决超三天、退款处理中超七天转异常接管。请求失败、配置错误和微信 ABNORMAL 也会进入失败计数。

运营通过既有持久任务与资金查询页面检查 task ID、类型、revision、失败码、未决时长及对应订单。修复配置、平台异常或业务数据原因后，才使用以下精确恢复入口：

```powershell
uv run python -m scripts.recover_durable_task --confirm-database YOUR_DATABASE --task-id TASK_UUID --revision 12 --operator OPERATOR --reason "已核对平台状态并修复配置"
uv run python -m scripts.recover_durable_task --confirm-database YOUR_DATABASE --task-id TASK_UUID --revision 12 --operator OPERATOR --reason "已核对平台状态并修复配置" --apply
```

恢复仅接受 attention 及准确 revision，同事务将任务改为 pending、重置当前失败计数并写入审计，保留历史总执行数及原错误；不修改支付、退款或钱包事实。审计操作者名称由受控宿主机操作人员提供，须关联主机访问记录。禁止定时批量重置 attention。

必须部署的观测项：Worker 存活、pending 最老时间、attention 数量、通知拒绝/落库失败、未处理通知、未决支付/退款、对账差异及发货上报失败。当前代码提供任务状态和脱敏错误日志，外部告警规则尚未部署。

## 6. 日账单核对

```powershell
uv run python -m scripts.reconcile_wechat_bill --confirm-database YOUR_DATABASE --date 2026-11-17
uv run python -m scripts.reconcile_wechat_bill --confirm-database YOUR_DATABASE --date 2026-11-17 --apply
```

只允许中国时区已结束且距今 90 天内的账单日。默认仍会访问微信下载账单，但不写对账记录；`--apply` 逐条幂等写入。分别申请 SUCCESS 与 REFUND，元数据验签后只访问固定官方下载地址，校验 SHA1 和交易条数；原账单及 OpenID 不落盘、不输出。

金额取订单金额及申请退款金额，退款非成功行只统计，不伪造退款完成。跨日重复退款按不变资金事实形成同一来源摘要，结算手续费等可变化字段不参与幂等。账单不存在、格式变化、摘要错误或下载失败明确报错；不得把“未取得账单”登记为核对通过。前半账单已落库后失败，可按同日期重跑；缺失本地资金事实形成 discrepancy，不自动确认资金成功。

本入口未配置每日定时器。上线时由受控调度每天运行已生成的前一日账单，保留成功日期、条数、差异及失败接续证据。

## 7. 交易恢复与发货

- 同一用户请求号恢复原意图，单订单只允许一个活动微信意图；新商户支付号为 32 位 UUID v7 十六进制值。
- 下单超时、断连或验签失败保存 unknown；持续按原号查询，查无单才按同号条件恢复。取消与到期先核对渠道，渠道关单确认后才释放。已付或迟到资金分别进入成交或异常退款。
- 通知先验原始字节签名、解密并可靠保存，4 秒内部预算内完成后空体 204；资金归属、金额等业务核验由持久任务完成，失败可接续。
- 微信退款通知不含 currency，国内协议适配显式归一为 CNY；提交及查退款响应仍校验币种。退款 ABNORMAL 需商户平台处理，CLOSED 保留终态，不自动创建另一笔退款。
- 实物发货与虚拟交付在原业务事务内建立 wechat_shipping 任务，使用实际交易号、支付者身份和固定履约时间重试。物流名称缺映射时明确失败。
- 小程序微信确认收货组件返回后查询平台状态，只有 3（确认收货）、4（交易完成）显示已确认；6（资金待结算）不作收货证明。微信平台状态不会直接改写商城履约。

## 8. 停收与回滚

停止新收款：设置 `WECHAT_PAY_ENABLED=false`，保持 `WECHAT_PAY_RECOVERY_ENABLED=true`、通知可达及 Worker 运行。关闭两个开关会停掉渠道处理，不能用于在途交易停收。

代码回滚必须保留通知与恢复能力。迁移降级在已有渠道支付或通知证据时拒绝执行；不能删除资金证据以强行降级。商户号或 AppID 变化会使旧意图归属检查失败，旧商户恢复需原商户配置的受控处理，当前无多商户自动路由。

## 9. 验证入口

协议回归源码为 `tests/test_wechat_pay_protocol.py`，PostgreSQL 持久性回归为 `tests/test_wechat_pay_persistence.py`，小程序状态边界为 `payment-domain.test.ts`。实际 pytest、Vitest、数据库迁移及微信平台验证需按项目授权执行；静态检查不能代替真实并发、到账、通知公网及发货管理验收。
