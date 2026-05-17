from aiogram.fsm.state import State, StatesGroup


class ProductCreate(StatesGroup):
    title = State()
    description = State()
    price = State()
    delivery_type = State()


class ProductEdit(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_price = State()


class StockAdd(StatesGroup):
    waiting_items = State()


class ManualFulfill(StatesGroup):
    waiting_content = State()
