STRINGS: dict[str, str] = {
    # Common
    "back": "« Назад",
    "to_menu": "« В меню",
    "cancel": "✖ Отмена",
    "skip": "Пропустить",
    "yes": "Да",
    "no": "Нет",
    "loading": "Минутку…",
    "banned": "Вы заблокированы.",
    # Main menu
    "menu_title": "🛒 <b>Главное меню</b>\n\nВыберите раздел:",
    "btn_catalog": "🛍 Каталог",
    "btn_cart": "🧺 Корзина",
    "btn_orders": "📦 Мои заказы",
    "btn_support": "🆘 Поддержка",
    # Catalog
    "catalog_empty": "Каталог пока пуст. Загляните позже.",
    "catalog_title": "🛍 <b>Каталог</b>\n\nВыберите категорию:",
    "subcatalog_title": "🛍 <b>{name}</b>\n\nВыберите подкатегорию или товар:",
    "no_providers": "⛔️ Способы оплаты не настроены",
    "out_of_stock": "Товар закончился",
    "stock_left": "📦 В наличии: <b>{n}</b>",
    "manual_delivery_note": "📨 Выдаётся вручную после оплаты",
    "prices_label": "💰 Способы оплаты:",
    # Cart
    "cart_empty": "🧺 Корзина пуста.\n\nЗайдите в каталог и добавьте товары.",
    "cart_title": "🧺 <b>Корзина</b>",
    "cart_total": "Итого: <b>{amount}</b>",
    "cart_promo_active": "Промокод <code>{code}</code>: −{discount}",
    "cart_promo_invalid": "Промокод не подходит",
    "cart_promo_applied": "Промокод применён",
    "cart_promo_prompt": "Введите промокод (или /cancel):",
    "cart_added": "✅ Добавлено в корзину",
    "cart_removed": "Удалено",
    "cart_cleared": "Корзина очищена",
    "cart_mixed_currency": "В корзине товары с разными валютами — оформляйте раздельно.",
    "cart_pick_provider": "Выберите способ оплаты:",
    "cart_pick_currency_first": "Выберите валюту для оформления:",
    # Checkout
    "checkout_invoice": (
        "🧾 <b>Счёт #{order_id}</b>\n\n"
        "{items}\n\n"
        "Сумма: <b>{total}</b>{discount_line}\n"
        "Способ: {provider}\n\n"
        "Откройте ссылку, оплатите, затем нажмите «Проверить оплату»."
    ),
    "discount_line": "\nСкидка: −{discount}",
    "btn_pay": "💳 Оплатить",
    "btn_check": "🔄 Проверить оплату",
    "btn_apply_promo": "🏷 Применить промокод",
    "btn_remove_promo": "🗑 Убрать промокод",
    "btn_cancel_invoice": "✖ Отменить",
    "paid_inline_sent": "Счёт отправлен в чат",
    "paid_already": "Уже выдан ✅",
    "paid_awaiting": "Оплата получена, ждите ручную выдачу.",
    "paid_not_yet": "Оплата пока не поступила. Попробуйте ещё раз.",
    "paid_expired": "Счёт {status}",
    "invoice_cancelled": "Счёт отменён",
    "invoice_provider_off": "Способ оплаты отключён",
    "invoice_create_failed": "Не удалось создать счёт. Попробуйте позже.",
    "stock_vanished_user": "⚠️ Оплата получена, но товар закончился. Администратор свяжется с вами.",
    "receipt": (
        "🧾 <b>Чек по заказу #{order_id}</b>\n"
        "Дата: {date}\n"
        "Сумма: <b>{total}</b>\n"
        "Способ оплаты: {provider}\n\n"
        "{items}"
    ),
    # Orders
    "orders_empty": "У вас пока нет заказов.",
    "orders_title": "📦 <b>Ваши заказы</b>",
    "order_line": "#{id} • {title} • {amount} • <i>{status}</i>",
    "order_page": "Страница {page}/{pages}",
    "status_pending_payment": "ожидает оплаты",
    "status_awaiting_delivery": "ожидает выдачи",
    "status_delivered": "выдан",
    "status_cancelled": "отменён",
    "status_refunded": "возвращён",
    # Support
    "support_disabled": "Чат поддержки временно недоступен.",
    "support_prompt": "Опишите вопрос одним сообщением — оператор ответит здесь же.",
    "support_sent": "✅ Сообщение передано в поддержку. Ожидайте ответ.",
    "support_reply_header": "💬 <b>Ответ поддержки</b>",
    "support_reply_help": "Ответьте на пересланное сообщение — текст пойдёт пользователю.",
    "support_reply_ok": "Доставлено",
    "support_reply_fail": "Не удалось отправить пользователю.",
    # Admin
    "admin_menu": "🛠 <b>Админ-панель</b>",
    "admin_no_access": "Нет доступа",
}
