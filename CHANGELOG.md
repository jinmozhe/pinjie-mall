# Changelog

本文件记录已经交付的项目能力和版本变化。格式参考 Keep a Changelog，版本发布前的变化记录在 `Unreleased`。

## Unreleased

### Added

- 完成阶段 F 会员资格贡献本地实现：订单首次成交在同一事务内按订单商品金额写入可冲销的消费资格事实，整单退款完成时按原贡献等额冲销并关联原事件，缺少历史原事实时不补造。资格写入复用已有会员重算和等级历史；有效邀请触发条件没有权威定义，未将首次绑定或任意成交擅自作为邀请贡献。后端与治理轻量门禁通过，pytest 和 PostgreSQL 动态验证未执行。

- 完成阶段 E 财务完整性与对账处置本地实现：新增订单支付、订单 SKU、提现钱包归属及渠道流水范围约束的前向迁移源码；审计事件增加主体类型、目标版本、提现状态目标约束和成功版本唯一性。用户提现创建、管理员审核、驳回、线下完成均同事务审计，重放事件不占用状态版本。新增 `reconciliation:resolve` 权限、版本化人工处置接口与 Admin 操作，处置保留差异状态和资金事实。根 OpenAPI、API Client 与 Admin 已同步，后端、Admin 与治理轻量门禁通过；pytest、实际迁移和 PostgreSQL 动态验证未执行。

- 完成阶段 D 资金恢复本地实现：可信支付和退款通知先保存资金成功事实、状态事件及耐久补偿任务，订单成交、库存限购流转、履约、佣金追回等后续动作改由独立短事务幂等完成。正常订单只接受一笔成交，重复支付、取消后迟到和到期临界收款保留原支付事实并创建异常退款；取消与到期扫描会保留成功或未决支付的预占并安排恢复或查询。后端轻量门禁通过；pytest、实际迁移和 PostgreSQL 动态验证未执行。

- 完成阶段 C 佣金与报价冻结本地实现：统一报价和订单保存命中批发阶梯、会员价格规则、买家等级及原运费规则，报价指纹覆盖完整规则决策；下单冻结佣金政策、来源预算和分配矩阵，支付只读取全局开关与受益资格。一级有效受益人缺矩阵时可使用来源预算兜底，显式零和停用、软删除资格均不发佣且不补位；交付后按冻结政策等待期排程，结算时复核订单、履约和未结束退款。根 OpenAPI、API Client 已同步，后端轻量门禁和 Admin typecheck/lint 通过；pytest、实际迁移和 PostgreSQL 动态验证未执行。

- 阶段 B 完成接单与履约售后互斥的本地实现：新增管理员接单契约、`orders:accept` 权限、审计命令与订单事件，发货、虚拟交付、用户确认收货和自动确认按订单、履约、退款固定顺序加锁，未结束退款阻断履约；新增 `20260923_01` 前向迁移允许管理员订单事件。后端轻量门禁、根 OpenAPI 导出、API Client 生成和 Admin 静态检查通过；pytest、实际迁移和 PostgreSQL 动态验证未执行。

- 完成后端目标模型开发库迁移与动态验证：本机开发库和隔离 PostgreSQL 测试库均已升级至 `20260922_07`，完成空库、重复升级、恢复演练、`alembic check`、67 张业务表及 23 张目标新增运行表核对。旧交易测试已适配当前模型，完整 Backend pytest 通过 398 项并达到 90.00% 行与分支覆盖率门禁；真实外部渠道、小程序会话、常驻 Worker 与积分消费政策仍未实施。

- 完成会员资格与积分后端专项：新增 `member_level_conditions`、`membership_qualification_events`、`member_level_events`、`points_accounts` 和 `points_ledgers`，并以 `20260922_06` 前向迁移接入。资格事件按来源幂等、可冲销且受原贡献上限保护，自动评估最高达标活跃等级并与会员档案版本和历史快照同事务保存。积分账户和不可变账本支持经权限、CSRF、审计与幂等键保护的人工授予和冲销，积分变动同步资格贡献。根 OpenAPI 与 API Client 已生成；实际数据库升级、pytest、测试迁移和 PostgreSQL 并发验证未执行，积分兑换、到期和抵扣政策未启用。

- 完成阶段 6 后端目标模型总核对与任务恢复：新增 `scripts.verify_target_model` 静态核对当前 62 张 ORM 表及 18 张目标新增运行表，确认 Alembic 唯一 head 为 `20260922_05`。新增显式单轮 `scripts.run_durable_tasks` Worker，使用短事务租约与数据库时钟完成或重试任务；内部执行订单到期、发货后自动确认和佣金结算，未接入的支付、退款和提现渠道任务保留重试或 attention，不伪造资金成功。实际数据库升级、pytest、测试迁移、PostgreSQL 并发和幂等验证、Worker 实际执行、真实渠道、常驻调度及告警未执行。

- 完成阶段 5 售后退款与资金结算后端：新增 `refund_attempts`，将退款申请改为未发货或未交付订单的整单申请，完整覆盖原订单明细与原运费。未接单订单自动审核，正额退款保存独立执行意图和任务，可信确认后同一事务回补原 SKU、标记限购 refunded、撤销或追回佣金并取消履约；归档 SKU 的回补立即清退可用库存。佣金交付满七日结算写入钱包版本账链，退款追回可扣减钱包或建立欠款；对账记录支持收款、退款和提现三类匹配。真实支付和提现渠道、任务 Worker、实际数据库升级、权限同步、pytest、测试迁移和 PostgreSQL 并发验证未执行。

- 完成阶段 4 交易订单与支付履约后端：新增用户商品累计限购账户和订单限购事实表，并以前向 Alembic revision 扩展订单、支付、履约和库存模型。购物车、结算预览、原子下单、订单读取和取消已恢复；下单重算统一报价并同事务写入订单快照、库存和限购预占以及到期任务。零元内部确认和可信支付确认会确认预占、创建履约并冻结三级预算佣金；未接入的支付渠道明确保存 unavailable。根 OpenAPI 与 API Client 已生成；实际数据库升级、权限同步、pytest、测试迁移、PostgreSQL 并发验证、真实渠道和 Worker 联调未执行。

- 完成阶段 3 分佣政策与持久任务后端基础：新增可发布的佣金政策、商品/SKU 来源规则、三级分配矩阵和 `commission_control` 总开关，政策草稿使用精确权限、CSRF、revision 和审计管理，发布后冻结并归档此前生效政策。新增 `durable_tasks` 的事务内入队、租约领取、失败关注和恢复基础；佣金、钱包和提现模型升级为行级三级权益、版本账链、余额快照与渠道事实字段。旧固定两级发佣统一返回 `503 / COMMERCE_UPGRADE_REQUIRED`，未接入提现渠道返回 `503 / WITHDRAWAL_CHANNEL_UNAVAILABLE`。根 OpenAPI 与 API Client 已生成，Admin 会员列表已改用 `level_id` 契约；实际数据库升级、权限同步、pytest、测试迁移和并发动态验证未执行。

- 完成阶段 2 会员价格与平台运费后端基础：新增会员等级、统一会员价格规则和可信外部身份映射表，并将会员档案改为可空等级外键、等级变更时间和版本；新增平台 `order_shipping` 配置、管理端权限与审计接口，以及按会员一口价、批发阶梯、最近分类规则、默认折扣和省级运费生成指纹的只读报价接口。外部身份 Provider 在渠道未接入时返回 `503 / EXTERNAL_IDENTITY_UNAVAILABLE`，购物车、结算和订单继续返回 `503 / COMMERCE_UPGRADE_REQUIRED`。根 OpenAPI 与 API Client 已生成；实际数据库升级、权限同步、pytest、测试迁移和并发动态验证未执行。

