"""balance: wallets, ledger, order.kind, exchange rate

Revision ID: 0002_balance
Revises: 0001_initial
Create Date: 2025-01-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_balance"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wallets",
        sa.Column(
            "user_id", sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("balance", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delta", sa.Numeric(20, 2), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "topup", "purchase", "refund", "admin_adjust",
                name="ledgerkind", native_enum=False, length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "ref_order_id", sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
        ),
        sa.Column("ref_admin_id", sa.BigInteger()),
        sa.Column("comment", sa.String(256)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ledger_user_id", "ledger_entries", ["user_id"])
    op.create_index("ix_ledger_created_at", "ledger_entries", ["created_at"])

    op.add_column(
        "orders",
        sa.Column(
            "kind",
            sa.Enum(
                "purchase", "topup",
                name="orderkind", native_enum=False, length=16,
            ),
            nullable=False,
            server_default="purchase",
        ),
    )
    # For top-up orders priced in a non-USD currency (e.g. RUB invoice
    # via Lava): how much USD to credit the wallet after successful payment.
    op.add_column(
        "orders",
        sa.Column("credited_amount", sa.Numeric(20, 2)),
    )

    # Key-value store for runtime-tweakable settings (exchange rate etc.).
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(256), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("orders", "credited_amount")
    op.drop_column("orders", "kind")
    op.drop_index("ix_ledger_created_at", table_name="ledger_entries")
    op.drop_index("ix_ledger_user_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("wallets")
