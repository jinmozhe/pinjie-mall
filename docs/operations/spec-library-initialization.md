# 电商规格属性库初始化手册

本手册用于将零售电商公共规格属性库重建到同结构的本机开发库。脚本采用“先备份、清空后重建”的方式，不做增量合并，也不适用于已投入商品运营、已有商品采用历史或需要保留分类模板的数据库。

## 1. 交付物与数据范围

- 执行入口：[seed_spec_library.py](../../apps/backend/scripts/seed_spec_library.py)。
- 版本化种子：[spec_library.v1.json](../../apps/backend/scripts/data/spec_library.v1.json)。
- 原始资料为 `电商通用规格属性值库.xlsx`，其 SHA-256 在种子元数据中固定。
- 种子记录 1,036 条原始来源映射，其中零售资料 963 条，本地生活资料 73 条均标记为排除且绝不入库。
- 当前种子包含 104 个公共属性和 801 个标准候选值。公共属性默认启用，不自动创建商城分类、分类模板、商品、SKU 或库存。

每条来源记录都保存行号、原始分类、处理结果、原因和目标编码。处理结果只有“保留、合并、拆分、自由录入、排除”；排除记录不得映射到任何属性或候选值。

## 2. 执行前条件

脚本只接受以下目标：

- Settings 中 `environment=local`，连接为本机 `localhost`、`127.0.0.1` 或 `::1` 的 PostgreSQL `asyncpg` URL，且 URL 不含查询参数。脚本以同一已解析连接目标打开应用连接和调用 `pg_dump`，连接后核验实际数据库、本机地址与端口。
- 数据库名称与 `--confirm-database` 完全一致，且不是 `_test` 数据库。
- Alembic 版本为 `20260923_02`，七张属性表、商品、SKU 和分类表的字段、主键、外键与当前模型一致。
- `products`、`product_skus`、`product_spec_attributes`、`product_spec_values`、`product_sku_spec_values`、`product_attribute_values` 均为空。
- 备份目录是仓库外的绝对路径，且运行用户可执行 `pg_dump` 与 `pg_restore`。

脚本还会扫描全部 schema，拒绝清空范围外表对七张表的任何外键引用。连接始终固定 `search_path=public`，防止同名表覆盖。分类模板可以存在，脚本会清空模板并递增受影响分类的版本；分类名称、树层级和其他分类资料保持不变。

## 3. 检查与执行

在仓库的 Backend 目录运行。先执行检查，确认输出的目标库、当前数量和预期数量；检查模式只读，不创建备份，也不改动数据。

```powershell
Set-Location apps/backend
uv run python -B -m scripts.seed_spec_library --check --confirm-database pinjie_mall_dev
```

确认检查通过后，使用仓库外备份目录执行重建：

```powershell
Set-Location apps/backend
uv run python -B -m scripts.seed_spec_library --apply `
  --confirm-database pinjie_mall_dev `
  --backup-dir E:\pinjie-mall-spec-library-backups
```

`--apply` 先核验实际连接目标，取得事务咨询锁和相关表锁，导出七张属性表和完整 `product_categories` 表的数据备份，校验备份文件，再在一个事务中按下列顺序处理：

1. 清空 `product_sku_spec_values`、`product_attribute_values`、`product_spec_values`、`product_spec_attributes`、`category_spec_attributes`、`spec_attribute_values`、`spec_attributes`。
2. 递增原有分类模板所属分类的版本。
3. 生成新的 UUID v7，插入公共属性与标准候选值。
4. 校验数量、编码唯一性、类型规则、归属关系和业务内容摘要。
5. 提交后使用新的只读连接再次核验。

脚本不使用 `CASCADE`、不禁用外键、不执行 Alembic 升级、不打印数据库连接串或密码。提交前的预检、备份、导入或核验失败都会拒绝继续或回滚事务。提交完成后的独立连接核验若失败，数据已经提交，脚本会尽力写入 `committed_unverified` 回执并以失败退出，必须停止重试并按备份受控处理；成功核验后的回执写入失败同样会明确提示已提交且已核验。

## 4. 备份与恢复边界

备份阶段成功后，脚本会在备份目录建立带时间和 UUID 的子目录，其中包含：

- `spec-library.dump`：七张属性表和完整 `product_categories` 表的 PostgreSQL custom-format 数据备份；脚本不会清空分类表。
- `manifest.json`：执行前行数、完整内容摘要、七张表摘要、完整分类表摘要、种子校验和和数据库版本。
- `receipt.json`：仅在回执写入成功时存在。提交后的独立核验通过时为 `committed_verified`；独立核验失败时脚本会尽力写入 `committed_unverified` 并以失败退出。已提交后若回执写入失败，文件可能缺失，脚本同样会以失败退出并要求停止重试。

备份长期保留，不作为任务临时文件清理。恢复前先在隔离数据库验证 dump 的表结构、行数、约束和业务摘要；不得直接把备份覆盖已有开发库、共享库或生产库。需要覆盖恢复时，先保全恢复目标的当前状态，再按 [数据库备份与恢复手册](database-backup-restore.md) 取得对应授权并执行。

隔离恢复库应先完成同版本迁移，并使用专用空库：`product_categories` 与七张属性表必须为空且不存在冲突记录。该 dump 仅含八张表的数据，不会清空恢复目标，也不会恢复 `products`、`product_skus` 或范围外表；不得在已有业务数据的库上执行。`spec-library.dump` 含恢复所需的完整分类表和七张属性表数据，可使用 `pg_restore --exit-on-error --single-transaction --data-only --no-owner --no-privileges --host <本机地址> --port <端口> --username <用户名> --dbname <隔离数据库> <备份目录>\spec-library.dump` 恢复。完成后分别核对 `manifest.json` 的 `tables_sha256`、`categories_sha256` 与行数；恢复目标必须保持隔离，不能直接覆盖已有开发库、共享库或生产库。

## 5. 新项目复用

同结构的新项目复制 `scripts/seed_spec_library.py` 与 `scripts/data/spec_library.v1.json`，并确认其模型、迁移版本、表名和数据库目标保护规则仍与脚本完全一致。任一项不同都应先改造并审查脚本，不能依赖自动猜测或绕过预检。

已存在商品、SKU、属性采用、订单历史或需要保留的分类模板时，不能使用本脚本的清空重建模式；应另建带映射、迁移窗口和恢复演练的数据迁移方案。
