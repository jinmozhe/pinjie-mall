# 微信小程序协作规则

本文件适用于 `apps/miniapp/**`。先读取根 `PROJECT_INDEX.md` 和根规则，再读取[工程标准](../../docs/architecture/miniapp-engineering-standard.md)、[架构设计](../../docs/architecture/miniapp-architecture.md)、[UI 规范](../../docs/architecture/miniapp-ui-standard.md)及任务相关[小程序 PRD](../../docs/MINIAPP_PRD.md)章节。

## 当前状态与工程边界

- 工程、公开浏览、独立微信会话、个人中心、地址、购物车、结算、订单、履约售后评价、公开帮助、资料头像、会员与双钱包流水/佣金/历史提现、推荐分享/主动绑定、本人积分查询及受限说明已有源码；默认登录关闭，新提现申请未开放，真实平台、数据库升级与资金渠道未验证。开发脚本和轻量门禁见工程标准，微信工具与真机验收独立留证。
- 技术路线为 Taro React、NutUI React-Taro、TanStack Query、Sass，只构建 weapp。精确版本由工程标准维护，初始化遵循单一全栈计划。
- 不创建 H5/Web 目标，不启动 HTTP 开发服务，不监听或暴露 3000。开发产物由微信开发者工具加载。
- 根 pnpm workspace 和锁文件是唯一依赖入口。小程序独立 React 18，不改变 Admin React 19，不忽略 peer 冲突或无范围放行构建脚本。

## 代码、契约与体验

- 页面组合 Feature 公开入口，跨 Feature 禁止穿透内部路径；纯 domain 不依赖 UI、平台或 I/O。
- 请求只通过应用传输/认证层，使用 Taro.request/uploadFile；既有生成类型只经 packages 公共入口消费，禁止复制 DTO、手改契约或导入 Admin 源码。
- 服务端数据由 Query 管理，购物车角标派生，交互状态优先局部；Token、session_key 与秘密不进入业务 Store、URL、日志或客户端配置。
- 价格、库存、订单、退款与佣金由 Backend 裁决；未知写结果不得自动重放或展示假成功，支付弹窗成功仍须查询后端事实。
- 商品说明仅渲染服务端标记 restricted_html_v1 的受限 HTML，使用 mp-html 原生组件；未审计 legacy 内容不公开渲染，独立图集保留，迁移和退役遵循工程标准及 ADR 0018。
- 颜色、字体、间距、点击区、组件和页面状态遵循 UI 规范，不新增未授权业务入口或另一套主题。

## 验证与收尾

- 初始化后日常只运行适用 typecheck、lint、边界与契约检查。当前任务未明确点名时，不执行 production build、Vitest、pytest、微信自动化、真机、数据库或渠道验证。
- 修改 Markdown 运行根 `pnpm lint:md`；治理与架构变化运行 workspace、boundaries 及适用文档门禁。
- 预览、上传、提审、发布和 Git 动作分别授权。交付区分文档定版、源码实现、验证与上线。
- 只清理本次可确认归属的临时产物、服务和测试进程，保留用户原有文件和服务，禁止结束 Codex 与浏览器总会话。
