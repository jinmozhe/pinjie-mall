# 微信小程序目录与应用架构

| 项目 | 内容 |
| --- | --- |
| 适用应用 | `apps/miniapp`，建议包名 `@pinjie/miniapp` |
| 文档状态 | 待工程实施的架构设计；目录、模块和示例尚未创建 |
| 产品依据 | [微信小程序 PRD](../MINIAPP_PRD.md)与[产品需求基线](../PROJECT_REQUIREMENTS.md) |
| 通用边界 | [模块与依赖边界](module-boundaries.md)、[认证机制](authentication-authorization.md)、[错误模型](error-model.md) |
| 核对日期 | 2026-09-17 |

## 1. 文档职责与设计依据

PRD 定义用户需要什么、业务边界和验收结果；本文定义代码放在哪里、依赖方向、状态所有者及执行链路。目录与技术细节在本文维护，PRD 通过链接引用；正式框架定版及重大技术取舍在后续 ADR 记录，具体实施、验证与未决事项进入活动全栈计划。

本次只补齐设计，不初始化小程序，不改变 Admin、Backend、生成契约或工作流。应用名称统一为 `miniapp`，不使用另一套 `miniprogram` 应用命名。

前后端都需要数据所有权、职责边界与明确依赖。后端强调权威业务规则和事务，前端还需要处理异步请求、缓存、交互状态和平台生命周期。不能用“后端只管命令、前端只管状态”划分全部职责，也不能假定 API 或平台能力长期不变。

高内聚通过同一业务能力是否集中、依赖是否明确、改变后的验证是否可控判断。跨契约需求合理地影响多个层；文件数量少不代表设计正确。本文采用业务 Feature 内聚，避免把所有业务组件、接口和 Store 分散成三个全局目录。

## 2. 技术候选与既有约束

| 事项 | 本项目采用的设计边界 |
| --- | --- |
| 框架 | Taro 4.2.1、React 18.3.1 为候选；只构建 weapp，不创建 H5 目标；同一发布序列的核心 Taro 编译、运行与平台包保持同版本，独立版本插件单独核验 |
| 应用隔离 | Admin 保持现有 React 19、Umi Max、Ant Design；小程序独立 React 18 与类型依赖，应用内单一 React 实例；不全局 override React 主版本 |
| 编译 | TypeScript strict，复用兼容的共享基础约束，独立设置小程序 JSX、类型和路径；优先验证官方对应模板的 Webpack 5，TS 与 Sass 版本待实际验证后锁定 |
| UI | 使用 `@nutui/nutui-react-taro`，Sass、设计 tokens 与主题变量；CSS Modules 按兼容情况启用，不使用浏览器 DOM 组件 |
| 状态 | TanStack Query 5 管服务端数据；局部状态优先，Zustand 只按真实跨页需求引入；Zod 用于必要运行时边界，不手写全套 API Schema |
| 网络与契约 | Taro.request、Taro.uploadFile 与既有 OpenAPI 生成类型；不直接复用 Axios 请求运行时，不新增平行契约包 |
| 工程与发布 | 沿用根 pnpm、Node 基线、唯一锁文件、依赖观察期与构建脚本白名单；miniprogram-ci 为专项预览上传工具候选 |
| 测试 | Vitest 优先验证纯逻辑及传输边界；组件测试需验证运行环境兼容，微信开发者工具与真机提供平台证据 |

截至核对日，Taro React 适配包的 peer 为 React `^18`；NutUI 的 latest 为 `3.0.23-cpp`，无后缀版本 `3.0.20` 也存在。版本标签和后缀不能独立证明微信生产适配，不把 `3.0.23-cpp` 直接固定为本项目基线。`@tarojs/test-utils-react@0.1.1` 的多个 peer 指向 Taro 3.6，不列入 Taro 4 默认测试依赖；不为 SKU 纯函数新增 Jest。

