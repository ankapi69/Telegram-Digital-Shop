from aiogram import Dispatcher

from bot.config import Settings
from bot.filters.admin import AdminFilter
from bot.handlers import catalog, checkout, orders, start
from bot.handlers.admin import menu as admin_menu
from bot.handlers.admin import orders as admin_orders
from bot.handlers.admin import products as admin_products
from bot.handlers.admin import stock as admin_stock


def register(dp: Dispatcher, settings: Settings) -> None:
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(checkout.router)
    dp.include_router(orders.router)

    admin_filter = AdminFilter(set(settings.admin_ids))
    admin_routers = (
        admin_menu.router,
        admin_products.router,
        admin_stock.router,
        admin_orders.router,
    )
    for router in admin_routers:
        router.message.filter(admin_filter)
        router.callback_query.filter(admin_filter)
        dp.include_router(router)
