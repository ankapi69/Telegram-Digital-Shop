# Telegram Digital Shop

Production-ready Telegram-бот для продажи цифровых товаров (аккаунты,
активационные ссылки). Слоистая архитектура, async-everything,
PostgreSQL + Redis, подключаемые платёжные провайдеры.

## Возможности

**Каталог**
- Категории → подкатегории (2 уровня) с CRUD прямо в боте.
- Фото товара, описание, цена в любой валюте.
- Загрузка единиц выдачи через CSV-файл **или** массовый текст.
- Показ остатка покупателю (можно скрыть).
- Авто- и ручная выдача в одном заказе.

**Покупка**
- Корзина с несколькими позициями (Redis с TTL).
- Промокоды: % и фикс, лимит использований, привязка к валюте.
- Платёжные провайдеры (см. ниже), оба способа подтверждения:
  webhook + кнопка «Проверить оплату».
- История заказов с inline-пагинацией.
- Авто-чек после оплаты.

**Поддержка**
- Кнопка «Поддержка» в главном меню.
- Сообщения пользователя пересылаются в группу `SUPPORT_GROUP_ID`.
- Ответ менеджера в группе (Reply) автоматически уходит пользователю.

**Админ-панель**
- Роли `superadmin / manager / support`.
- Уведомления о новых заказах и запросах ручной выдачи → `NOTIFY_GROUP_ID`.
- Статистика: выручка по дням, топ товаров, DAU, баны.
- Рассылка: текст + фото + inline-кнопка, throttled rate limiter.
- Блокировка пользователей, поиск по ID/`@username`.

**Под капотом**
- Async SQLAlchemy 2 + asyncpg, индексы, connection pool.
- Alembic-миграции (запускаются автоматом при старте).
- Redis: FSM, корзина, кеш каталога, ретеншн support-replies.
- Compare-and-swap резервация склада (race-free на любых СУБД).
- Idempotent fulfillment: webhook + кнопка не могут продублировать выдачу.
- Loguru, throttling, graceful shutdown.

## Платёжные провайдеры

| Код         | Валюта  | Webhook | Ручная проверка |
| ----------- | ------- | :-----: | :-------------: |
| `stars`     | XTR     | –       | – *(нативно)*   |
| `cryptobot` | любой*  | ✔       | ✔               |
| `lava`      | RUB     | ✔       | ✔               |

\* CryptoBot: `CRYPTOBOT_ASSET` задаёт актив (USDT/TON/BTC/…).

Добавить новую платёжку — один файл `bot/payments/<name>.py`,
наследник `PaymentProvider`. Зарегистрировать в
`bot.payments.registry.build_registry()` и добавить колонку цены в
`Product` + миграцию.

## Запуск

### Docker (рекомендуется)

```bash
cp .env.example .env
# открой .env, поставь BOT_TOKEN и SUPERADMIN_IDS
docker compose up -d --build
```

Compose поднимает Postgres + Redis + бота. Миграции применяются
автоматически при старте контейнера.

### Локально (dev)

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bot
```

При локальной разработке без Postgres достаточно поменять
`DATABASE_URL=sqlite+aiosqlite:///./shop.db` — Alembic-миграции
сработают и на SQLite.

## Структура

```
bot/
├── handlers/
│   ├── user/        start, catalog, cart, checkout, orders, support
│   └── admin/       menu, products, categories, stock, orders,
│                    promo, stats, broadcast, users
├── services/        cart, catalog, checkout, promo, stats,
│                    broadcast, notifier, support, cache
├── payments/        base, registry, fulfillment, stars,
│                    cryptobot, lava + webhook.py
├── repositories/    user, category, product, stock, order,
│                    promo, stats
├── database/        models.py (все ORM-модели), engine.py
├── middlewares/     db, throttling, user_context, i18n
├── keyboards/       user.py, admin.py
├── filters/         admin.py (RoleFilter, SupportGroupFilter)
├── states/          admin.py (FSM-группы)
├── locales/         ru.py + translate()
└── utils/           logging (loguru), money, csv_import, pagination
migrations/          Alembic
```

## Конфигурация

| Переменная                | Назначение                                              |
| ------------------------- | ------------------------------------------------------- |
| `BOT_TOKEN`               | Токен от @BotFather                                     |
| `SUPERADMIN_IDS`          | Полный доступ                                           |
| `MANAGER_IDS`             | Каталог, склад, заказы                                  |
| `SUPPORT_IDS`             | Поддержка, пользователи                                 |
| `DATABASE_URL`            | postgres / sqlite                                       |
| `REDIS_URL`               | Redis (FSM + корзина + кеш + support replies)           |
| `NOTIFY_GROUP_ID`         | Группа уведомлений (новые заказы, ручная выдача)        |
| `SUPPORT_GROUP_ID`        | Группа поддержки (форвард-в, reply-обратно)             |
| `WEBHOOK_*`               | aiohttp-сервер для платёжных webhook'ов                 |
| `CRYPTOBOT_*` / `LAVA_*`  | Ключи платёжек                                          |
| `CATALOG_CACHE_TTL`       | TTL кеша каталога (сек)                                 |
| `CART_TTL_SECONDS`        | Сколько живёт корзина в Redis                           |
| `BROADCAST_RATE_PER_SEC`  | Ограничение скорости рассылки                           |

## Команды

- `/start` — главное меню (каталог, корзина, заказы, поддержка).
- `/admin` — админ-панель (по ролям).
