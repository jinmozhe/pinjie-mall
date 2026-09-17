"""Create commerce foundation tables.

Revision ID: 20260917_01
Revises: 20260829_01
This revision contains a frozen PostgreSQL DDL snapshot; it never imports runtime models.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260917_01"
down_revision: str | None = "20260829_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE shipping_templates (\n\tname VARCHAR(100) NOT NULL, \n\tpricing_method VARCHAR(10) NOT NULL, \n\tregions JSONB NOT NULL, \n\tfree_shipping_threshold NUMERIC(15, 2), \n\texcluded_provinces JSONB NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\trevision INTEGER NOT NULL, \n\tupdated_by_id UUID NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_shipping_pricing_method CHECK (pricing_method IN ('piece', 'weight')), \n\tCONSTRAINT ck_shipping_revision CHECK (revision > 0), \n\tCONSTRAINT ck_shipping_threshold CHECK (free_shipping_threshold IS NULL OR free_shipping_threshold >= 0), \n\tCONSTRAINT ck_shipping_regions CHECK (jsonb_typeof(regions) = 'array'), \n\tCONSTRAINT ck_shipping_exclusions CHECK (jsonb_typeof(excluded_provinces) = 'array')\n)"
    )
    op.execute("COMMENT ON TABLE shipping_templates IS '运费模板与确定性地区计费规则'")
    op.execute("COMMENT ON COLUMN shipping_templates.name IS '模板名称'")
    op.execute("COMMENT ON COLUMN shipping_templates.pricing_method IS 'piece 按件，weight 按克'")
    op.execute("COMMENT ON COLUMN shipping_templates.regions IS '地区及默认计费规则'")
    op.execute("COMMENT ON COLUMN shipping_templates.free_shipping_threshold IS '包邮商品金额门槛'")
    op.execute("COMMENT ON COLUMN shipping_templates.excluded_provinces IS '不参与满额包邮的省份'")
    op.execute("COMMENT ON COLUMN shipping_templates.is_active IS '是否允许新商品绑定和结算'")
    op.execute("COMMENT ON COLUMN shipping_templates.revision IS '编辑版本'")
    op.execute("COMMENT ON COLUMN shipping_templates.updated_by_id IS '最后操作管理员 ID'")
    op.execute(
        "CREATE TABLE product_categories (\n\tname VARCHAR(100) NOT NULL, \n\tparent_id UUID, \n\tsort_order INTEGER NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\trevision INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_product_category_parent CHECK (parent_id IS NULL OR parent_id <> id), \n\tCONSTRAINT ck_product_category_revision CHECK (revision > 0), \n\tFOREIGN KEY(parent_id) REFERENCES product_categories (id) ON DELETE RESTRICT\n)"
    )
    op.execute("CREATE INDEX ix_product_categories_parent_id ON product_categories (parent_id)")
    op.execute("COMMENT ON TABLE product_categories IS '商品三级分类'")
    op.execute("COMMENT ON COLUMN product_categories.name IS '分类名称'")
    op.execute("COMMENT ON COLUMN product_categories.parent_id IS '父分类 ID'")
    op.execute("COMMENT ON COLUMN product_categories.sort_order IS '排序值'")
    op.execute("COMMENT ON COLUMN product_categories.is_active IS '分类启用状态'")
    op.execute("COMMENT ON COLUMN product_categories.revision IS '编辑版本'")
    op.execute(
        "CREATE TABLE products (\n\tname VARCHAR(200) NOT NULL, \n\tdescription TEXT NOT NULL, \n\tproduct_type VARCHAR(16) NOT NULL, \n\tcategory_id UUID NOT NULL, \n\tshipping_template_id UUID, \n\tstatus VARCHAR(16) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_products_type CHECK (product_type IN ('physical', 'virtual')), \n\tCONSTRAINT ck_products_status CHECK (status IN ('draft', 'on_sale', 'off_sale')), \n\tCONSTRAINT ck_products_revision CHECK (revision > 0), \n\tFOREIGN KEY(category_id) REFERENCES product_categories (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(shipping_template_id) REFERENCES shipping_templates (id) ON DELETE RESTRICT\n)"
    )
    op.execute("CREATE INDEX ix_products_category_id ON products (category_id)")
    op.execute("CREATE INDEX ix_products_shipping_template_id ON products (shipping_template_id)")
    op.execute("CREATE INDEX ix_products_status_created ON products (status, created_at)")
    op.execute("COMMENT ON TABLE products IS '商品 SPU 资料，不保存库存'")
    op.execute("COMMENT ON COLUMN products.name IS '商品名称'")
    op.execute("COMMENT ON COLUMN products.description IS '商品纯文本说明'")
    op.execute("COMMENT ON COLUMN products.product_type IS '实物或虚拟商品'")
    op.execute("COMMENT ON COLUMN products.category_id IS '商品分类 ID'")
    op.execute("COMMENT ON COLUMN products.shipping_template_id IS '运费模板，虚拟商品为空'")
    op.execute("COMMENT ON COLUMN products.status IS '草稿、上架或下架'")
    op.execute("COMMENT ON COLUMN products.revision IS '商品及变体的编辑版本'")
    op.execute(
        "CREATE TABLE product_skus (\n\tproduct_id UUID NOT NULL, \n\tcode VARCHAR(100) NOT NULL, \n\tspecifications JSONB NOT NULL, \n\tprice NUMERIC(15, 2) NOT NULL, \n\tweight_grams INTEGER NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_product_skus_price CHECK (price >= 0), \n\tCONSTRAINT ck_product_skus_weight CHECK (weight_grams >= 0), \n\tCONSTRAINT ck_product_skus_specifications CHECK (jsonb_typeof(specifications) = 'object'), \n\tCONSTRAINT uq_product_sku_specifications UNIQUE (product_id, specifications), \n\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, \n\tUNIQUE (code)\n)"
    )
    op.execute("CREATE INDEX ix_product_skus_product_id ON product_skus (product_id)")
    op.execute("COMMENT ON TABLE product_skus IS '稳定商品变体，不删除重建'")
    op.execute("COMMENT ON COLUMN product_skus.product_id IS '所属商品 ID'")
    op.execute("COMMENT ON COLUMN product_skus.code IS '全局唯一 SKU 编码'")
    op.execute("COMMENT ON COLUMN product_skus.specifications IS '规格组合，无规格为空对象'")
    op.execute("COMMENT ON COLUMN product_skus.price IS '基础售价人民币元'")
    op.execute("COMMENT ON COLUMN product_skus.weight_grams IS '实物重量克数'")
    op.execute("COMMENT ON COLUMN product_skus.is_active IS '变体是否启用'")
    op.execute(
        "CREATE TABLE product_images (\n\tproduct_id UUID NOT NULL, \n\tasset_id UUID NOT NULL, \n\tposition INTEGER NOT NULL, \n\tPRIMARY KEY (product_id, asset_id), \n\tCONSTRAINT uq_product_image_position UNIQUE (product_id, position), \n\tCONSTRAINT ck_product_image_position CHECK (position >= 0), \n\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE RESTRICT\n)"
    )
    op.execute("COMMENT ON TABLE product_images IS '商品图片资产引用，首张为主图'")
    op.execute("COMMENT ON COLUMN product_images.product_id IS '所属商品'")
    op.execute("COMMENT ON COLUMN product_images.asset_id IS '引用图片资产'")
    op.execute("COMMENT ON COLUMN product_images.position IS '图片排序'")
    op.execute(
        "CREATE TABLE inventory_accounts (\n\tsku_id UUID NOT NULL, \n\tavailable INTEGER NOT NULL, \n\treserved INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_inventory_quantities CHECK (available >= 0 AND reserved >= 0), \n\tCONSTRAINT ck_inventory_revision CHECK (revision > 0), \n\tUNIQUE (sku_id), \n\tFOREIGN KEY(sku_id) REFERENCES product_skus (id) ON DELETE RESTRICT\n)"
    )
    op.execute("COMMENT ON TABLE inventory_accounts IS 'SKU 库存账户，独立于商品资料'")
    op.execute("COMMENT ON COLUMN inventory_accounts.sku_id IS '稳定 SKU ID'")
    op.execute("COMMENT ON COLUMN inventory_accounts.available IS '可售数量'")
    op.execute("COMMENT ON COLUMN inventory_accounts.reserved IS '订单占用数量'")
    op.execute("COMMENT ON COLUMN inventory_accounts.revision IS '库存版本'")
    op.execute(
        "CREATE TABLE inventory_movements (\n\tsku_id UUID NOT NULL, \n\trequest_id UUID NOT NULL, \n\tactor_id UUID NOT NULL, \n\tquantity_delta INTEGER NOT NULL, \n\tbefore_available INTEGER NOT NULL, \n\tafter_available INTEGER NOT NULL, \n\texpected_revision INTEGER NOT NULL, \n\tresulting_revision INTEGER NOT NULL, \n\treason VARCHAR(200) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_inventory_movement_request UNIQUE (sku_id, request_id), \n\tCONSTRAINT ck_inventory_delta CHECK (quantity_delta <> 0), \n\tCONSTRAINT ck_inventory_movement_balance CHECK (before_available >= 0 AND after_available >= 0), \n\tCONSTRAINT ck_inventory_movement_equation CHECK (after_available = before_available + quantity_delta), \n\tFOREIGN KEY(sku_id) REFERENCES product_skus (id) ON DELETE RESTRICT\n)"
    )
    op.execute("CREATE INDEX ix_inventory_movements_sku_id ON inventory_movements (sku_id)")
    op.execute("COMMENT ON TABLE inventory_movements IS '不可变人工库存调整流水与幂等结果'")
    op.execute("COMMENT ON COLUMN inventory_movements.sku_id IS '变动 SKU ID'")
    op.execute("COMMENT ON COLUMN inventory_movements.request_id IS '调用方业务幂等号，同 SKU 内唯一'")
    op.execute("COMMENT ON COLUMN inventory_movements.actor_id IS '操作管理员 ID'")
    op.execute("COMMENT ON COLUMN inventory_movements.quantity_delta IS '增减数量'")
    op.execute("COMMENT ON COLUMN inventory_movements.before_available IS '变动前可售库存'")
    op.execute("COMMENT ON COLUMN inventory_movements.after_available IS '变动后可售库存'")
    op.execute("COMMENT ON COLUMN inventory_movements.expected_revision IS '原请求期望版本'")
    op.execute("COMMENT ON COLUMN inventory_movements.resulting_revision IS '完成后的库存版本'")
    op.execute("COMMENT ON COLUMN inventory_movements.reason IS '调整原因'")
    op.execute(
        "CREATE TABLE user_addresses (\n\tuser_id UUID NOT NULL, \n\treceiver_name VARCHAR(100) NOT NULL, \n\tmobile VARCHAR(32) NOT NULL, \n\tprovince_code VARCHAR(6) NOT NULL, \n\tcity_code VARCHAR(6) NOT NULL, \n\tdistrict_code VARCHAR(6) NOT NULL, \n\tprovince VARCHAR(100) NOT NULL, \n\tcity VARCHAR(100) NOT NULL, \n\tdistrict VARCHAR(100) NOT NULL, \n\tstreet_address VARCHAR(300) NOT NULL, \n\tis_default BOOLEAN NOT NULL, \n\trevision INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_address_revision CHECK (revision > 0), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT\n)"
    )
    op.execute("CREATE INDEX ix_user_addresses_user_created ON user_addresses (user_id, created_at)")
    op.execute("CREATE UNIQUE INDEX uq_user_address_default ON user_addresses (user_id) WHERE is_default")
    op.execute("COMMENT ON TABLE user_addresses IS '用户收货地址，订单另存独立快照'")
    op.execute("COMMENT ON COLUMN user_addresses.user_id IS '所属用户 ID'")
    op.execute("COMMENT ON COLUMN user_addresses.receiver_name IS '收件人姓名'")
    op.execute("COMMENT ON COLUMN user_addresses.mobile IS '收件联系电话'")
    op.execute("COMMENT ON COLUMN user_addresses.province_code IS '省份行政编码'")
    op.execute("COMMENT ON COLUMN user_addresses.city_code IS '城市行政编码'")
    op.execute("COMMENT ON COLUMN user_addresses.district_code IS '区县行政编码'")
    op.execute("COMMENT ON COLUMN user_addresses.province IS '省份名称'")
    op.execute("COMMENT ON COLUMN user_addresses.city IS '城市名称'")
    op.execute("COMMENT ON COLUMN user_addresses.district IS '区县名称'")
    op.execute("COMMENT ON COLUMN user_addresses.street_address IS '详细地址'")
    op.execute("COMMENT ON COLUMN user_addresses.is_default IS '是否默认地址'")
    op.execute("COMMENT ON COLUMN user_addresses.revision IS '编辑版本'")


def downgrade() -> None:
    raise RuntimeError("商城业务表可能包含库存流水和地址数据，禁止自动删表降级；请按经审查的备份恢复或前向修复方案处理")
