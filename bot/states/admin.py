from aiogram.fsm.state import State, StatesGroup


class ProductCreate(StatesGroup):
    title = State()
    description = State()
    delivery_type = State()


class ProductEdit(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_price_stars = State()
    waiting_price_rub = State()
    waiting_price_usdt = State()


class StockAdd(StatesGroup):
    waiting_items = State()


class ManualFulfill(StatesGroup):
    waiting_content = State()