- 完成后端目标模型商品首期：新增品牌、公共属性、标准值、分类直接模板、商品属性采用、商品候选值、SKU 规格组合和描述值共 8 张表，并以前向 Alembic revision 改造商品、SKU 与库存流水。商品支持公共与自建属性、版本冻结、服务端组合键、批发阶梯、可选重量、品牌、限购配置、规格归档及库存清退；管理与公开 SKU 契约隔离成本价。旧运费模板报价、购物车与订单入口返回 `503 / COMMERCE_UPGRADE_REQUIRED`，等待统一价格、运费和订单快照阶段恢复。根 OpenAPI 与 API Client 已生成，Admin 旧商品页已切换为迁移中状态；pytest、测试数据库迁移和并发动态验证未执行。

- 整合全域目标数据库字典与 v3.0 参考稿，纠正原“50 表”统计为原稿 66 表；补齐小程序身份后登记 67 表、全局配置、字段约束、状态机、事务恢复、验收及现行 44 表迁移差异。同步 PRD 与小程序需求为统一运费、零元成交、未发货/未交付整单含原运费退款及三级预算分佣，按一级到三级截断且来源禁用全停发；仅交付设计文档，源码、迁移和真实业务验收尚未执行。

- 将 Backend 固定运行端口从 `8000` 迁移到 `18168`：同步 Backend 启动与健康检查、Admin 开发代理和 Nginx、生产 Compose、候选镜像、E2E 默认地址及运维文档；未修改 API 契约、数据库和权限数据。

- 交付 Admin 电商 A0 至 A4 本地实现：商品分类、运费、商品/SKU、图片与库存，订单履约、退款审核、支付与对账，会员推荐、佣金、双轨钱包流水及提现审核。补齐服务端筛选、原子批量状态操作和精确权限保护的选中导出，同步 OpenAPI 与生成客户端。隔离测试库及本地运行库完成字段注释迁移，本地权限目录已同步；Backend 全量 pytest 353 项通过，综合覆盖率 90.60%。Admin typecheck、lint 通过，production build、Vitest 和浏览器自动化未执行；真实资金渠道未接入。

- 完成全仓文档事实一致性审计：同步根 README 与 Backend README 的 M1 至 M4 本地实现状态、Admin 运营页面缺口、`apps/miniapp` 目标目录及小程序 PRD/架构入口；保留历史计划和当前未实现渠道、迁移与小程序工程的准确边界。

- 补充小程序目录与应用架构文档，明确 Feature 公开入口、商品详情到加购链路、Query 角标派生、认证与请求恢复边界，并由 PRD 和架构索引统一引用；目录与依赖保持待实施状态，未创建应用工程。

- 新增微信小程序 PRD 初版，细化首个可交易版本、会员分销体验、账户与交易异常、消费者接口缺口、Admin 运营依赖及验收矩阵，并关联产品基线和文档索引；仅交付需求文档，未初始化小程序、执行迁移、联调渠道或发布。

- 落地商城后端 M4：会员档案与首次两级推荐、可信付款冻结的佣金规则快照、交付满七日结算、按可信退款比例撤销或追回佣金、佣金与消费双轨钱包、幂等提现申请及审核解冻；同步六张表的迁移、权限、OpenAPI 和生成客户端。真实支付/退款/提现渠道、实际迁移、权限同步和 pytest 未执行。

- 落地商城后端 M3：支付意图与不可变状态事件、实物和虚拟履约状态机、按已交付订单明细申请的退款与审核事件、公开评价和渠道账单对账差异记录；实物发货满七日通过受精确数据库确认保护、默认 dry-run 的命令自动确认。微信和支付宝未配置时明确记录支付不可用，真实渠道支付、退款、验签和回调未实现。

- 落地商城后端 M2：用户购物车、服务端结算预览、报价指纹、幂等待付款订单、订单与运费快照、库存占用、取消及 30 分钟超时释放；订单创建锁定运费模板和库存，达到订单到期点的内部支付确认明确拒绝。新增受精确数据库确认保护、默认 dry-run 的订单超时处理命令。支付确认仅为后续支付领域的内部入口，真实迁移、动态交易测试和渠道支付未执行。

- 落地商城后端 M1：三级分类、商品与稳定 SKU、图片引用保护、独立库存与幂等调整流水、本人收货地址、运费模板与 Decimal 试算；同步八张表的迁移文件、精确管理权限、审计、OpenAPI 和生成客户端，建立统一需求与四阶段计划。数据库迁移、权限同步、pytest 和真实并发验证未执行，交易、支付及分销仍为后续阶段。

- 完成独立商城基线校正：项目身份、PRD、Backend 默认名称与 OpenAPI 契约统一为 `pinjie-mall`；CNB、TCR、GitHub Actions、Compose、发布与运维文档收敛为 Backend 和 Admin 两端。微信小程序确立为唯一 C 端的后续实现方向，`apps/web` 历史源码冻结保留，启动、构建、测试、镜像、发布、部署和 E2E 入口均已阻断或移除。远端商城资源、重型测试与生产部署未执行。

- 手动 `CI - Full Validation` 增加默认 full、可选 smoke：smoke 跳过 Admin/Web Vitest 和 coverage，保留 Backend pytest、生产构建、四项目入口页面基线和桌面 Stage C；full v2 与 smoke v1 证据隔离，模式及 strict 拒绝 smoke 的 Guard 接入本地与 CI。Handoff 保持 strict/fast，fast 不主动核验 smoke；Admin 并发和候选镜像工作流保持原配置，真实 full/smoke 与发布部署未执行。
- 回馈派生项目的发布可靠性修复：停用当前 CNB/TCR 个人版远程构建缓存读写，补齐候选证据校验错误提示；新增固定母版仓库的手动只读 CNB 诊断及离线回归门禁。Backend runtime 增加系统包升级，保留固定基础镜像与正式发布扫描要求；真实母版镜像扫描与生产部署未执行。
- 统一 GitHub、CNB、TCR、1Panel 凭据归属、可选本机镜像核验、派生项目权限范围、独立发布与逐阶段排障规范，纠正仍要求写入远程缓存的旧说明。

- 补充 Admin 空表自适应规则：按实际行数据切换横向宽度策略，空表解除多余固定宽度，有数据时保留宽表滚动，覆盖筛选无结果、回收站和空与非空切换；本次仅更新规范，未批量修改页面或执行视觉验收。
- 增加受控 OpenAPI 破坏性变更登记和 CI 门禁：按方法、完整路径与错误描述生成临时忽略清单，校验关联计划、批准日期、消费者迁移和回滚记录及最长 30 天期限；初始零例外，继续保留 `fail-on: ERR` 和契约生成漂移检查，未登记的破坏性变化保持阻断。
- 完善 Admin 五类通用工程规则：统一容器与间距、列宽分配、紧凑筛选及移动端布局、查询一致性和受控状态开关。同步规则入口与文档索引，保留母版既有工具栏、删除确认及状态 Tag 实现；本次为文档更新，不包含组件迁移。

