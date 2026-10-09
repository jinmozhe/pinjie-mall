# 微信小程序工程实施标准

## 1. 职责与当前状态

本文是 `apps/miniapp` 技术栈、依赖准入、代码、配置和验证的执行标准。技术取舍见 [ADR 0017](../adr/0017-小程序采用TaroReact与NutUI决策.md)，目录与协作机制见[小程序架构](miniapp-architecture.md)，视觉与组件要求见[小程序 UI 规范](miniapp-ui-standard.md)，需求见[小程序 PRD](../MINIAPP_PRD.md)。

2026-10-09：文档基线已定版，应用只有规则文件，尚无 package.json、源码、开发脚本或构建产物。下文中的目标命令和配置在初始化专项落实，不能当作当前可执行入口。元数据核验不等于兼容验收。

## 2. 初始化技术栈与版本

| 能力 | 确定基线 | 执行要求 |
| --- | --- | --- |
| 应用 | `apps/miniapp`、`@pinjie/miniapp` | 独立 pnpm workspace 包，只交付微信 weapp |
| Taro | 4.3.0 | 同序列 CLI、taro、runtime、shared、helper、components、React/微信插件和 runner 精确同版；按官方模板实际需要声明 |
| React | 18.3.1 | 应用内单一实例；不引入 react-dom，不改变 Admin React 19 |
| React 类型 | `@types/react` 18.3.31 | 小程序 tsconfig 只解析本应用匹配的 React 类型 |
| 语言 | TypeScript 5.9.3、strict | 独立 JSX 与平台类型；不直接继承 Admin 的浏览器/Umi 配置 |
| 编译 | `@tarojs/webpack5-runner` 4.3.0 | `compiler.type = 'webpack5'`；其声明 webpack peer 为 5.91.0，初始化须按实际解析核对，不强行覆盖为不支持的版本 |
| UI | `@nutui/nutui-react-taro` 3.0.20 | 明确无后缀稳定版本，不随 latest 自动切换 cpp 或 beta |
| 图标 | `@nutui/icons-react-taro` 3.0.2 | 按需导入，与组件使用的传递图标版本核对去重 |
| 服务端状态 | `@tanstack/react-query` 5.101.4 | Query 缓存、取消、失效和生命周期适配 |
| 样式 | Sass 1.105.1、tokens、NutUI 主题 | 不默认引入 Tailwind、CSS-in-JS 或浏览器字体包 |
| 请求 | Taro.request、Taro.uploadFile | 独立传输与认证，消费根契约生成类型 |
| 内容 | mp-html 2.5.2 | 微信原生组件经 Taro usingComponents 接入，渲染受限商品 HTML；不复制 Admin DOM 组件 |
| 可选状态/校验 | Zustand、Zod | 有跨页状态或必要运行时输入边界才引入，精确版本在对应实施计划与锁文件核验 |
| 逻辑测试 | Vitest 的 node 环境 | 沿用测试策略；平台 UI 用微信工具及真机验证，执行需当前任务明确授权 |
| 预览上传 | miniprogram-ci 2.1.31 | 发布工具独立准入，Node 24、签名和上传链路须单独验证 |
| 环境 | 根 package.json 的 Node 24 基线、pnpm 11.17.0 | 不建立子应用锁文件；后续根基线变化时统一核对 |

本表为初始化精确版本基线，版本升级在工程计划内明确修订，不能运行不带版本的安装命令让发布标签替代决策。2026-10-09 已核对上述固定包的公开版本与适用 peer/engines；尚未安装小程序依赖或做其 frozen 解析。TypeScript 采用 5.9 系列以缩小首次 Taro 接入的工具变化范围，不随最新主版本自动升级。

根 `pnpm-workspace.yaml` 当前 `minimumReleaseAge: 10080` 为七天。Taro 4.3.0 和 Sass 1.105.1 已超过观察期；所有传递依赖仍需实际检查。依赖解析失败、peer 冲突、安装脚本未准入和线上 Security 失败必须如实传播，不关闭信任策略、忽略冲突或无范围更新 allowBuilds。

## 3. 初始化与配置

1. 建立单一全栈实施计划，关联 `BASE-*` 与 `MP-*`，记录接口、身份与验证影响。
2. 从匹配版本的官方 React/TypeScript/Webpack 5 模板提取必要配置，移除演示、H5 目标与无业务用途依赖；保留全部已确认产品能力。
3. 在应用内声明依赖和脚本，从根 pnpm 管理安装与根锁文件；首次安装后复核实际解析和所需构建脚本。
4. 配置 `src/app.tsx`、app.config.ts、主包/分包与原生组件；环境标识、API 和资源 HTTPS 基址显式配置，不猜测环境或回退生产地址。
5. 接入 workspace 状态、TypeScript 公开入口与循环依赖门禁、变更路由和适用 CI。只创建 AGENTS 不表示 ready。

