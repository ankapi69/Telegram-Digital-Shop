"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(64)),
        sa.Column("full_name", sa.String(255)),
        sa.Column("locale", sa.String(8), nullable=False, server_default="ru"),
        sa.Column(
            "role",
            sa.Enum("user", "support", "manager", "superadmin",
                    name="userrole", native_enum=False, length=16),
            nullable=False, server_default="user",
        ),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_last_seen", "users", ["last_seen_at"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("parent_id", sa.Integer(),
                  sa.ForeignKey("categories.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.Integer(),
                  sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("photo_file_id", sa.String(256)),
        sa.Column(
            "delivery_type",
            sa.Enum("auto", "manual",
                    name="deliverytype", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_stock", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("price_stars", sa.Integer()),
        sa.Column("price_rub", sa.Numeric(12, 2)),
        sa.Column("price_usdt", sa.Numeric(20, 8)),
        sa.Column("manual_template", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_products_active", "products", ["is_active"])
    op.create_index("ix_products_category_id", "products", ["category_id"])

    op.create_table(
        "promos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "discount_type",
            sa.Enum("percent", "fixed",
                    name="promotype", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.String(16)),
        sa.Column("max_uses", sa.Integer()),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128)),
        sa.Column("payment_url", sa.Text()),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("discount_amount", sa.Numeric(20, 8),
                  nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("promo_code", sa.String(64)),
        sa.Column(
            "status",
            sa.Enum(
                "pending_payment", "awaiting_delivery",
                "delivered", "cancelled", "refunded",
                name="orderstatus", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("provider", "external_id",
                            name="uq_orders_provider_external"),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_paid_at", "orders", ["paid_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(),
                  sa.ForeignKey("products.id"), nullable=False),
        sa.Column("title_snapshot", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("delivered_content", sa.Text()),
        sa.Column(
            "status",
            sa.Enum("pending", "delivered",
                    name="orderitemstatus", native_enum=False, length=16),
            nullable=False, server_default="pending",
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    op.create_table(
        "stock_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer(),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_sold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_item_id", sa.Integer(),
                  sa.ForeignKey("order_items.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_stock_items_product_id", "stock_items", ["product_id"])
    op.create_index("ix_stock_available", "stock_items", ["product_id", "is_sold"])


def downgrade() -> None:
    op.drop_table("stock_items")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("promos")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("users")