`miniprogram-ci@2.1.31` 仅是已核对的发布候选，Node engine 下限满足不代表 Node 24 全链路验证通过。后续在实际依赖策略下完成解析、微信构建、关键组件和真机验证，再固定精确版本。未实现的兼容能力不得靠忽略 peer 冲突或降低仓库门禁取得通过。

## 3. 推荐目录

以下树是目标结构，按交付范围逐步创建有实际代码的文件。`stores/`、组件封装、测试目录与各 Feature 子目录按需要创建，不提前铺满空目录。每个 Feature 的目录数量由复杂度决定。

```text
apps/miniapp/
├── AGENTS.md                         应用规则，初始化时补齐
├── config/                           Taro 编译、环境与单位转换配置
├── project.config.json               可公开的微信开发者工具项目配置
├── package.json                      独立脚本与应用依赖，无子应用锁文件
├── tsconfig.json                     独立 React 类型与严格类型配置
├── src/
│   ├── app.tsx                       Provider 装配与应用生命周期
│   ├── app.config.ts                 页面、TabBar 与分包声明
│   ├── pages/                        主包页面入口与页面级组合
│   │   ├── home/index.tsx
│   │   ├── category/index.tsx
│   │   ├── product/detail/index.tsx
│   │   ├── cart/index.tsx
│   │   └── account/index.tsx
│   ├── subpackages/                  按功能划分的分包页面入口
│   │   ├── checkout/pages/confirm/index.tsx
│   │   ├── orders/pages/list/index.tsx
│   │   ├── orders/pages/detail/index.tsx
│   │   ├── aftersales/pages/apply/index.tsx
│   │   ├── account/pages/addresses/index.tsx
│   │   └── distribution/pages/overview/index.tsx
│   ├── features/
│   │   ├── catalog/
│   │   │   ├── index.ts              对外公开组件、Hook 与必要类型
│   │   │   ├── components/           ProductCard、SkuSelector 等业务 UI
│   │   │   ├── hooks/                useProductDetail、useSkuSelector
│   │   │   ├── domain/               sku-selection.ts 等纯交互规则
│   │   │   ├── api/                  catalog.service.ts，消费生成类型
│   │   │   ├── queries/              查询 key、选项与数据投影
│   │   │   └── types.ts              本 Feature 视图类型，不复制 API DTO
│   │   ├── cart/                     查询、加购、更新、删除及角标派生
│   │   ├── checkout/                 报价、草稿、幂等下单与支付编排
│   │   ├── orders/                   本人订单、履约及状态展示
│   │   ├── aftersales/               退款资格、申请和进度
│   │   ├── account/                  登录界面、资料、地址与账户操作
│   │   └── distribution/             会员、推荐、佣金、钱包与提现
│   ├── components/
│   │   ├── ui/                      有实际增益的通用展示组件
│   │   └── layout/                  安全区、页面框架、跨页布局
│   ├── lib/
│   │   ├── api/
│   │   │   ├── request.ts           鉴权请求入口与统一响应解包
│   │   │   ├── transport.ts         Taro.request 与 RequestTask 取消
│   │   │   ├── upload.ts            上传协议、字符串响应与取消适配
│   │   │   └── errors.ts            网络、HTTP、业务错误分类
│   │   ├── auth/
│   │   │   ├── session.ts           内存凭据、会话状态、恢复单飞
│   │   │   └── auth-api.ts          无递归恢复的认证端点封装
│   │   └── storage/                有版本与校验的非敏感持久化
│   ├── platform/                    微信能力适配，不包含服务端交易规则
│   │   ├── login.ts                 Taro.login 的 code 获取
│   │   ├── payment.ts               Taro.requestPayment
│   │   ├── network.ts               网络状态读取、监听与解除
│   │   ├── navigation.ts            受控导航与参数传递
│   │   ├── storage.ts               平台原始读写能力
│   │   ├── share.ts                 分享配置与平台交互
│   │   └── tabbar.ts                系统 TabBar 角标投影
│   ├── query/
│   │   ├── client.ts                QueryClient 与默认策略
│   │   └── lifecycle.ts             focusManager、onlineManager 适配
│   ├── stores/                      可选，只有真正跨 Feature 的客户端状态
│   └── styles/                      tokens、全局样式与 NutUI 主题
└── tests/                            按需放集成级测试；纯函数测试可就近放置
```