| 目标脚本 | 用途 | 当前状态与授权 |
| --- | --- | --- |
| `pnpm --filter @pinjie/miniapp dev:weapp` | Taro build --type weapp --watch，输出供微信工具加载 | 尚未配置；不启动 HTTP/H5 服务 |
| `pnpm --filter @pinjie/miniapp typecheck` | tsc --noEmit | 尚未配置；初始化后为日常轻量门禁 |
| `pnpm --filter @pinjie/miniapp lint` | 兼容的 ESLint、Hooks 与边界规则 | 尚未配置；初始化后为日常轻量门禁 |
| `pnpm --filter @pinjie/miniapp build:weapp` | Taro 微信生产产物 | 尚未配置；当前任务明确点名才执行 |
| `pnpm --filter @pinjie/miniapp test` | 授权范围内的 Vitest | 尚未配置；普通开发/提交不自动执行 |

公开 project.config.json 只放可公开配置与 AppID。project.private.config.json、真实环境文件、上传私钥、输出目录和日志应加入忽略规则。AppID 可公开，AppSecret、session_key、支付密钥与上传私钥不得进入客户端、仓库或产物。

根 dev 保持 Admin 入口，Backend 本机使用已有 18168，Admin 使用 3001。小程序真机连接可达且符合微信配置的 HTTPS 服务；手机 localhost 不指向电脑。禁止启动 Web、H5 或监听 3000。

## 4. 代码与依赖边界

- pages/subpackages 负责路由、生命周期与页面组合，只通过 Feature 的 index.ts 消费业务能力。
- 同一 Feature 的 UI、Hook、Query、api/service、domain 就近组织；跨 Feature 不穿透内部文件，不使用 export * 暴露全部实现。
- domain 保持纯 TypeScript，不导入 React、Taro、NutUI、Query 或 I/O。最终价格、库存、资格、佣金与退款由 Backend 决定。
- lib/api、lib/auth 和 platform 分别负责传输、会话和微信能力；基础设施不反向依赖具体 Feature。
- Admin、小程序不相互导入源码或 DOM 组件；共享只经 packages 公共入口。生成 API 类型使用 import type，禁止复制 DTO、运行 Admin 请求管道或手改生成文件。
- 导入路径、别名、React 类型解析与 ESLint 配置在初始化时明确校验。不得用 any、强制断言或忽略规则掩盖契约不匹配。

## 5. 数据、请求与恢复

| 场景 | 实施要求 |
| --- | --- |
| 响应 | 分别判断网络、HTTP 和业务响应，统一解包业务数据；平台 success 回调不等于业务成功 |
| 查询 | key 包含资源、参数与私有身份范围；服务端状态只保留于 Query，角标从购物车派生 |
| GET 重试 | Query 默认最多重试一次适用的短暂故障；认证、业务拒绝、取消不重试；遵守 Retry-After，不叠加 transport 重试 |
| 写操作 | Mutation 不通用自动重试；幂等恢复使用相同业务 request_id 与内容，追踪 ID 不充当幂等号 |
| 取消 | AbortSignal 对接真实 RequestTask/UploadTask.abort，并解除监听；客户端取消不证明服务端写未执行 |
| 未知结果 | 先按端点确认策略查询；加购目前无幂等 request_id，不能盲目重发；成交与退款处理中不显示成功 |
| 会话 | access 凭据私有内存持有；单飞恢复一次；认证 API 直接使用 transport，避免递归刷新 |
| 身份切换 | 取消私有请求、清理缓存、递增会话代次，拒绝旧响应回填；旧写操作不得以新身份重放 |
| 生命周期 | 初始网络状态与监听适配 onlineManager，前后台适配 focusManager；隐藏页停止无意义轮询，监听注册一次并清理 |
| 上传 | 单独适配 multipart、字符串响应、HTTP 与业务错误、大小和取消；不套用 JSON 请求假设 |

轮询必须有结束条件、时间上限和退出路径；具体时限由支付状态契约与实施计划定义。禁止离线持久化交易 Mutation 并自动恢复执行。服务端金额按十进制字符串展示，不使用前端浮点重新决定优惠、运费或佣金。

公开商品价格只作为浏览参考，SKU 数量、会员资格与地址改变后请求统一报价；公开接口尚未给出完整会员报价时，不自行展示推算的“会员到手价”。订单显示历史快照，订单、履约、售后和资金状态按契约映射，不猜测业务枚举。

## 6. 商品富文本与图片

