# 小程序推荐分享与本人积分查询

## 1. 当前状态与运行方式

推荐与分享、我的积分两个页面已具备源码，入口在个人中心的会员与钱包分组。AppID 继续使用公开游客标识 touristappid，服务端微信登录默认关闭；不伪造私有数据。取得实际 AppID 后，先按[独立身份手册](miniapp-identity-and-content.md)配置服务端秘密、迁移、HTTPS 与合法域名，再进行本地微信平台验收。

开发命令仍为根目录 `pnpm --filter @pinjie/miniapp dev:weapp`，开发者工具加载 dist。watch 持续增量编译，源码修改无需每次手工完整构建；配置、依赖或编译器变化重启 watch。具体导入步骤见[本地开发手册](local-dev-environment.md)。本阶段未启动 watch 或微信工具，未升级依赖、增加迁移或发布。

## 2. 本人推荐关系

| 操作 | MiniappBearer 接口 | 边界 |
| --- | --- | --- |
| 本人推荐查询 | `GET /api/v1/miniapp/referral` | not_opened、unbound、bound；只返回本人邀请码、绑定时间，不输出推荐人身份 |
| 确认原码匹配 | 同路径，带 invitation_code 查询参数 | 8 至 16 位大写字母或数字；matches_invitation 仅表示当前已绑定关系是否匹配指定码，不预览陌生推荐人资料或判断陌生码存在 |
| 主动首次绑定 | `POST /api/v1/miniapp/referral` | invitation_code 输入复用既有领域契约；首次绑定、同码幂等、自邀与循环保护由领域服务裁决 |

打开分享页只保留绑定意图。页面参数仅接收 invite，格式受控，不反复 URL 解码、不跳转用户提供的网址。用户登录后核对当前账户，点击确认并在弹窗再次确认；页面加载、登录成功和分享返回都不会自动绑定。无档案时可以主动到会员中心开通；绑定也按既有领域语义创建本人档案及双钱包。

推荐关系不能换绑，不开放推荐链、团队成员身份列表或有效邀请统计。绑定不承诺积分、会员等级或佣金奖励。不存在的邀请码、自邀、循环和换绑由服务端明确拒绝。

## 3. 未知结果与账户隔离

发送绑定前，按当前用户标识保存版本为 1 的原邀请码；保存失败则不发送。记录位于本机 pinjie.referral 用户命名空间，不含凭据、推荐人身份或资金数据。返回页面、重启或重新登录同一账户可继续查询；其他账户无法加载该记录，也不会自动执行旧操作。

网络、协议、认证及服务故障保留原码，先查询当前关系与指定码是否匹配。仅 bound 且 matches_invitation 为 true 才声明原码绑定已确认；已绑定其他关系显示未匹配并禁止换绑。当前未绑定不证明在途写入失败，保留原码，仅提供用户主动确认的同码幂等恢复，不自动重放或更换邀请码。

本次新写入取得确定的结构拒绝或领域推荐拒绝时可解除意图；此前未知写入的恢复即使失败仍保留原码直到查询确认。恢复记录损坏时阻止新增绑定并提供帮助；存储或查询失败明确反馈。退出取消私有请求与缓存，异步结果通过会话代次隔离，不能回填另一账户。

## 4. 微信分享

采用 Taro useShareAppMessage 页面钩子，页面配置 enableShareAppMessage=true，按钮使用微信原生 openType=share。本人邀请码读取成功后，分享固定路径 `/subpackages/finance/referral/index?invite=本人邀请码`；未登录、查询失败或没有本人码时，菜单分享仅回到公开商城首页，不转发收到的他人邀请码。

分享使用固定 750 × 600 PNG，比例 5:4，构建配置显式复制到 dist/assets/share-mall.png，避免默认截图带出当前账户或积分信息。源文件为 apps/miniapp/src/assets/share-mall.png，生成脚本为 scripts/design/render-miniapp-share-card.py。不制作二维码，不上传平台分享图片，不把分享钩子触发认定为发送成功、有效邀请或收益事实。

## 5. 本人积分

| 操作 | MiniappBearer 接口 | 展示 |
| --- | --- | --- |
| 积分账户 | `GET /api/v1/miniapp/points` | not_opened 的 account=null；opened 返回可用、冻结、追回欠款、账户版本与更新时间 |
| 积分流水 | `GET /api/v1/miniapp/points/ledgers` | 本人账户、page/page_size，默认 10、最多 100，ID 倒序；账户未建立返回明确 404 |

查询不会创建积分账户或奖励。账户未建立、零余额、真实空流水和读取失败分别展示。积分余额与三类流水变化采用精确十进制字符串，禁止用 Number 转换或前端合并成应得余额；积分与人民币钱包分开展示。

流水仅投影记录号、类型、三类变化、来源类别与时间，不输出 account_id、source_id、冲销关联、内部备注或幂等键。历史类别可展示，但不代表对应动作当前开放。有效邀请规则、积分兑换、到期、抵扣及自动订单积分政策保持未启用。

## 6. 官方核验与验收边界

2026-10-09 读取当前在线官方文档，并核对本地锁定 Taro 4.3.0 类型；沿用现有精确技术基线，不按 latest 标签盲目升级依赖。

- [微信 Page 与分享返回契约](https://developers.weixin.qq.com/miniprogram/dev/reference/api/Page.html)：完整路径以 / 开头；自定义图片支持 PNG/JPG，比例 5:4；分享返回数据不构成服务端推荐关系。
- [微信原生 Button](https://developers.weixin.qq.com/miniprogram/dev/component/button.html)：open-type=share 为用户主动触发分享入口。
- [Taro React Hooks](https://docs.taro.zone/docs/hooks)：useRouter 读取页面参数；useShareAppMessage 对应微信分享生命周期，须设置 enableShareAppMessage。
- [Taro Button](https://docs.taro.zone/docs/components/forms/button)：使用原生 openType=share，沿用既有 Sass tokens。

本阶段完成轻量源码、类型、契约和治理检查。pytest、Vitest、微信编译、工具、真机与数据库动态验证未执行。后续取得 AppID 后需核验冷启动分享落地、登录取消与恢复、菜单/按钮分享、非法码/自邀/循环、同码幂等、未知结果重启恢复、账户切换、积分归属与分页，以及窄屏、键盘、安全区和分享封面实际显示。未取得这些证据前不能声明平台或完整业务验收通过。