目录补充约束：

- 当前不存在上述实现，`dev:weapp`、构建、lint 与 typecheck 等脚本在初始化时配置，不能描述为已经可用。
- 商品与 SKU 选择先归 `catalog`；没有独立业务边界与复用证据时，不拆一个全局 `features/sku`。
- 商品卡片留在 `features/catalog/components/`，通过公开入口复用。业务组件不全部堆入 `components/biz`。
- 每个领域的端点封装与生成类型转换放在自身 `api/`，不集中堆入全局 `services/` 或单一 `endpoints.ts`。
- 单个 Feature 的可持久草稿优先就近放置；应用级 `stores/` 只容纳真实跨 Feature 的非敏感状态。暂时没有该需求时不安装 Zustand。
- 主包 TabBar 入口与分包页明确区分。商品详情是否留在主包由首屏路径和包体实测决定，目录树不代替微信构建配置。
- 项目私有配置、环境秘密、`node_modules` 与构建产物不进入源码目录；公开配置只包含可公开值。AppID 是环境标识，上传私钥是秘密，两者不能混为同一保密等级。

## 4. 依赖方向与层级职责

### 4.1 两条协作链

```text
页面 / 分包入口
  ├─ Feature 公开入口 -> 业务 UI + Hook
  │                        ├─ 纯 domain 规则 -> 本地交互状态
  │                        └─ Query / Mutation
  │                              -> Feature api/service
  │                              -> lib/api/request
  │                              -> lib/api/transport -> Taro.request
  └─ 页面生命周期与组合回调

应用装配 -> 认证状态、QueryClient、生命周期、TabBar 投影
Feature 用例 -> platform/payment、share、navigation 等必要能力
纯展示组件 <- props 与回调
```

HTTP Transport 直接适配 Taro.request，不必再增加一个仅转发参数的 platform/http。支付、登录、分享等平台能力独立协作，不是所有网络请求必经的一层。只在需要测试注入或真实多端实现时抽出相应端口。

### 4.2 职责表

| 位置 | 允许职责 | 禁止职责 |
| --- | --- | --- |
| pages、subpackages 页面 | 参数校验、路由、页面生命周期、页面级组合与反馈 | 直接拼接口、调用领域 service、处理 Token、复制定价或库存规则 |
| Feature 业务组件 | 自身业务展示与交互；容器组件可调用本 Feature Hook | 原始网络请求、绕开认证、访问其他 Feature 内部文件 |
| 通用纯展示组件 | props 展示、回调、NutUI/Taro 基础组件组合 | 内置购物车查询、会话与支付规则；建立全局业务依赖 |
| Feature Hook / Query | 查询、Mutation、局部状态组合与明确用例 | 把 API Schema、认证刷新、平台底层和所有业务逻辑塞进一个 Hook |
| Feature domain | SKU 可选组合、输入和展示推导等纯 TypeScript | React、Taro、NutUI、Query、Zustand、I/O；权威价格、库存和佣金计算 |
| Feature api/service | 使用生成操作与 DTO 类型，封装路径方法及必要映射 | 持有缓存、操作 UI、调用另一个 Feature 内部 API、隐式默认成功 |
| lib/api | 传输、认证接入、解包、错误、追踪与取消 | 全局业务 Store、业务重试循环、资金状态最终决策 |
| lib/auth | 凭据、单次恢复、会话失效与撤销语义 | 把 Token 暴露给页面或持久化到 Zustand、递归认证刷新 |
| platform | 封装必要微信能力与平台结果 | 将支付弹窗成功当作已收款、自行签名或保存 AppSecret |
| query、storage、stores | 分别管理缓存基础设施、持久化边界、少量客户端状态 | 三处各保存一份相同服务端数据 |

