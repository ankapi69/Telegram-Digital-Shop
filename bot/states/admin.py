from aiogram.fsm.state import State, StatesGroup


class ProductCreate(StatesGroup):
    title = State()
    description = State()
    delivery_type = State()


class ProductEdit(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_photo = State()
    waiting_price_stars = State()
    waiting_price_rub = State()
    waiting_price_usdt = State()
    waiting_manual_template = State()


class StockAdd(StatesGroup):
    waiting_items = State()


class ManualFulfill(StatesGroup):
    waiting_content = State()


class CategoryCreate(StatesGroup):
    name = State()


class CategoryEdit(StatesGroup):
    rename = State()
    sub_name = State()


class PromoCreate(StatesGroup):
    code = State()
    discount_type = State()
    value = State()
    currency = State()
    max_uses = State()


class Broadcast(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    waiting_button = State()
    confirm = State()


class UserSearch(StatesGroup):
    query = State()


class CartPromo(StatesGroup):
    waiting_code = State()


class Support(StatesGroup):
    waiting_message = State()


class AdminBalanceAdjust(StatesGroup):
    target = State()         # used by the standalone "by ID" entry-point
    amount = State()
    comment = State()


class AdminUserSearchForBalance(StatesGroup):
    query = State()
