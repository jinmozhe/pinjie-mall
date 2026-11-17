# 小程序页面跳转记录与上线配置简明指南

适用于本项目 Taro React 微信小程序。开发时自动记录冷启动及后续页面路径；上线使用生产构建，路由记录会自动关闭，无需删除调试源码。

## 1. “放到 Taro 源码入口”的原理

微信开发者工具读取 `apps/miniapp/dist/` 中的编译产物。实际应修改 Taro 的 `src/app.tsx`，由 Taro 编译成微信可运行的代码；直接修改 dist 会被下一次编译覆盖。

当前执行顺序：`useLaunch → startRouteTrace → 记录启动入口并注册 wx.onAppRoute → 页面跳转时输出 Console`。useLaunch 位于应用入口，注册早于本项目的会话恢复，不用等启动后手动粘贴监听代码；切到后台不会停止监听。

| 文件（相对仓库根目录） | 职责 |
| --- | --- |
| [apps/miniapp/src/app.tsx](../../apps/miniapp/src/app.tsx) | 在 useLaunch 注册记录，在组件卸载时清理监听 |
| [apps/miniapp/src/platform/route-trace.ts](../../apps/miniapp/src/platform/route-trace.ts) | 记录序号、时间、跳转方式、前后路径及页面未找到标志；重复初始化先移除旧监听 |
| [apps/miniapp/config/index.ts](../../apps/miniapp/config/index.ts) | 根据 `mode === 'development'` 注入 `__ROUTE_TRACE_ENABLED__`，同时配置 API 与资源源站 |
| [apps/miniapp/src/types.d.ts](../../apps/miniapp/src/types.d.ts) | 声明编译常量的 TypeScript 类型，不负责开关取值 |
| [apps/miniapp/package.json](../../apps/miniapp/package.json) | dev:weapp 持续开发编译；build:weapp 生成生产产物 |

日志只进入 Console，不上传后台、不写本地存储、不保存历史数组，也不输出 query、授权 code、Token 或用户资料。开发时每次路由事件有少量格式化及 Console 开销；生产关闭注册和输出，具体性能与包体需以生产产物验收为准。

## 2. 在微信开发者工具查看

1. 在仓库根目录启动开发编译，等待编译成功：

   ```powershell
   Set-Location E:\fastapi\pinjie-mall
   $env:NODE_ENV = 'development'
   pnpm --filter @pinjie/miniapp dev:weapp
   ```

2. 微信开发者工具导入 `E:\fastapi\pinjie-mall\apps\miniapp`，项目配置的 miniprogramRoot 为 dist/。
3. 打开“调试器 → Console”，显示 Info 级别日志，搜索 `[路由轨迹]`；如果有上下文选项，选择小程序逻辑层 AppService。
4. 保持 Console 打开并重新编译，让启动过程重新执行，再操作登录、手机号授权、Tab 切换和返回。按“序号”查看先后顺序。

单条示例，路径和序号仅用于说明：

```text
[路由轨迹] {"序号":3,"时间":"14:20:30","跳转方式":"navigateTo","来源页面":"pages/cart/index","目标页面":"subpackages/account/auth/index","页面未找到":false}
```

| 字段或现象 | 怎么理解 |
| --- | --- |
| 页面未找到：false | 本条未标记页面不存在，属于正常记录；字段名每条都会显示 |
| 页面未找到：true | 路由事件标记目标不存在，核对目标路径和 src/app.config.ts 的 pages/subPackages 注册 |
| 来源页面 | 按上一条未标记为不存在的目标推导，并非实时读取完整页面栈 |
| 启动入口和首条路由路径相同 | 可能只是启动参数记录与首个路由事件各记一次，不代表重复跳转 |
| 没有日志 | 检查 Info/过滤条件、是否使用开发产物及启动是否报错；配置或环境变量改变后重启 watch，再重新编译 |
| 只看到启动入口和警告 | 当前环境缺少 onAppRoute/offAppRoute，需使用支持这些接口的基础库；官方从 3.5.5 开始支持，项目公开配置当前为 3.17.4 |

序号在监听重新初始化后重新计数；历史是否跨编译保留取决于开发者工具 Console 设置。日志展示已收到的路由事件，无法覆盖所有失败的导航调用，也不记录动画完成时刻。手机号绑定或登录是否成功，继续查看 Network 中接口响应。

## 3. 上线前哪些文件和配置需要处理

| 项目 | 上线前操作 |
| --- | --- |
| src/app.tsx、src/platform/route-trace.ts、src/types.d.ts | 保留，无需删除监听代码或手动改布尔值 |
| config/index.ts | 保留按编译 mode 控制的开关；不需要新建 dev.ts/prod.ts，当前项目没有这两个文件 |
| 构建终端的公开环境变量 | 设置正式 TARO_APP_API_BASE_URL 与 TARO_APP_ASSET_BASE_URL；必须为 HTTPS 源站，不带尾部斜线或 /api/v1 路径；资源与 API 同源时可使用同一地址 |
| package.json | 保留现有脚本，使用 build:weapp；上传前停止 dev:weapp，避免 watch 把生产 dist 覆盖回开发版本 |
| [project.config.json](../../apps/miniapp/project.config.json) | 核对 appid 属于发布主体，当前已登记 wx5e57afb47fd45568；保留 miniprogramRoot 为 dist/、urlCheck 为 true，以及 .map 打包排除配置 |
| project.private.config.json | 只保留本机，不入库；验收时关闭“不校验合法域名、TLS、HTTPS 证书”选项，不能依赖本地绕过设置通过验收 |
| 微信公众平台后台 | 配置正式 request、uploadFile、downloadFile 等实际用到的合法域名，核对 HTTPS 证书、隐私指引及手机号能力资格 |
| 服务端环境配置 | AppID 与小程序一致；AppSecret、JWT/HMAC 密钥只放服务端，按[身份接入手册](miniapp-identity-and-content.md#联调前置条件)核对登录开关、Redis、迁移和建号设置 |
| dist/ | 只使用本次成功生产构建的产物，禁止手改；微信工具点击“上传”不会自动将开发产物转换为生产产物 |

上线前操作示例，以下域名是占位值，执行前替换为自己的正式域名：

```powershell
# 先在 dev:weapp 所在终端按 Ctrl+C，停止 watch。
Set-Location E:\fastapi\pinjie-mall
$env:NODE_ENV = 'production'
$env:TARO_APP_API_BASE_URL = 'https://api.example.com'
$env:TARO_APP_ASSET_BASE_URL = 'https://assets.example.com'
pnpm --filter @pinjie/miniapp build:weapp
```

编译成功后，让微信开发者工具重新编译当前 dist。清空 Console 并冷启动、切页，确认不再新增 `[路由轨迹]`；同时检查请求使用正式域名，再进行真机、体验版和提审验收。修改环境变量后必须重新构建，仅在开发者工具点击编译无法替换已注入产物的源站与开关。

`project.config.json` 的 minified、minifyWXSS/minifyWXML、uploadWithSourceMap 等工具选项不控制路由记录，本功能无需修改这些值。路由日志关闭只证明该调试功能停用，不代表其他日志、包体、业务或上线验收已经完成。

本指南只说明操作步骤；本次文档整理未执行生产构建、上传、提审或发布。后续交由 Codex 执行时，按项目规则分别明确授权对应操作。

参考：[微信 onAppRoute 官方文档](https://developers.weixin.qq.com/miniprogram/dev/api/base/app/app-route/wx.onAppRoute.html)、[小程序工程标准](../architecture/miniapp-engineering-standard.md)、[本地开发手册](local-dev-environment.md#终端三小程序-watch-与微信开发者工具)。