description 采用受限 HTML，与独立 detail_images 分开。实际 Admin 已输出 Tiptap HTML，后端当前按字符串保存；字段注释仍为纯文本，服务端净化与格式迁移尚无完成证据。后续接入必须先统一后端字段语义、内容策略、历史数据和根契约，不能把客户端渲染器当作输入安全保证。

目标标签允许 `p`、`br`、`strong`、`b`、`em`、`i`、`u`、`ul`、`ol`、`li`、`span`、`font`、`h1` 至 `h6`，覆盖现有编辑器的段落、强调、列表、颜色与可粘贴标题。只保留经验证的文字颜色属性，不允许任意 style、事件属性、脚本、iframe、表单、链接跳转或内嵌媒体；商品媒体继续由独立资产图集提供。边界策略在服务端执行，拒绝不支持的新内容并反馈，历史不合规内容采用显式迁移与复核，禁止按字符串猜测版本形成永久双轨。

mp-html 不开启脚本、链接导航、编辑、Markdown 或额外媒体插件。通过 usingComponents 声明微信原生组件并确保源码进入构建产物，原生组件边界内配置文字样式，不能假定 React 全局 CSS 能穿透。内容为普通文本的历史记录须在接入计划中按已审计来源转换并转义，不直接按 HTML 解释任意旧字符串。

详情图按后端有序 URL/width/height 显示，等宽、按比例占位、widthFix、下方懒加载、失败可重试和点击预览。可信 HTTPS 基址解析站内资源，绝对 URL 同样受域名准入约束。数量、字节和像素预算以[商品详情图集操作规范](../operations/product-detail-images.md)为准。

## 7. 样式、单位与包体

UI tokens 与业务组件必须遵循[小程序 UI 规范](miniapp-ui-standard.md)。业务 Sass 使用 750 设计宽度；NutUI 源样式按其 375 宽度独立换算，配置 designWidth 函数与 `deviceRatio[375] = 2`，防止控件尺寸减半或应用尺寸翻倍。原生 rpx 不二次换算，JS 动态尺寸使用对应设计宽度的 Taro.pxTransform 或明确 rpx。

主题用共享语义变量映射 NutUI 变量，不在业务页面直接写一组全局覆盖。CSS Modules 先验证 Taro 编译与第三方主题边界，无法适用时使用应用/Feature 命名作用域；不默认用浏览器选择器、hover 或 window/document。

主包保留四个 TabBar 页面。详情页位置和业务分包由真实入口与包体测量确定；禁止把分包全部导入全局 index 或 app.tsx。业务列表采用服务端分页、有界缓存和图片尺寸选择，不添加未授权的营销装修、搜索、优惠券或游客购物车。

## 8. 验证与交付

日常只运行适用 typecheck、lint、边界与契约漂移轻量检查。公开接口变化按 Backend 实现、导出根 OpenAPI、generate-api、消费者适配顺序完成。production build、Vitest、pytest、微信自动化、真机与数据库验证仅在当前任务明确点名后执行，不通过 CI、定时任务或上传脚本间接扩大。

工程首次验收应在授权范围核对精确依赖与冻结安装、微信构建产物、NutUI 控件/图标尺寸、mp-html 原生组件、Query 生命周期、主包与分包及 iOS/Android 关键旅程。性能预算和基础库下限由 E0 实测与上线环境定版，不能虚构已支持机型或包体证据。

上传、体验版、提审和生产发布各自留证并分别授权。小程序版本、AppID、环境、完整 Commit SHA、锁文件和契约摘要用于追溯；不能把上传成功记录为上线。收尾只清理本次可确认归属的缓存、产物和进程，不结束 Codex 或浏览器总会话。

## 9. 官方核验入口

- [Taro 编译配置](https://docs.taro.zone/docs/config-detail)
- [Taro 设计稿与单位转换](https://docs.taro.zone/docs/size)
- [Taro 原生组件混用](https://docs.taro.zone/docs/hybrid/)
- [Taro Webpack 5 runner 元数据](https://registry.npmjs.org/@tarojs/webpack5-runner/4.3.0)
- [NutUI React-Taro 固定版本元数据](https://registry.npmjs.org/@nutui/nutui-react-taro/3.0.20)
- [TanStack Query 固定版本元数据](https://registry.npmjs.org/@tanstack/react-query/5.101.4)
- [NutUI 3.0.20 官方 Taro 尺寸与编译配置](https://github.com/jdf2e/nutui-react/blob/v3.0.20/packages/nutui-taro-demo/config/index.js)
- [mp-html 原生组件与 usingComponents 用法](https://github.com/jin-yufeng/mp-html#使用方法)
- [微信小程序登录](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)

技术路线与初始化版本已定版，依赖解析、工程配置、真机和渠道验证未执行。平台或依赖声明变化时按官方证据更新本标准，不将文档存在视为实现通过。
