from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DeliveryType(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    AWAITING_DELIVERY = "awaiting_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderItemStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"


class OrderKind(str, enum.Enum):
    PURCHASE = "purchase"
    TOPUP = "topup"


class LedgerKind(str, enum.Enum):
    TOPUP = "topup"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADMIN_ADJUST = "admin_adjust"


class PromoType(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class UserRole(str, enum.Enum):
    USER = "user"
    SUPPORT = "support"
    MANAGER = "manager"
    SUPERADMIN = "superadmin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16),
        default=UserRole.USER,
        nullable=False,
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_users_last_seen", "last_seen_at"),)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parent: Mapped["Category | None"] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    photo_file_id: Mapped[str | None] = mapped_column(String(256))
    delivery_type: Mapped[DeliveryType] = mapped_column(
        Enum(DeliveryType, native_enum=False, length=16), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Per-currency prices. ``None`` hides the product from that provider.
    price_stars: Mapped[int | None] = mapped_column(Integer)
    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_usdt: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))

    # Manual-delivery products have no auto stock pool but admin can pin a
    # default content (e.g. a stock notice) that goes out automatically.
    manual_template: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock_items: Mapped[list["StockItem"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_products_active", "is_active"),)


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="stock_items")

    __table_args__ = (Index("ix_stock_available", "product_id", "is_sold"),)


class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    discount_type: Mapped[PromoType] = mapped_column(
        Enum(PromoType, native_enum=False, length=16), nullable=False
    )
    # PERCENT → 0..100; FIXED → currency-agnostic decimal applied to total
    # when invoice currency matches ``currency`` (or any currency when null).
    value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(16))
    max_uses: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    payment_url: Mapped[str | None] = mapped_column(Text)

    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    promo_code: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, length=32), nullable=False
    )
    kind: Mapped[OrderKind] = mapped_column(
        Enum(OrderKind, native_enum=False, length=16),
        default=OrderKind.PURCHASE,
        nullable=False,
    )
    # For TOPUP orders priced in non-USD currency (Lava in RUB): how much
    # USD will be credited to the wallet on successful payment.
    credited_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )

    __table_args__ = (
        Index("ix_orders_status", "status"),
        Index("ix_orders_paid_at", "paid_at"),
        UniqueConstraint("provider", "external_id", name="uq_orders_provider_external"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    title_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    delivered_content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OrderItemStatus] = mapped_column(
        Enum(OrderItemStatus, native_enum=False, length=16),
        default=OrderItemStatus.PENDING,
        nullable=False,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="items")


class Wallet(Base):
    __tablename__ = "wallets"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), default=Decimal("0"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    # Integer PK so SQLite gets a working autoincrement; on Postgres
    # this is still 32-bit but ledger volume in a typical shop never
    # gets close.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delta: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    kind: Mapped[LedgerKind] = mapped_column(
        Enum(LedgerKind, native_enum=False, length=16), nullable=False
    )
    ref_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL")
    )
    ref_admin_id: Mapped[int | None] = mapped_column(BigInteger)
    comment: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
