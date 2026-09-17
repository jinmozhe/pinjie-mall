"""Create transaction foundation tables.

Revision ID: 20260917_02
Revises: 20260917_01
This revision is a frozen PostgreSQL DDL snapshot and never imports runtime models.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260917_02"
down_revision: str | None = "20260917_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE cart_items (user_id UUID NOT NULL, sku_id UUID NOT NULL, quantity INTEGER NOT NULL, selected BOOLEAN NOT NULL, revision INTEGER NOT NULL, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CONSTRAINT uq_cart_user_sku UNIQUE (user_id, sku_id), CONSTRAINT ck_cart_quantity CHECK (quantity BETWEEN 1 AND 999), CONSTRAINT ck_cart_revision CHECK (revision > 0), FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, FOREIGN KEY(sku_id) REFERENCES product_skus (id) ON DELETE RESTRICT)"
    )
    op.execute("COMMENT ON TABLE cart_items IS '用户购物车意图，不占用库存也不保存权威价格'")
    op.execute(
        "CREATE TABLE orders (user_id UUID NOT NULL, request_id UUID NOT NULL, request_hash VARCHAR(64) NOT NULL, quote_fingerprint VARCHAR(64) NOT NULL, product_type VARCHAR(16) NOT NULL, status VARCHAR(24) NOT NULL, currency VARCHAR(3) NOT NULL, items_amount NUMERIC(15, 2) NOT NULL, freight_amount NUMERIC(15, 2) NOT NULL, total_amount NUMERIC(15, 2) NOT NULL, address_snapshot JSONB, shipping_snapshot JSONB NOT NULL, pricing_version VARCHAR(32) NOT NULL, expires_at TIMESTAMP WITH TIME ZONE NOT NULL, paid_at TIMESTAMP WITH TIME ZONE, payment_reference VARCHAR(160), cancelled_at TIMESTAMP WITH TIME ZONE, cancel_reason VARCHAR(200), revision INTEGER NOT NULL, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CONSTRAINT uq_order_user_request UNIQUE (user_id, request_id), CONSTRAINT uq_orders_payment_reference UNIQUE (payment_reference), CONSTRAINT ck_order_status CHECK (status IN ('pending_payment', 'paid', 'cancelled')), CONSTRAINT ck_order_product_type CHECK (product_type IN ('physical', 'virtual')), CONSTRAINT ck_order_amounts CHECK (items_amount >= 0 AND freight_amount >= 0 AND total_amount = items_amount + freight_amount), CONSTRAINT ck_order_currency CHECK (currency = 'CNY'), CONSTRAINT ck_order_revision CHECK (revision > 0), CONSTRAINT ck_order_shipping_snapshot CHECK (jsonb_typeof(shipping_snapshot) = 'array'), CONSTRAINT ck_order_address_snapshot CHECK ((product_type = 'physical' AND address_snapshot IS NOT NULL AND jsonb_typeof(address_snapshot) = 'object') OR (product_type = 'virtual' AND address_snapshot IS NULL)), CONSTRAINT ck_order_paid_fact CHECK ((status = 'paid' AND paid_at IS NOT NULL AND payment_reference IS NOT NULL) OR (status <> 'paid' AND paid_at IS NULL AND payment_reference IS NULL)), CONSTRAINT ck_order_cancel_fact CHECK ((status = 'cancelled' AND cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL) OR (status <> 'cancelled' AND cancelled_at IS NULL AND cancel_reason IS NULL)), FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT)"
    )
    op.execute("CREATE INDEX ix_orders_user_created ON orders (user_id, created_at, id)")
    op.execute("CREATE INDEX ix_orders_expiry ON orders (expires_at, id) WHERE status = 'pending_payment'")
    op.execute("COMMENT ON TABLE orders IS '交易订单与不可变计价快照'")
    op.execute(
        "CREATE TABLE order_items (order_id UUID NOT NULL, product_id UUID NOT NULL, sku_id UUID NOT NULL, product_name VARCHAR(200) NOT NULL, sku_code VARCHAR(100) NOT NULL, specifications JSONB NOT NULL, quantity INTEGER NOT NULL, unit_price NUMERIC(15, 2) NOT NULL, line_amount NUMERIC(15, 2) NOT NULL, weight_grams INTEGER NOT NULL, product_revision INTEGER NOT NULL, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CONSTRAINT uq_order_item_sku UNIQUE (order_id, sku_id), CONSTRAINT ck_order_item_quantity CHECK (quantity BETWEEN 1 AND 999), CONSTRAINT ck_order_item_amount CHECK (unit_price >= 0 AND line_amount = unit_price * quantity), CONSTRAINT ck_order_item_specs CHECK (jsonb_typeof(specifications) = 'object'), FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT)"
    )
    op.execute("COMMENT ON TABLE order_items IS '订单明细快照，后续退款与评价的稳定标识'")
    op.execute(
        "CREATE TABLE order_events (order_id UUID NOT NULL, revision INTEGER NOT NULL, from_status VARCHAR(24), to_status VARCHAR(24) NOT NULL, actor_type VARCHAR(16) NOT NULL, actor_id UUID, reason VARCHAR(200) NOT NULL, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CONSTRAINT uq_order_event_revision UNIQUE (order_id, revision), CONSTRAINT ck_order_event_actor CHECK (actor_type IN ('user', 'system', 'payment')), CONSTRAINT ck_order_event_status CHECK (to_status IN ('pending_payment', 'paid', 'cancelled')), FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT)"
    )
    op.execute("COMMENT ON TABLE order_events IS '订单状态变更事实，与订单和库存同事务写入'")
    op.execute(
        "CREATE TABLE inventory_reservations (order_id UUID NOT NULL, sku_id UUID NOT NULL, quantity INTEGER NOT NULL, status VARCHAR(16) NOT NULL, revision INTEGER NOT NULL, released_at TIMESTAMP WITH TIME ZONE, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CONSTRAINT uq_inventory_reservation_order_sku UNIQUE (order_id, sku_id), CONSTRAINT ck_inventory_reservation_quantity CHECK (quantity BETWEEN 1 AND 999), CONSTRAINT ck_inventory_reservation_status CHECK (status IN ('reserved', 'confirmed', 'released')), FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT, FOREIGN KEY(sku_id) REFERENCES product_skus (id) ON DELETE RESTRICT)"
    )
    op.execute("CREATE INDEX ix_inventory_reservations_order_id ON inventory_reservations (order_id)")
    op.execute("COMMENT ON TABLE inventory_reservations IS '订单库存占用事实与幂等状态'")


def downgrade() -> None:
    raise RuntimeError("交易表包含订单和库存占用事实，禁止自动删表降级；请使用备份恢复或前向修复。")