页面允许使用 `useLoad`、`useRouter`、`useDidShow`、`useDidHide` 等页面生命周期能力，UI 可以直接使用 `View`、`Text` 与 NutUI 组件。集中约束的是认证、支付、网络、存储等副作用，禁止所有 Taro API 会妨碍正常页面实现。

NutUI 包装仅在统一错误提示、安全区、可访问标签或业务交互等有真实收益时增加；主题优先通过 tokens 和主题变量统一。不能为了“统一 API”复制整套 UI 库。

### 4.3 Feature 公开入口与组合

跨 Feature 及页面导入只经过目标 Feature 的 `index.ts`，禁止穿透到 `hooks/`、`api/`、`domain/`、组件或 Store 内部。同一 Feature 内使用相对路径，避免通过自己的 index 回流形成循环。基础设施不反向导入 Feature；需要通知业务层时使用应用装配的回调或事件接口。

```typescript
// 页面级组合示意，文件和导出尚未实现
import { ProductDetailView, useProductDetail, useSkuSelector } from '@/features/catalog';
import { useAddToCart } from '@/features/cart';

// 禁止：从另一个 Feature 的内部路径导入
// import { useAddToCart } from '@/features/cart/hooks/useAddToCart';
```

catalog 向外输出商品展示和 SKU 选择能力，cart 输出加购能力，页面或明确的用例组合二者，避免 catalog 与 cart 双向依赖。Feature 内部组件优先接收 props 与操作回调；确有自身查询需求的容器组件可以使用本 Feature Hook，不强迫所有数据经过多层 props 转发。

公开入口使用明确导出，不通过 `export *` 聚合全部页面、样式和分包依赖。只导出消费者需要的能力与视图类型，禁止把所有实现暴露为“公共”来绕过边界。

## 5. 商品详情、选规格与加购完整链路

关联 PRD：`MP-CAT-002`、`MP-CAT-003`、`MP-CART-001`、`MP-CART-002`、`MP-AUTH-003`、`MP-UX-002`。

1. 商品卡片通过导航能力进入 `pages/product/detail/index.tsx`。页面解析并校验商品标识，调用 catalog 公开的 `useProductDetail`；非法参数不发起无意义请求。
2. Hook 使用包含商品标识的 Query key，调用 `catalog.service.ts`；service 消费生成类型并进入 `lib/api/request.ts`，最后由 Transport 调用 Taro.request。页面只收到解包后的业务数据和明确错误。
3. `useSkuSelector` 结合本地状态与 `catalog/domain/sku-selection.ts` 推导规格选项和当前 SKU。商品数据变化时重新核对选择，交互可选性不代替服务端最终可售校验。
4. 用户点击加购，页面组合 cart 公开的 `useAddToCart`。需要登录时先建立身份，返回后由用户确认继续；不在登录成功事件中自动提交加购。
5. Mutation 调用 `cart.service.ts`，再经统一请求层提交 SKU 和数量；认证模块提供凭据。服务端校验用户、商品与库存，返回权威条目。
6. 写成功后更新已知条目的 Query 缓存或定向失效本人购物车查询。当前响应只有一个条目，不包含整个购物车总数量，不能直接拿返回 quantity 当作全局角标。
7. 角标 Hook 从同一个本人购物车 Query 派生展示值，应用壳把值投影到系统 TabBar；采用自定义 TabBar 时也读取该公开 Hook。两种 UI 实现均不维护另一份 Zustand badgeCount。
8. 写已成功但刷新购物车失败时，反馈“已加入，购物车刷新失败”并提供查询重试；不能把查询失败反馈为加购失败并诱导再加一次。

