from __future__ import annotations

from aiogram import Dispatcher, Router

from bot.config import Settings
from bot.database.models import UserRole
from bot.filters.admin import RoleFilter
from bot.handlers.admin import (
    balance as admin_balance,
    broadcast as admin_broadcast,
    categories as admin_categories,
    menu as admin_menu,
    orders as admin_orders,
    products as admin_products,
    promo as admin_promo,
    rates as admin_rates,
    stats as admin_stats,
    stock as admin_stock,
    users as admin_users,
)
from bot.handlers.user import (
    balance as user_balance,
    cart as user_cart,
    catalog as user_catalog,
    checkout as user_checkout,
    orders as user_orders,
    start as user_start,
    support as user_support,
)


def _admin(router: Router, min_role: UserRole) -> Router:
    flt = RoleFilter(min_role)
    router.message.filter(flt)
    router.callback_query.filter(flt)
    return router


def register(dp: Dispatcher, settings: Settings) -> None:
    # Support group reply listener (placed first, scoped by chat id filter)
    dp.include_router(user_support.make_group_router(settings))

    # User-facing
    for r in (
        user_start.router,
        user_catalog.router,
        user_cart.router,
        user_balance.router,
        user_checkout.router,
        user_orders.router,
        user_support.router,
    ):
        dp.include_router(r)

    # Admin
    dp.include_router(_admin(admin_menu.router, UserRole.SUPPORT))
    dp.include_router(_admin(admin_products.router, UserRole.MANAGER))
    dp.include_router(_admin(admin_categories.router, UserRole.MANAGER))
    dp.include_router(_admin(admin_stock.router, UserRole.MANAGER))
    dp.include_router(_admin(admin_orders.router, UserRole.MANAGER))
    dp.include_router(_admin(admin_promo.router, UserRole.SUPERADMIN))
    dp.include_router(_admin(admin_stats.router, UserRole.SUPERADMIN))
    dp.include_router(_admin(admin_broadcast.router, UserRole.SUPERADMIN))
    dp.include_router(_admin(admin_balance.router, UserRole.MANAGER))
    dp.include_router(_admin(admin_rates.router, UserRole.SUPERADMIN))
    dp.include_router(_admin(admin_users.router, UserRole.SUPPORT))
