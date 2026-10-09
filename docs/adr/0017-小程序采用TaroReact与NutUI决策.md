# ADR 0017：小程序采用 Taro React 与 NutUI

- 状态：已定版，工程与公开浏览已实施，平台与交易验收未完成
- 日期：2026-10-09
- 授权依据：用户要求确定小程序技术栈并补齐工程标准与 UI 规范
- 当前标准：[小程序工程标准](../architecture/miniapp-engineering-standard.md)
- 配套设计：[小程序架构](../architecture/miniapp-architecture.md)、[小程序 UI 规范](../architecture/miniapp-ui-standard.md)

## 背景

商城的唯一消费者端为微信小程序，Backend 与 Admin 已有独立实现。团队已有 React、TypeScript、pnpm 和生成契约基础，需要复用工程经验，同时避免把浏览器 DOM、Admin React 运行时和 Cookie 会话带入微信环境。

既有架构列出了 Taro、NutUI 与 Query 候选组合，但没有定版，也没有可执行的应用标准。本决策确定技术方向和初始化基线，不代表应用已安装、构建、验收或上线。

## 决策

1. 小程序采用 Taro 4、React 18 与 TypeScript，目录为 `apps/miniapp`，包名为 `@pinjie/miniapp`。只编译 `weapp`，不提供 H5、Next.js、其他平台或 Node 服务。
2. 采用 Taro 官方 Webpack 5 编译链和 Sass，首期不并行维护 Vite 或 Skyline。Taro 同一发布序列的 CLI、运行时、组件、React 插件、微信插件与编译包使用相同精确版本。
3. UI 采用 `@nutui/nutui-react-taro` 和微信原生基础组件。应用业务主题由独立设计 tokens 控制；图标使用 NutUI Taro 图标，不引入依赖 DOM 的 shadcn/ui、Radix、Ant Design 或 lucide-react 运行时。
4. 服务端状态采用 TanStack Query 5；交互状态优先 React 局部状态。Zustand 和 Zod 仅在实际需求成立时引入，不作为初始化必装依赖。
5. 网络采用 Taro.request 和 Taro.uploadFile。通过 `import type` 消费既有 `@pinjie/api-client` 公共入口，不执行其 Axios SDK，不创建第二套 OpenAPI 或 DTO。
6. 商品说明遵循现有 Admin 富文本能力，采用受限 HTML 与 `mp-html` 微信原生组件；详情图集继续独立维护。内容净化、标签策略、字段说明和历史内容格式必须在后续全栈接入中对齐。
7. 微信登录、支付、分享、存储与网络生命周期集中适配。小程序使用独立 Public Client Bearer Profile；Admin Cookie、Origin、CSRF 与 React 19 保持独立。
8. 沿用根 pnpm workspace、唯一锁文件、Node 基线、依赖七天观察期、安装脚本白名单和 Fail Closed 门禁。预览工具采用 miniprogram-ci，上传、提审和发布继续分别授权。

精确版本、配置和脚本要求由工程标准维护。2026-10-09 官方 npm 元数据确认 Taro 4.3.0 React 插件 peer 为 React `^18`，NutUI 3.0.20 接受 React 18，Query 5 接受 React 18/19。Taro 4.3.0 于 2026-09-29 发布，符合本仓库七天观察期。

## 取舍

| 方案 | 评估 | 结论 |
| --- | --- | --- |
| Taro React + NutUI | 复用 React/TS 经验，提供小程序适配组件；需验证编译、原生行为和包体 | 采用 |
| 微信原生 WXML/WXSS | 平台直接控制能力强，但业务页面需要另一套开发范式 | 仅在已证实的平台缺口中局部接入原生组件 |
| uni-app Vue | 可覆盖多端，但本项目只交付微信，团队已有 React 能力 | 不建立第二套框架体系 |
| 浏览器组件库直接复用 | 依赖 DOM，与微信渲染、事件和生命周期不同 | 不采用 |
| React 19 全仓统一 | Taro 当前 React peer 不覆盖 React 19 | 不强制统一，各应用独立解析 |

## 影响与验证边界

- 后续初始化需登记小程序状态、TypeScript 边界、变更路由和轻量脚本；现有门禁通过不代表小程序已被覆盖。
- NutUI 传递依赖包含浏览器相关包、统计工具和预发行图标范围，需在实际解析时核对安装行为、按需产物和包体，禁止无范围放行安装脚本或忽略 peer 冲突。
- Webpack runner 当前声明精确 webpack peer；依赖安全与可解析性仍需真实安装及线上 Security 证据，不能仅凭 engines 下限判断 Node 24 全链路通过。
- 本次未安装小程序依赖，未执行小程序构建、应用测试、真机、渠道或上传验证。

## 升级与回滚

后续升级先核对官方兼容声明与仓库依赖策略，在同一工程计划更新标准、应用 package.json 和根锁文件，执行已授权验证。兼容失败时停止推进，记录实际失败，禁止自动切换编译器、框架或降低门禁。

工程回滚使用上一份已验证的应用与锁文件快照，契约变化遵循受控迁移；推翻本决策时新增 ADR。本次仅交付文档，不产生需要回滚的运行服务或数据库变化。

## 官方依据

- [Taro 4.3.0 发布记录](https://github.com/NervJS/taro/releases/tag/v4.3.0)
- [Taro React 4.3.0 元数据](https://registry.npmjs.org/@tarojs/react/4.3.0)
- [NutUI React-Taro 3.0.20 元数据](https://registry.npmjs.org/@nutui/nutui-react-taro/3.0.20)
- [TanStack Query 非浏览器生命周期适配](https://tanstack.com/query/latest/docs/framework/react/react-native)
- [微信小程序登录流程](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)