```text
商品详情页
  -> catalog/useProductDetail -> catalog api -> request -> transport
  -> catalog/useSkuSelector   -> 纯规格推导 + 局部状态
  -> cart/useAddToCart        -> cart api -> request -> transport
                                  |
                                  v
                         本人购物车 Query 缓存
                                  |
                                  v
                        角标派生 -> TabBar 投影
```

### 加购超时与认证重放

当前 `POST /api/v1/cart-items` 输入没有幂等 request_id，同一 SKU 再次加入会累加数量。超时、断网或响应丢失时不能无条件重发；先查询购物车并说明结果无法精确确认时需要用户检查。要支持可自动恢复的精确加购，须在后续全栈计划扩展契约和服务端幂等，前端自行生成字段无效。

认证层只在明确的会话错误且端点契约保证业务尚未执行时，允许一次恢复和受控重放；不能把任意 401、网络失败或未知结果都当作可重试。切换账号或撤销会话后，旧 Mutation 不得在新身份下重新执行。

## 6. 状态、缓存与副作用归属

| 状态 | 位置 | 更新方式 |
| --- | --- | --- |
| 商品、购物车、地址、订单、支付与资金记录 | TanStack Query | 服务端返回值、精确缓存更新或定向失效 |
| 购物车角标 | 从购物车 Query 派生 | 根据产品定义的口径计算；不加一、不保存独立业务副本 |
| SKU 选择、当前弹层、未提交表单 | React 局部状态 | 用户操作及输入数据变化后校验 |
| 跨页结算意图、筛选偏好 | Feature 内草稿或按需 Zustand | 只保留非敏感客户端意图，不保存可直接成交的旧报价 |
| 当前路由和 TabBar 选中项 | Taro 路由状态 | 由实际页面同步，不另建可独立漂移的路由 Store |
| 凭据与恢复任务 | lib/auth | 私有内存状态、明确轮换与撤销；页面只接收安全会话摘要 |
| 本地非敏感偏好 | lib/storage -> platform/storage | 版本校验、损坏提示或明确重置，不默默恢复为成功状态 |

角标采用总件数或条目数必须有统一产品口径；显示格式可设置上限，但格式化不能改变底层数据。具体口径在涉及角标的实施计划确定；首次查询失败不伪装成空购物车，已有值过期时不得宣称已同步。失效查询不保证未订阅的缓存立即重新获取，应用壳需要角标时订阅相同 Query，返回购物车页再按新鲜度规则刷新。

私有 Query key 包含用户或会话隔离范围。应用装配在退出、停用或合法账号切换时取消请求、清理私有缓存并递增会话代次；请求和 Mutation 回调核对代次，防止取消未及时生效时旧响应回填。取消本地请求不等于撤销服务端已经执行的写操作。

`query/lifecycle.ts` 把前后台事件接到 focusManager，把初始网络状态及变化接到 onlineManager，订阅只注册一次并解除。页面重新显示与应用回前台分别处理，支付返回、地址保存等只刷新受影响查询。订单轮询设置上限并在隐藏时停止，资金写操作不保存为恢复联网后自动执行的队列。

游客购物车与合并暂不属于 PRD 首版范围，不因出现 Zustand 或 Storage 就增加该能力。

## 7. 请求、认证与支付协作

### 7.1 避免基础设施循环

```text
Feature api -> request -> auth/session（取得凭据、单飞恢复）
                      -> transport（发送当前业务请求）
auth/session -> auth-api -> transport（认证请求，无自动恢复）
             -> platform/login（取得微信 code）
```

底层 Transport 不依赖 session、request、Feature 或 UI。`auth-api` 不调用带自动恢复的 request，避免 `request -> refresh -> request` 递归。登录失效通知由应用装配接收并清理缓存，不让 auth 反向依赖具体订单或购物车 Feature。

微信 code 在后端换取可信身份；AppSecret 和 session_key 不进入客户端。后端只在确有用途时按受控策略保存 session_key，不把永久保存它作为登录的无条件要求。小程序会话的 audience、密钥策略、建号和现有账户迁移在认证专项中统一设计，不改变 Admin Cookie、Origin 与 CSRF 机制。