- 增加 Admin `ProTable` 列表开发规则：工具栏左侧通过 `headerTitle` 显示“XX列表”，右侧统一提供刷新、密度、列设置和全屏；搜索、筛选与重置按需实现，预计数据较多且需求不明确时开发前向用户确认。本次仅更新规则与接入说明，未批量改造现有页面。
- 增加手动生产镜像组合验收、可信交接证据、固定 digest 部署清单、1Panel 变量预检与只读 TCR 保留计划；Full Validation 改为并行三端检查后验证 Admin Nginx dist 与 Web standalone，成功证据升级 v2，并保留脱敏诊断；CNB main 交接串行，Docker 依赖层缩小输入，Trivy 改为一次完整扫描后转换和结构化门禁。本次完成本地实现，真实云构建、镜像 E2E 与生产部署未执行。
- 增加面向人工操作人员的 GitHub Actions、CNB、TCR、1Panel 端到端发布手册，统一 `strict` 与 `fast` 选择、三端构建核对、单镜像证据、固定 digest 拉取、首次初始化、日常更新、健康检查、停止条件、发布记录和回滚步骤；现有专题文档收敛为工作流机制、账号权限、容器、生产基础设施和回滚决策入口。
- 为 GitHub `Handoff Source to CNB` 增加默认 `strict`、可显式选择 `fast` 的双验证模式：严格模式完整核对同 SHA Full Validation Artifact，快速模式要求单行原因并记录 Commit、操作者和未执行完整验证的事实；四个轻量 Push 工作流、默认分支、应用状态、模块边界以及 CNB/TCR 供应链门禁在两种模式下继续强制执行。
- 将 CNB 三镜像统一发布拆为 `backend-image`、`web-image` 和 `admin-image` 三条按真实 Docker 输入触发的独立 Pipeline：每端使用独立锁、Registry 缓存、扫描、SBOM、provenance、OCI 来源标签和 `pinjie-cnb-tcr-image-v1` 证据；`SOURCE_DATE_EPOCH` 使用 Git committer time，并增加仅在 `main` 可见的受控三端全量构建入口，生产继续通过 1Panel 按完整 digest 人工更新。
- 将生产 Compose 改为复用 1Panel 管理的共享 PostgreSQL 18.4 与 Redis 8.10.0：应用侧移除项目内数据库、缓存服务和数据卷，Backend 与可选日志消费者通过外部 `1panel-network` 访问共享实例，Web 与 Admin 保持网络隔离；生产 PostgreSQL 使用独立数据库与角色，当前 Redis 使用 `default` 用户和独立逻辑库 `/1`，并明确逻辑库不提供权限隔离；同步环境变量、配置门禁、备份恢复和迁移回滚边界。
- 增加腾讯云 TCR 个人版 CAM 最小权限操作手册：区分 CNB `tcr-publisher` 与生产服务器 `tcr-puller`，提供三个指定私有仓库的只读 JSON、个人版凭证初始化、服务器 Docker 登录、正反向权限验收、轮换、禁用、泄露响应和常见错误处理，并明确企业版服务级账号不适用于当前个人版链路。
- 增加 GitHub 到 CNB 的固定 SHA 源码交接和 CNB 到 TCR 的单仓发布链路：GitHub 继续核验四项 Push Run，默认严格模式同时核验同 SHA Full Validation Artifact，只以非强制快进方式更新 CNB `main`；CNB 使用固定 digest 工具镜像构建三端镜像、复用 TCR Registry 缓存、执行 Trivy、CycloneDX SBOM、BuildKit provenance、SHA 标签冲突保护、写后 digest 复核和结构化发布证据，不再由 GitHub Runner 上传生产镜像层。
- 完成连续不同 Commit 的 CNB 到 TCR 真实发布验证：三张 Run 唯一候选镜像及其 SBOM、provenance 和 TCR digest 复核通过，Trivy High/Critical 门禁通过，最终 SHA 标签、`pinjie-cnb-tcr-release-v1` 清单和十份附件均写后校验成功；固定 epoch 缓存复验将完整发布从 14 分 19 秒降至 1 分 29 秒，生产部署未触发。
- 为三端镜像发布增加 GHCR 与腾讯云 TCR 个人版双仓输出：同一次 BuildKit 构建按相同内容 digest 推送两个 Registry，发布矩阵在扫描前分别核验候选 digest，最终阶段同时执行 SHA 标签冲突检查、创建和写后复核；TCR 凭证仅来自受保护的 `image-publishing` Environment，现有生产部署继续使用 GHCR，待地域和独立只读身份确认后再切换运行镜像源。
- 建立同 Commit SHA 的完整验证与镜像发布证据门禁：人工 `CI - Full Validation` 在默认分支上校验目标 SHA，依次运行 Backend pytest、Admin/Web Vitest、两端 production build 和 Chromium Playwright，全部成功后上传 30 天保留的不可变 Artifact；`Publish Images` 通过 GitHub Actions API 核验成功 Run、Artifact 有效期、Commit SHA、Run ID 和完整验证集合，缺失或不一致时在镜像构建前失败关闭。
- 建立文档权威边界与索引一致性自动门禁：根项目索引只维护身份、阶段、活动计划和权威入口，详细实现状态回归实际源码、配置、迁移、生成契约和专题架构文档；`docs/` 明确为专题项目文档唯一发布来源；治理检查自动拒绝已废弃索引路径、规则正文或桥接漂移、指令容量不足、计划登记或活动状态不一致、非法计划枚举和专题文档漏登记，并通过 9 类负向夹具验证。
- 增加全局系统设置与站点配置媒体能力：Backend 使用单一 `system_settings` 表按 `site`、`registration` 固定分组保存强类型 JSONB，提供 revision 并发保护、配置级权限、审计和注册 Fail Closed；Admin 新增 `/settings` 的站点与注册两个固定 Tab，支持独立 LOGO 上传、只读权限和冲突草稿保留；Web 通过完整 SiteProfile 统一首页、登录、注册、用户中心品牌与 Metadata，并以带 revision 的同源代理缓存固定配置媒体。站点 LOGO 使用独立可补偿目录，不进入文件资产表。
- 将超级管理员身份授予从 `admins:update` 拆分为独立的 `PATCH /api/v1/admin/admins/{admin_id}/superuser` 和系统权限 `admins:superuser:change`：普通角色无法分配该权限，Dependency 与 Service 双重校验操作者真实超级管理员状态，管理员资料更新不再接受 `is_superuser`，创建管理员入口同样阻止普通管理员直接创建超级管理员；资料、状态、角色、密码和会话操作增加超级管理员目标保护，批量状态目标包含超级管理员时也要求超级管理员身份，Admin 身份操作、行级入口和角色权限 Tree 已同步新边界。
- 为 Admin 管理员、用户和角色列表增加状态列直接切换：三页复用统一的可点击状态 Tag、行级 Loading、成功刷新和失败提示；无更新权限时仅显示只读状态，管理员本人和用户回收站继续受原有保护，原操作入口及批量状态操作保持不变。
- 将 Admin 角色权限配置升级为弹窗内直接展示的 Ant Design Tree：扁平源码权限目录在前端按用户、管理员、角色与权限、安全与系统、文件资产分组，支持父子联动、名称与权限码搜索、全选、反选、清空、展开控制和已选统计；搜索不改变隐藏选择，停用权限保持可见并锁定，未知权限进入“其他权限”，保存前只保留后端目录中的真实权限码。
- 增加 Web 用户头像资料闭环：用户中心可上传、更换和移除本人头像，Backend 通过 `users.avatar` 和 `PUT /api/v1/users/me/avatar` 校验本人上传的 `avatar` 资产并持久化；头像为空或图片失效时回退显示名称首字符，仍被用户或管理员引用的资产禁止硬删除，上传后绑定失败会明确提示。
- 增加 Admin 创建普通用户与公开注册开关联动：新增受 `users:create`、管理员会话、CSRF 和审计保护的创建端点，管理员手动填写初始密码并可决定是否允许登录，创建过程不产生 Web 会话；Web 通过公共能力契约服从 Backend 数据库中的注册设置，关闭时隐藏注册入口并重定向，能力不可用时失败关闭。
- 升级 Admin 系统状态页面为全景监控看板：后端提供受 `system:overview:read` 保护的聚合接口 `GET /api/v1/admin/system/overview`，支持 PostgreSQL 与 Redis 实时探针、公开运行配置摘要，以及带 120 秒 Redis 缓存、采样时间、来源和超时状态的业务遥测；统计排除回收站用户并采用启用管理员、启用角色、现存资产和保留期内审计事件口径。前端保留全局健康横幅、基础设施与安全配置、资产遥测和运行环境 4 大板块，支持手动刷新和 15/30/60 秒轮询，刷新失败时继续显示有明确过期提示的上次成功数据。
- 建立 AI 辅助开发的本地检查点与高风险文件编辑治理：功能单元通过轻量验证后主动请求本地提交授权，已获分阶段授权时立即精确提交；批量整文件写入必须具备可恢复基线、严格错误处理、写前校验、原子替换和逐文件复读，且不扩大推送等独立授权。
- 增加统一用户软删除回收站：通过 `SoftDeleteMixin` 记录删除时间、删除主体和可选删除原因，用户自助注销与 Admin 单条或批量删除统一进入长期可恢复回收站；移除恢复截止、匿名化字段、到期匿名化脚本和回收站保留期配置，恢复后保持停用。
- 增加 Admin 文件资产管理页与受权限控制的资产筛选、预览、地址复制、单条删除和批量硬删除；图片资产在操作列点击“打开”时使用 Ant Design 当前页预览，非图片继续在新窗口打开；上传主体列隐藏 UUID 文本，在主体类型旁提供带反馈的图标复制入口；Backend 资产列表支持文件名、场景和上传主体筛选，批量删除通过固定锁顺序、文件暂存、失败恢复、权限、CSRF 和审计保持可补偿一致性。
- 建立 Admin 列表治理基线：除明确登记的只读日志外，数据列表必须按权限提供批量选择和与实体生命周期一致的批量操作；新增 Admin 管理端点必须显式声明资源权限并通过受控权限目录同步进入目标环境。
- 为 Admin 用户和角色列表增加受权限控制的批量选择、启用、停用和删除操作：用户删除采用可恢复软删除，角色删除采用未被管理员引用时的硬删除；Backend 提供四个原子批量端点，并保留管理员列表既有批量启停及安全日志只读边界。
- 完善 Admin 管理员列表：展示头像与显示名称，提供资料编辑、身份列超级管理员切换、独立密码重置、批量启用或停用，以及“编辑、角色、会话、更多”的紧凑不换行操作布局；管理员列表与顶部账户菜单统一使用浅色首字符头像回退，头像为空或图片加载失败时不再显示空圆形；Backend 同步增加头像更新和原子批量状态接口。
- 增加统一文件与多媒体资产服务：本地存储端口、Magic Number 与场景策略、同主体 SHA-256 去重、双域 Cookie/CSRF 上传、RBAC 资产查询、标准警告审计删除、Admin/Web 上传组件及生产持久卷。
- 增加 Session 分页契约、Refresh Token 级联清理和默认 dry-run 的会话保留清理工具，支持显式 `--apply`、结果统计和隔离测试库验证。
- 增加 Admin 认证 HTTP、启动生命周期、权限映射和 Web BFF/SSR 会话恢复回归测试，将高风险传输边界纳入前端覆盖率门禁。
- 增加 Web App Router PNG favicon，使用 Next.js `ImageResponse` 生成业务中立的 Pinjie 图标，并通过 production build、桌面和移动浏览器及真实资源响应检查。
- 建立 GitHub 单维护者远端治理基线：启用漏洞告警、Secret Scanning、Push Protection 和私密漏洞报告，限制 Actions 来源并要求完整 SHA Pinning，为 `main` 配置 Ruleset，并预创建不含 Secrets 或 Variables 的 `production` Environment。
- 增加基于 TypeScript Compiler API 的前端依赖图门禁，覆盖跨应用引用、Feature 内部越界、循环依赖和可静态解析的动态导入，并提供正反例。
- 增加 PostgreSQL 本地迁移与备份恢复演练工具，强制使用独立 `_test` 数据库并校验 revision、表、行数和约束。
- 增加 1Panel 单机生产运行手册，覆盖不可变镜像、环境变量、迁移、健康检查、日志、备份恢复和回滚边界。
- 增加错误请求入参捕获与脱敏管道：仅对非敏感路由的错误 JSON 请求捕获入参，递归脱敏敏感字段，最多保存 4096 个字符并通过 Redis Stream、PostgreSQL 和 Admin 只读抽屉提供排障入口。
- 增加 Backend Loguru 本地文件日志能力：支持环境变量控制的开关、路径、50 MB 轮转、10 天保留、ZIP 压缩和异步写入；只读容器可关闭文件 Sink。
- 完成阶段 C 通用业务核心能力：C/B 独立 Browser Cookie Profile、Argon2id、JWT、Session 绑定 CSRF、PostgreSQL 权威 Refresh Rotation、重放撤销、Redis 原子限流和严格 Origin 校验。
- 增加用户、管理员、角色、权限、会话、Refresh、安全登录事件、审计和可选请求元数据模型及 Alembic 迁移，并提供初始化管理员、权限同步、日志保留清理和 Redis Stream 消费脚本。
- 完成 Web 注册、登录、SSR 用户中心、资料、密码、会话、退出和注销流程，以及 Admin 登录、权限导航、用户、管理员、角色权限和安全日志工作台。
- 增加阶段 C 真实 PostgreSQL/Redis 集成测试、C/B 安全回归、Admin/Web 组件测试和桌面/移动 Chromium 跨栈 E2E；Web production E2E 使用 Next.js standalone server 和受控跨平台服务回收脚本。
- 增加 Browser Cookie Profile、会话、RBAC 与审计 ADR，明确未来小程序和原生 App 通过独立 Public Client Bearer Profile 扩展。
- 完成阶段 B 运行基础设施：Backend FastAPI 入口、统一响应与错误处理、请求上下文、数据库会话与事务、Redis 生命周期、健康探针、系统状态接口、Alembic 环境、UUID v7 和基础测试。
- 完成 Admin/Web 业务中立系统状态页、同域 API 代理、Vitest + RTL + jsdom + MSW 组件测试及覆盖率门禁。
- 增加根 Playwright Test 与 axe 跨栈 E2E 配置，覆盖桌面和移动 Chromium、控制台错误、横向溢出和关键可访问性扫描。
- 增加 Backend、Web、Admin 三个生产 Dockerfile、Nginx 同域代理、生产 Compose 健康依赖和 PostgreSQL 18.4/Redis 8.10.0 运行基线。
- 增加 PostgreSQL 测试隔离约束、OpenAPI 原子导出、生成 API Client 和独立浏览器 E2E CI 工作流。
- 增加 Backend 默认 90% 行与分支覆盖率门禁，以及配置、Redis、限流、健康探针和真实用户/管理 API 生命周期回归测试。
- 增加仓库级 markdownlint 配置、VS Code 扩展建议和固定版本的 `pnpm lint:md` 命令，以 GFM 为语法基线统一 AI 与开发者的 Markdown 格式。
- 建立 Git 提交追溯规则，区分普通提交的 Git 历史与发布、部署、派生、安全审计、回滚和交接等跨系统 SHA 记录。
- 建立全项目索引，统一导航项目身份、三端开发目标、计划、系统状态、权威来源和派生项目入口。
- 建立全栈计划生命周期和永久保护规则，禁止 AI 删除、移动、重命名或替换既有计划文档。
- 建立派生项目记录母版基线、派生类型和业务范围的治理入口。
- 建立 `docs/PROJECT_REQUIREMENTS.md` 产品需求基线，集中定义母版目标用户、适用场景、目标能力、非目标、派生规则和完成验收标准。
- 建立 `BASE-*` 需求编号与全栈计划关联规则，区分目标能力、当前实现状态、实施过程和已交付事实。
- 建立讨论结论知识沉淀规则，将已确认或有证据的长期结论路由到现有权威文档，不保存聊天原文，也不提前创建空的 Brainstorming 或 Research 目录。
- 纳入 Backend、Admin、Web、共享包、Compose、GitHub Actions、ADR、架构、蓝图和运维文档的完整工程骨架。
- 建立 `empty`、`partial`、`ready` 三态工程完整性门禁；部分实现、契约不一致和跨模块内部依赖会直接失败，空骨架只报告治理检查结果。
- 建立模块化单体、领域所有权、Fail Closed、认证授权分层、测试、可观测性和可靠性架构基线。
- 建立受控迁移兼容和不可变发布 ADR，生产部署固定镜像 digest，禁止 `latest` 与缺失版本回退。
- 增加 GitHub Actions 工作流说明，记录 push 自动检查、Pull Request 差异门禁、人工镜像发布、生产部署和失败定位流程。
- 增加 `SECURITY.md`、CODEOWNERS、Pull Request 风险模板、Gitleaks、Dependency Review、包管理器依赖审计、依赖文件扫描和 Semgrep CE 静态代码扫描治理基线。
- 分离 CI、镜像发布和生产部署工作流；发布生成 SBOM 与构建来源证明，部署要求受保护环境、明确开关和固定 digest。
- 增加发布回滚、数据库备份恢复和事故响应手册，以及统一文本编码、换行和模块边界检查脚本。
- 增加环境变量分层与 Backend 本地运行手册，明确根 `.env`、三端应用配置、1Panel 部署关系和 VS Code 下的后端启动顺序。
- 建立 Backend 两层规则体系，以 `apps/backend/AGENTS.md` 承载宪法级红线和任务读取路由，以工程实施标准承载 FastAPI、事务、数据库、缓存、外部调用、日志、探针、测试和质量门禁的具体规范。
- 增加 AI 助手开发与文档读取指南，区分 Codex、Antigravity 的自动规则发现和项目主动读取，并覆盖常见任务、计划确认、跨栈实施、验证交付与独立授权链路。
- 初始化 GitHub Wiki，并从主仓库已推送提交完整同步 `docs/` 下 12 份受管文档和同步清单。

### Fixed

- 修复后端数据规划审查阶段 A 的零折扣和积分幂等问题：SKU、商品和分类继承中的零折扣保留为零，缺少折扣因子明确报配置错误；人工积分重放核对完整意图及债务分量，按幂等键和用户账户串行保护首次建账。新增报价、重放冲突及 PostgreSQL 并发回归用例源码；本轮 pytest 和数据库动态验证按项目策略未执行。

- Admin 仅在打开或整页刷新时，身份恢复触发的 Refresh 返回 `503 / SERVICE_UNAVAILABLE` 后跳转登录页，保留原站内回跳地址并显示安全错误消息与请求编号；开发环境提示检查 Redis。运行期间、普通接口 503、429 和网络故障保持原处理；补充回归用例，动态验证未执行。

- 修复 Admin 全量审查发现的权限目录失败误清空角色权限、设置草稿版本错配、角色分页截断、运行中会话失效恢复、角色启停覆盖资料和头像上传保存竞态；同步过期权限与欢迎页测试断言并补充针对性回归用例。Admin typecheck、lint 通过，Vitest、生产构建和浏览器自动化按当前授权未执行。

- 修复商城 M1 至 M4 的库存总容量与版本、分类可售、购物车陈旧覆盖、订单幂等和金额边界、跨阶段锁顺序、退款原支付与累计额度核对、推荐并发与付款时点快照、累计追佣舍入、提现解冻抵债及敏感错误日志问题。跨领域编排收敛至应用层，补齐后台订单、履约、退款查询及精确权限。新增 `20260917_05` 迁移、回归测试源码并同步契约；购物车修改要求 revision，与尚未推送的 M1 至 M4 实现同批交付，相对远端 main 无破坏性诊断。实际迁移、权限同步、pytest 及真实并发测试未执行。