### 7.2 Transport 与重试

- Transport 统一 BaseURL、超时、HTTP 状态、业务响应解包、请求追踪及 Retry-After；Taro success 回调不直接表示 HTTP 或业务成功。
- Query 负责适用 GET 的有限重试，request 不再叠加网络重试；业务拒绝、认证失败和取消不进入通用重试循环。
- 认证模块负责一次并发恢复，刷新接口不自刷新；429、503 与网络失败保留故障状态，不直接清除会话。
- 上层取消连接到真实 RequestTask.abort，并解除监听；上传使用 uploadFile 的取消与字符串响应语义，不能直接复用 JSON 请求假设。
- 下单、支付、退款、提现各自管理独立业务请求号；同一动作的恢复复用原号与原内容。订单创建请求号与支付意图请求号不混为一个全局幂等号，也不与追踪 ID 混用。
- service 可把生成 DTO 转成 UI 视图，但不能手写平行 API Schema。类型断言和 `any` 不能替代契约适配与输入验证。

### 7.3 支付平台适配的边界

checkout 用例先调用后端创建支付意图，获取签名参数，再调用 platform/payment；平台返回后通过 orders 的公开查询能力确认后端结果。平台适配器只表达调用完成、用户取消和平台失败，不直接更新已付款缓存。

切换支付渠道通常同时影响后端下单、商户配置、身份字段、签名、回调、退款、对账、公开契约、页面可用性与验收，不能承诺只新增一个 alipay.ts。微信小程序首版仍只开放经验证的微信支付，不因适配层存在而增加其他渠道。

## 8. 分包、样式与可维护性

app.tsx 只装配必要 Provider、生命周期及应用级投影，不导入全部业务页面。分包按页面入口和实际依赖图组织，不能仅移动文件后认定依赖已经离开主包。重点检查共享 Feature 的 index、全局样式、NutUI 全量引入及主包对分包能力的依赖，不能只依赖 tree-shaking 宣称包体正确。

设计 tokens 集中维护，局部样式与业务组件就近组织；明确设计稿宽度、Taro 单位转换和原生 rpx 的使用，防止重复转换。业务组件归 Feature，通用布局归 components，独立平台适配不承载 NutUI 或组件主题。

| 变化 | 正常影响范围 | 评审重点 |
| --- | --- | --- |
| 商品卡片样式 | catalog/components，必要时 styles tokens | 不应修改请求或领域计价 |
| SKU 选择交互 | catalog/domain、Hook，必要时组件及测试 | 规则与 UI 契约可能一起变化，不能机械要求只改纯函数 |
| API 服务域名 | 环境配置与 request 入口 | 发布环境与域名准入同步，不影响领域规则 |
| 加购接口字段 | Backend、OpenAPI、生成类型、cart api、受影响 Hook/UI | 按真实契约影响适配，不承诺只改 service |
| 会话轮换规则 | Backend Profile、auth、request、会话隔离及安全测试 | 不是单个拦截器可以独立决定的逻辑 |
| 角标显示口径 | cart 派生选择器与 TabBar 展示 | 不新增持久业务副本，不在加购回调手工维护计数 |
| 支付渠道 | 全栈资金与平台链路 | 需独立计划、资金恢复及真实渠道验收 |

Hook 按明确用例拆分，如 `useCheckoutPreview`、`useCreateOrder`、`useCheckoutDraft`，避免一个 Hook 承担全部流程；也不为每个 useState 强制创建文件。结算草稿只包含当前支持的地址、SKU 和数量等意图，不加入尚未实现的优惠券选择。

## 9. 测试、治理与实施顺序

### 9.1 验证层次