- 为冻结的 Web Dockerfile 补充非 root `USER node`，修复 Semgrep 的 `missing-user` 告警；保留构建与启动主动失败。仓库启用 Dependency graph 后，线上 Security 复验通过。

- 修复 GitHub Dependabot 的 10 条 Moderate 前端依赖告警：锁定 decode-uri-component 0.5.0、qs 6.16.0、hono 4.13.5、colord 2.9.4 及 Admin/Web Vitest 和 coverage-v8 4.1.11；query-string 6.14.1 通过受控 CommonJS 补丁继续使用安全解码器。依赖检查覆盖锁文件、补丁和畸形编码解析行为；Vitest、生产构建和浏览器验证按策略未执行，远端告警待源码交付后由 Dependabot 重扫确认。

- 修复根 Markdown 工具链的 `smol-toml` 高危依赖阻断：通过限定 `markdownlint-cli2@0.23.2` 的传递依赖并重新生成锁文件，将实际安装版本固定为 1.7.1；Markdown、文本、文档、依赖、工作区和边界轻量门禁通过，PR #53 的 13 项必需检查通过，重型验证、发布与部署未执行。

- 将 Web Next.js 与配套 ESLint 插件升级至 16.3.3，并锁定 sharp 0.35.4、js-yaml 4.3.2 与 SVGO 2.8.4，修复线上依赖门禁报告的两项 Critical 和三项 High；保留七天冷却、Umi 补丁、构建白名单和线上安全门禁。源码依赖修复不代表现有生产镜像已更新，构建、重型测试、镜像发布与部署未执行。

- 统一 Admin 所有单条与批量删除、移入回收站及移除操作的二次确认：用户删除复用标准弹窗并保留可选原因，系统设置 LOGO 与管理员头像移除补齐确认；公共弹窗增加同步防重锁、提交中关闭保护及失败反馈，LOGO 固定确认时 revision，头像继续保存后生效并与上传互斥。保留角色、文件资产现有确认流程，同步管理端规则与验收基线；轻量门禁通过，Vitest、构建和浏览器验证未执行。
- 修复 Admin 生产 Nginx 与 Backend 重复输出安全响应头，导致头像下载得到 `nosniff, nosniff` 并阻断 Full Validation 的问题；由代理统一输出四种安全头，保留后端直连保护和 E2E 严格断言。
- 修正 Full Validation 矩阵命令的环境变量传参，使 Semgrep 严格扫描可以解析；安全扫描增加解析诊断，发布工具子进程限制可执行程序、固定禁止 Shell 并防止调用选项覆盖。
- 修复事务内管理员权限重查复用旧 ORM 状态、两端将业务凭据错误误判为会话失效以及刷新故障被原 401 掩盖的问题；Web SSR 会话恢复增加非认证故障提示与手动重试，管理员站内头像保存与资产删除共用行锁并校验有效引用。
- 修复 CNB 变更路由夹具使用动态正则触发 Semgrep ReDoS 阻断的问题，改用固定路由模式匹配并增加通配符不得跨目录的负向夹具；同时将 `fast-uri` 固定到修复 4 个 High 漏洞的 `3.1.6`。
- 修复 1Panel Web 编排预拉取无法识别应用镜像 `${VAR:?提示}` 表达式的问题：四个应用服务改用基础变量插值，继续由生产门禁核对准确变量名和完整不可变 digest；补充错误变量接线负向夹具，以及面板任务状态与实际容器状态不一致时的健康核验步骤。
- 修复 Admin Alpine 运行镜像只升级手工包清单导致新可修复漏洞遗漏的问题，构建时升级当前仓库中的全部已安装包；CNB Trivy 阻断现在输出精简漏洞表格，并在失败阶段保存原始扫描、digest、metadata 和摘要附件，同时继续保持 High、Critical 门禁 Fail Closed。
- 修复 CNB 跨 Commit Registry 缓存失配：`SOURCE_DATE_EPOCH` 从每个 Git Commit 的提交时间改为固定 Unix epoch `0`，避免未变化的 COPY 和依赖层因文件元数据时间不同而重新构建；复验确认 Backend `uv sync`、Web/Admin `pnpm install`、应用复制和 production build 层全部命中，候选构建和缓存写回从 13.2 分钟降至 57.4 秒，完整 Commit SHA 继续由 BuildKit provenance 和结构化发布清单追溯。
- 修复 Web 与 Admin 生产运行镜像被基础层可修复漏洞阻断发布的问题：Web runtime 升级 Alpine OpenSSL 并移除 standalone 服务不需要的全局 npm，Admin runtime 只升级 Trivy 命中的 c-ares、curl、OpenSSL、libexpat、libxml2 和 nghttp2 包；保留 Node/Nginx 运行方式、非 Root 用户、健康检查、Trivy High/Critical Fail Closed、SBOM 和构建来源证明。
- 修复 Backend 生产镜像被基础系统与运行时工具中的可修复 High 漏洞阻断发布的问题：builder 与 runtime 同步更新到官方 Python 3.14.7 slim-trixie Linux amd64 固定摘要，runtime 精确安装修复后的 OpenSSL 包并移除应用运行不需要的全局 pip 及其 vendored 代码；继续保留 Trivy High/Critical Fail Closed、SBOM、构建来源证明和当前源码交接验证模式要求。
- 修复首次远端完整验证中测试 Origin 配置错配的问题：Runner 同时允许真实 E2E 使用的 `127.0.0.1` 与 Backend 既有 API 测试使用的 `localhost`，避免 pytest 请求在业务断言前被 CSRF Origin 校验拒绝。
- 修复 Backend uv 工具版本和锁文件元数据可能漂移的问题：项目通过 `required-version` 固定 uv `0.11.32`，Backend、完整验证和 Security 工作流显式安装同一版本，并用该版本重建和验证 `uv.lock`；同时补齐根 README 遗漏的 Backend、Admin 和 Web 实际能力目录。
- 修复 Admin 系统设置页站点 LOGO 预览随原图比例变化的问题，预览区域固定为正方形并保持图片完整适配；同时补齐站点资料、LOGO、注册策略、revision 冲突、权限与失败重试组件测试。
- 修复全栈重型门禁暴露的契约与可访问性问题：Web BFF 放行公开 SiteProfile 同源读取，Admin 响应式数据表隐藏包含可聚焦全选框的 Ant Design 测量行，Playwright 按当前站点资料断言品牌标题；以前向迁移修复用户软删除字段注释漂移，并同步 OpenAPI 与 API Client 中文说明。
- 修复 Web 与 Admin 会话始终显示“未知设备”的问题：Backend 使用锁定版本的 `ua-parser` 从已清理 User-Agent 生成“浏览器 · 操作系统”展示名称，新登录会话直接保存标准化结果；同时提供默认 dry-run、显式 `--apply` 且不输出敏感原文的旧会话回填工具。
- 修复 Admin 用户、角色和文件资产列表在移动端缺少表格内横向滚动的问题：三页使用明确的 `scroll.x` 并将滚动限制在表格内部；用户页将生命周期切换压缩为移动端下拉框，文件资产页将场景和上传主体筛选收进底部抽屉，搜索和常用操作保持紧凑且桌面端交互不变。
- 修复 Admin 公共样式在所有 `.ant-table-container` 上强制设置 `overflow-x: auto`，导致普通列表形成重复滚动层并在右侧显示异常纵向滚动条的问题；标准列表恢复弹性布局，真实宽表继续使用 Ant Design `scroll.x` 受控滚动。
- 修复 Admin 未认证请求在认证 Cookie 校验前解析数据库资源导致错误语义漂移的问题，补齐系统概览嵌套 OpenAPI 中文说明及生成客户端注释。
- 修复 Admin/Web 测试夹具、Ant Design 可访问名称和响应式列模拟漂移，并补齐系统概览、个人设置、文件资产与 API 请求形状回归，使 Backend、Admin、Web 全量覆盖率门禁恢复通过。
- 修复 Web 用户中心移动端头像区横向撑宽和资料表单指针命中异常；浏览器 E2E 改为串行执行共享测试管理员流程，消除桌面与移动项目并发修改资料的竞态。

- 修复 Web BFF 遗漏 `PUT /api/v1/users/me/avatar` 导致头像绑定在到达 Backend 前返回 `404`；同步以表驱动用例覆盖全部 13 个浏览器端代理接口，并继续拒绝 Admin 与未登记接口。
- 统一 Admin 列表空态：使用 `ProTable` 的页面只显示表格内建“暂无数据”，外层查询状态仅处理加载、失败和重试；无 `ProTable` 的列表、抽屉和面板继续保留独立空态。
- 补齐管理员头像输入输出字段的 OpenAPI 中文说明、隔离测试 Redis 变量与 pytest 临时目录，并以前向迁移修复 `request_logs` 表注释漂移。
- 移除 Umi `4.7.5` 未使用的 Vite 4 构建链，通过精确 pnpm Hook 和受控补丁关闭不安全入口，修复 Webpack 开发服务器忽略 host 的行为，并增加版本漂移、锁文件和补丁门禁。
- 修复 Web/Admin Cookie Profile 共享 Origin 与代理路径导致的跨端会话越权面；Backend 按 Profile 精确校验 Origin，Web BFF 和 Admin Nginx 只允许各自路径并过滤另一端 Cookie。
- 修复最后超级管理员并发竞争、跨 `AsyncSession` 事务上下文误判，以及认证提交后 Redis 限流清理失败翻转成功结果的问题；真实 PostgreSQL 并发和 Redis 失败路径均已覆盖。
- 修复 Admin/Web 刷新、退出和改密生命周期不一致，统一为单次 Refresh 与一次重放、失败保留当前页面、改密保留当前会话并轮换 Cookie。
- 修复 Web canonical 在构建时固化 localhost、子页面标题重复品牌名，以及 Next.js 16.3 standalone 在 Windows 复制目录链接后无法启动的问题。
- 修复 Browser E2E 仍使用旧统一 CORS 变量且未注入 Web 公开 Origin 的配置漂移；冷启动 wrapper 现可自行启动 Windows standalone、Umi 和四个桌面/移动项目。
- 修复 Umi 工具链四项可安全升级的传递依赖漏洞：范围受控地将 `@babel/core`、`@babel/runtime`、`esbuild` 和 `send` 提升到修复版本，旧漏洞解析已从根锁文件移除，并通过 Admin、Web 和真实跨栈回归。
- 修复 Backend 文件日志默认文本格式遗漏 Loguru 绑定字段的问题；文件 Sink 改为 UTF-8 JSON Lines，请求记录稳定包含 `request_id`、`trace_id`、HTTP 方法、规范化路由、状态码和耗时，并由真实文件写入测试覆盖。
- 修复 Admin 五个受保护页面只提供命名导出，导致 Umi production lazy route 触发 React 306 错误的问题；用户、管理员、角色、安全和系统状态页面现同时提供路由所需的默认导出。
- 修复 Web 主动退出期间迟到的用户或会话请求 401 覆盖预期 `/login` 跳转的问题；退出发起前显式中止在途读取并增加竞态回归测试。
- 修复 CI 暴露的 Backend Ruff 格式不一致和 Web 测试 matcher 类型缺失问题；Web TypeScript 现在显式加载 Vitest 与 Testing Library matcher 类型。
- 修复 GitHub CI 的 Alembic `request_logs` 表注释漂移，并修正 Admin Umi 代理在 Linux CI 下改写 Origin 导致登录 403 的问题。
- 修复 Browser E2E 在 Admin 登录跳转后读取已释放响应体和过早启动的问题，为 Umi 初始 HTML 补齐页面标题、中文语言属性和允许缩放的 viewport；E2E 模式关闭 MFSU，只在 `/umi.js` 返回 JavaScript Content-Type 后启动浏览器测试，并在解析登录响应前校验 JSON Content-Type。
- 修复 Web Vitest 运行时未注册 Testing Library DOM matcher 的问题；显式扩展 Vitest `expect` 后 Web 17 项测试全部通过。
- 修复 Node 传递依赖的高危漏洞门禁：通过精确 pnpm overrides 提升 `immer`、`node-fetch`、`axios`、`image-size` 和 `vite`，本地 `pnpm audit --audit-level high` 不再报告 High 或 Critical 漏洞。
- 修复 Web 首页在用户已经登录后仍显示“登录”和“创建账户”入口的问题；首页通过服务端当前用户接口确认真实会话，匿名或身份服务暂不可用时继续保留入口。
- 修复 PostgreSQL 18 生产命名卷挂载路径，并在生产 Compose 中默认关闭 Backend 与请求日志消费者的文件日志，避免非 Root 只读运行时写入失败。
- 修复 OpenAPI 公开 Schema 字段缺少中文说明的问题，238 个字段现由 Backend Schema 源码生成中文描述，根契约与共享 API Client 已同步。
- 修复 Governance 文本检查在 Linux PowerShell 中无法读取点文件、正反例脚本遗留预期失败退出码的问题。
- 修复生产部署摘要直接向 Bash 插入 GitHub 表达式的注入风险，并修正 Admin Nginx 健康响应的内容类型声明。
- 修复根 `.env.example` 的乱码、粘连和职责错位，只保留 `compose.prod.yml` 使用的公开部署变量模板。
- 修复 Compose、GitHub Actions 和共享包说明中的既有乱码与换行损坏，并统一文本文件为 UTF-8 无 BOM且保留末尾换行。
- 修复角色创建后响应序列化触发 SQLAlchemy 异步懒加载并返回 500 的问题。
- 修复 Admin 非 Root Nginx 因 PID 指令层级和运行目录不可写而无法启动的问题。