| 对象 | 方法 | 证据边界 |
| --- | --- | --- |
| 纯 domain、数据转换、角标派生 | Vitest node 环境 | 可验证边界与确定性，不证明微信 UI |
| Transport 与认证恢复 | 注入平台请求、时钟和凭据边界，验证并发、取消、错误与重放 | 不 Mock 被测内部方法伪造结果 |
| Query 与 Hook | 验证缓存失效、隔离与用户结果，运行环境先完成兼容核验 | jsdom 不自动支持 Taro 运行时，MSW 不能默认拦截 Taro 原生请求 |
| 组件与页面 | 按兼容情况选测试环境；必要时评估 miniprogram-simulate | 模拟微信组件需适配生成产物，不等于直接渲染 React TSX 或完整应用 |
| 平台流程 | 微信开发者工具及 iOS、Android 真机 | 登录、支付、前后台、分包、弱网和原生组件实证 |
| 发布产物 | 经授权的 miniprogram-ci 及实际包体报告 | 工具质量报告不能替代运行、真实资金与性能验收 |

`checkCodeQuality` 等工具入口须按实施时官方能力和实际报告接入，本文不把它描述为已经验证的压缩、无用代码清除或完整质量门禁。Jest、Taro Test Utils 与另一套组件测试体系只有在确有必要且验证兼容后再评估，不列为默认安装项。

### 9.2 门禁与命令

当前状态检查及 TypeScript 边界扫描主要覆盖 Backend、Admin 和历史 Web，尚未登记 miniapp。后续初始化必须补齐应用 empty/ready/partial 状态、公开入口与循环依赖、跨应用引用、变更路由和正反例；当前边界检查通过不能证明本文拟议结构已受检查。

日常拟提供 `pnpm --filter @pinjie/miniapp typecheck`、`lint` 与独立 `dev:weapp`。脚本尚未配置；根 pnpm dev 保持 Admin 行为，微信构建监听输出由开发者工具加载，不运行 H5 服务或 3000 端口。

Push、PR 只接入适用轻量门禁和生成漂移检查。Taro production build、Vitest、平台自动化、真实数据库与渠道验证按当前任务明确授权执行；预览、上传与发布分别授权并留证，不能借工作流调用链自动触发。AppID 等公开环境标识可进入受控配置，上传私钥等秘密仅进入受保护 CI 环境，上传网络出口按平台要求核对。

### 9.3 落地顺序

1. 读取 PRD、本文与适用规则，在单一全栈计划关联需求，明确身份与渠道的关键前置条件。
2. 先验证最小工程、依赖、关键商品组件、Query 与包体；此步骤可使用明确标识的样例，不当作业务验收。
3. 实现微信身份、会话模型和消费者接口扩展，导出根 OpenAPI，再生成既有 API Client 类型并适配请求层。
4. 按 PRD 顺序建设浏览、购物车、结算、订单及必要 Admin 运营能力，保持业务 Feature 内聚。
5. 完成真实支付、退款、异常恢复、任务运行及既有分销资金联动，再按实际开放范围完成会员与提现体验。
6. 在授权范围内验证架构门禁、微信环境、真机及发布产物，记录实际通过、失败和未执行项。

## 10. 官方核验入口

- [Taro React 生命周期 Hooks](https://docs.taro.zone/docs/hooks/)
- [Taro 4.2.1 发布记录](https://github.com/NervJS/taro/releases/tag/v4.2.1)
- [Taro React 适配包元数据](https://registry.npmjs.org/@tarojs/react/4.2.1)
- [NutUI React-Taro 发布元数据](https://registry.npmjs.org/@nutui/nutui-react-taro)
- [Taro Test Utils 发布元数据](https://registry.npmjs.org/@tarojs/test-utils-react/0.1.1)
- [TanStack Query 非浏览器生命周期适配](https://tanstack.com/query/latest/docs/framework/react/react-native)
- [微信小程序登录流程](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)
- [miniprogram-ci 发布包说明](https://www.npmjs.com/package/miniprogram-ci)

版本元数据只能证明发布及声明的兼容范围。本文不以包存在、官方文档示例或架构图作为本项目安装、构建、真机、渠道或上线验证证据。