### Changed

- 收紧 pnpm 安全补丁验证：根锁文件、冻结安装和实际消费者模块解析共同构成证据，禁止依据 `node_modules/.pnpm` 的目录枚举、名称或残留实例判断版本；排障只清理本次确认归属的临时资源。

- 同步 GitSync 全仓交付规则：显式执行即授权处理本仓库全部本地分支、提交及可交付 worktree 改动，自动保留整合，不因 main 领先或分叉重复确认；同一错误三次修复或恢复仍失败即中止并报告，由用户决定后续处理。Security 扫描仅在 GitHub Actions 执行，不要求本地扫描或统一 pnpm 前置入口，保留既有轻量检查、秘密核对和线上门禁；更新开发与工作流指南，Antigravity 全局同名技能同步相同规则。

- 当前单维护者、1Panel 人工部署流程取消候选镜像验收、专用 Environment/Secrets、请求 JSON 和自动变量预检要求；统一为 CNB/TCR 人工核验、固定 digest 更新和上线复验，并明确纯文档无运行影响时无需更新镜像或容器。工作流与脚本保持现状，不纳入当前流程。
- 优化 AI 执行规则：局部低风险修改不强制新建计划，已有授权不因计划登记或任务续接重复确认，检查失败先修复范围内问题，检查点提交不阻塞实现；同步开发指南、按影响维护索引和真实完成条件，保留重型验证、Git 及生产动作授权边界，并消除 Admin 既有二次确认规则的歧义。
- 派生项目计划基线规则调整为母版永久保留全部计划，独立业务仓库可在派生初始化阶段由用户人工一次性清理母版继承计划并重建索引；AI 仍不得删除、移动或重命名计划，派生项目必须同时记录母版不可变 Tag 和完整 Commit SHA，初始化结束后恢复计划永久保护。
- 将根目录 `PROJECT_INDEX.md` 精简为项目身份、当前阶段、活动计划和权威入口；新增 `plans/INDEX.md` 作为全部实施计划的唯一永久登记，`plans/README.md` 继续只维护计划规则和生命周期。
- 全项目索引迁移到根目录 `PROJECT_INDEX.md` 并作为唯一当前事实与任务导航入口；项目规则、README、PRD、ADR、架构、运维和全部既有计划中的旧名称与路径已同步更新，`.agents/` 继续只保留 Antigravity 规则桥接文件。
- Admin 登录表单输入框改用 Ant Design Filled 变体，默认使用透明边框和半透明白色填充，hover 与 focus 逐级增强背景和焦点反馈；输入内容、占位文字和登录按钮文字继续使用 `14px / 400`，登录按钮保持浅蓝底与深蓝字。
- Admin 登录页“忘记密码？”改为浅灰色说明入口，取消点击弹窗；鼠标悬停或键盘聚焦时通过 Ant Design Tooltip 提示“请联系超级管理员为您重置密码”。
- Admin 登录页能力描述改为“统一身份、精细权限、全链路审计的管理中枢”，以相同字符数直接概括现有认证、RBAC 与审计能力。
- Admin 登录页品牌标识改用与浏览器图标同源的品捷 SVG 轮廓，通过 CSS Mask 呈现 `#D32029` 扁平深红单色并放大至 `54px`，移除临时 `PJ` 菱形标识和高光渐变；登录、会话说明和忘记密码提示保持不变。
- Admin 登录页按参考页面调整为无卡片窄表单，视觉中心位于视口上部约三分之一，并保留项目品牌标识、低透明度蓝青红三色宽幅斜向漫射背景和单行页脚；背景使用固定 CSS 渐变且不随机变化，保留真实用户名密码认证、错误反馈和安全 Cookie 会话，移除无效的自动登录复选框、单标签 Tabs 与第三方登录图标，并将“忘记密码？”改为联系超级管理员重置密码的悬浮提示。
- 统一 Admin 管理操作确认规则：整个管理端移除密码二次确认 Token 的授权语义、确认请求头和密码确认弹窗；只有角色、文件资产等物理硬删除在单条和批量入口共用标准警告弹窗，按钮固定为“确定”和“取消”，用户软删除、启停、凭据重置、会话撤销、身份与权限调整直接提交；Backend 继续执行管理员会话、资源权限、CSRF、事务内资源校验和审计。旧版确认端点按 ADR 0007 临时保留至 2026-09-26，仅用于契约迁移并记录弃用调用。
- 三端日常开发、`$git-sync`、Push 与 Pull Request 收敛为轻量门禁：Admin/Web 只自动运行 typecheck 和 lint，Backend 只自动运行静态、导入与契约检查；前端 build、Vitest、pytest、Playwright 和测试数据库验证仅在用户明确授权后执行，GitHub Actions 不再自动运行这些重型验证。
- Admin 桌面布局按 Ant Design Pro 官方比例调整：展开侧栏统一为 `256px`，PageContainer 移除 `1480px` 固定上限并改用流式工作区，桌面与移动端按 `40px`、`24px`、`16px` 三级内边距响应，保留现有页面、表格和业务操作。
- 保留 `Protect main` Ruleset 和 13 项必需检查，启用 rebase Auto-merge 与合并后自动删除分支；`$git-sync` 现可一次完成当前任务的分支、提交、推送、PR、检查等待、自动合并、分支清理和本地 `main` 同步，失败时保留 PR 与分支并停止。
- 四个自动 GitHub Actions 工作流收敛为目标为 `main` 的 Pull Request 和 `main` push 触发，Security 继续保留每周定时扫描；功能分支 push 不再重复运行整套检查，合并后的 `main` 仍生成镜像发布所需的四项 Push Run。
- Admin 全面采用官方 Ant Design 6 与 ProComponents 视觉交互体系：以 ProLayout 官方 Token 实现浅色侧栏、白色 Header 和浅灰工作区，恢复 ProTable 原生工具栏与轻量操作列，移除侧栏 Logo，并新增 `/welcome` 默认主页和管理快捷入口；认证、RBAC、CSRF 与 Refresh 流程保持不变。
- 收紧 `main` Ruleset：移除维护者永久 bypass，保留 Pull Request、会话解决和 13 项状态检查；日常交付统一通过开发分支和 Pull Request。
- 移除把 Umi bundler 的 Vite 4 强制覆盖到 Vite 6 的不兼容 override；随后从 Webpack 模式依赖树移除未使用的 Umi Vite 4 构建链，Admin Vitest 独立使用 `vite@6.4.3`。
- Backend、Admin、Web、PostgreSQL 和 Redis 的生产基础镜像全部固定完整 digest，生产 Compose 门禁同时覆盖 Dockerfile、应用镜像变量、基础设施引用和可变引用反例。
- 用户、用户管理和管理员管理的 Session 列表统一为有上限的服务端分页响应；根 OpenAPI 与共享 API Client 已重新生成并迁移全部消费者。
- 对 Umi 固定的 React Router `6.3.0` 两条 Medium 告警和暂无修复版本的 `elliptic 6.6.1` Low 告警建立截至 2026-09-21 的限时风险接受；GitHub 使用 `tolerable_risk` 保留依赖链、可达性、负责人和复核条件，本地低级别原始审计继续报告这些未修复上游风险。
- 将内部自用单维护者的自审、管理员 bypass 和 Ruleset bypass 明确为已接受治理模型；不增加第二维护者，继续保留自动状态检查、不可变发布、操作审计以及提交、推送、发布和部署的独立授权边界。
- 将七个 GitHub Actions 工作流中的十个旧版 JavaScript Action 升级到原生 Node.js 24 的正式版本；全部引用继续固定完整 Commit SHA，不再依赖 GitHub Runner 对 `node20` Action 的兼容覆盖。
- Browser E2E 改为 GitHub Actions 人工按需触发，不再随 Push 或 Pull Request 自动运行；Publish Images 取消 E2E 成功记录依赖，继续校验同一 Commit SHA 的 Governance、Backend、Frontend 和 Security 四项自动门禁。
- Admin 全面迁移到官方 Ant Design Pro v6/Umi Max：采用 `@umijs/max`、Ant Design 6、ProComponents 3、Icons 6、ProLayout、Umi 配置式路由和运行时 Access；保留 Cookie/CSRF/Refresh/RBAC、共享 API Client 和现有管理页面。
- 完成 Admin Umi 运行时收尾：通过跨平台 `PORT=3001` 启动包装器固定端口，修复 Umi 环境变量和 initialState 接线，适配 Ant Design 6 弃用属性，并完成桌面/移动登录页浏览器冒烟。
- 用户与管理员的新密码规则统一为 6 至 64 个字符，登录及本人改密时的当前密码输入限制为最多 64 个字符；Backend、Admin、Web 和初始管理员脚本保持一致。
- FastAPI 文档的接口分组、摘要、字段说明和响应说明改为中文，API 成功与失败响应的顶层 `message` 统一为中文；路径、参数、字段、错误 `code` 和 `operationId` 保持英文程序标识。
- 停用 Dependabot 定期依赖升级分支和 Pull Request，依赖版本调整改为人工发起、评审和验证；保留漏洞告警、Dependency Review、依赖审计和静态代码扫描安全门禁。
- 因个人私有仓库无法启用 GitHub Code Security，将不可运行的 CodeQL Job 替换为固定版本、无账号且不上传源码的 Semgrep CE SAST 门禁。
- 清空并关闭 GitHub Wiki，项目文档统一以仓库 `docs/` 为唯一来源，后续提交和文档同步流程跳过 Wiki。
- 生产 Compose 改为强制接收 Backend、Web 和 Admin 的完整不可变镜像引用，缺失变量时立即失败。
- 前端和治理 CI 运行基线升级到仍受官方支持的 Node.js 24，并固定 pnpm 11.17.0。
- uv 和 pnpm 依赖解析增加七天新版本冷却期；pnpm 同时拒绝奇异传递依赖和包信任等级降级。
- pnpm 依赖构建脚本改为显式白名单，仅批准当前构建所需的 `esbuild` 和 `sharp`。
- Backend 生产镜像固定为官方 CPython 3.14.7 slim-trixie 完整 digest，并通过 Linux x86_64 三端容器健康验收。
- 升级 Next.js 至 16.3.0、ProComponents 至 2.8.10、OpenAPI 生成器至 0.99.0、Markdown 检查器至 0.23.2，并通过精确 override 修复间接依赖漏洞；完整 Node.js 依赖审计无已知 High 或 Critical 漏洞。

### Documentation

- 固化 Windows 原生 Codex 的 GitHub CLI Keyring 边界：认证型 `gh` 命令跳过沙箱探测并直接申请准确宿主执行，同时保留登录变更、远端写操作和高风险命令的独立授权要求。
- 将个人 Windows 开发机 Codex 基线调整为 `elevated + Custom`、`workspace-write` 和默认联网，补充 Schannel `SEC_E_NO_CREDENTIALS` 诊断矩阵、准确宿主升级兜底、禁止规避措施及桌面端升级后的复验删除条件。
- 建立 Codex Windows 配置与 ACL 独立标准，统一说明用户级和项目级 `config.toml`、`elevated + Custom`、同机多项目、跨电脑迁移、缓存与代理边界、受保护路径、正反向验收、故障分类、最小修复和回滚；既有 AI 工作流与本地环境文档收敛为入口。
- 建立 Codex Windows 原生沙箱长期治理流程，区分 Owner 混杂、真实 NTFS ACL、工作区边界和命令审批；采用 `elevated + Custom (config.toml)`、最小 uv Cache 可写根、回环代理环境过滤和正反向验证，不对无实际故障的 `CodexSandbox*` Owner 做周期性归一。
- 建立 Admin Umi/Pro 框架边界与工程实施标准，明确 Umi 公共入口、Feature 目录、项目唯一安全 HTTP 管道、Access 与服务端授权、ProComponents 场景化选择及依赖分层准入规则。
- 增加 Admin 本地运行与验证排障手册，明确 Umi 启动目录和端口、生成缓存、jsdom 测试、浏览器兜底验证、真实跨栈前置条件，以及 Windows 系统故障与应用故障的证据边界；同步根和 Admin 级长期规则。
- 完成 Admin 技术栈文档一致性审计：根 README、架构 ADR、环境变量手册、项目结构索引和历史原始方案均已区分当前 Ant Design Pro v6/Umi Max 实现与旧方案记录。
- 完成母版开发总结和一致性收尾：同步根与三端 README、项目结构、依赖白名单来源、历史方案边界、数据库恢复、生产运行文档、67 项需求追踪及 13 条母版验收矩阵，并完成三端质量、容器、文件日志和桌面/移动 Browser E2E 最终验收。
