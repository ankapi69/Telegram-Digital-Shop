# Telegram Digital Shop

Простой Telegram-бот для продажи цифровых товаров (активационные ссылки,
аккаунты, ключи) с подключаемыми платёжными провайдерами.

## Возможности

- Каталог товаров с описанием и **отдельной ценой на каждую валюту**.
- Два типа выдачи:
  - **Авто** — товар хранится списком (склад) и выдаётся в момент оплаты.
  - **Ручная** — после оплаты заказ попадает в очередь, админ присылает
    содержимое из админ-панели.
- Платежи через подключаемых провайдеров. Каждый продаёт в своей валюте,
  у товара может быть произвольный набор цен.
- Подтверждение оплаты двумя способами: **вебхук** (если настроен) и
  кнопка **«Проверить оплату»** в чате с ботом.
- Защита от спама, идемпотентная выдача заказов под параллельным
  webhook + кнопкой, атомарная резервация склада (CAS-update,
  работает на SQLite и Postgres).

## Поддерживаемые платёжки

| Код          | Валюта     | Webhook | Ручная проверка | Где взять токены                       |
| ------------ | ---------- | :-----: | :-------------: | -------------------------------------- |
| `stars`      | XTR (Stars)| –       | – *(нативно)*   | Только `BOT_TOKEN`                     |
| `cryptobot`  | любая*     | ✔       | ✔               | `@CryptoBot` → Crypto Pay → Create App |
| `lava`       | RUB        | ✔       | ✔               | lava.ru → Кабинет → API                |

*CryptoBot: `CRYPTOBOT_ASSET` задаёт актив (USDT/TON/BTC/…).
Stars подтверждаются Telegram'ом автоматически, отдельная проверка не нужна.

## Подключить новую платёжку

Добавить файл `bot/payments/<name>.py`, унаследовать
`PaymentProvider`, реализовать четыре метода:

```python
class MyProvider(PaymentProvider):
    code = "myprov"
    display_name = "MyProv"

    def __init__(self, ...):
        self.currency = "EUR"
        ...

    def price_for(self, product) -> Decimal | None:
        return product.price_eur          # добавьте свою колонку в Product

    async def create_invoice(self, *, bot, order, product, user) -> InvoiceResult: ...
    async def verify(self, order) -> PaymentStatus: ...
    async def parse_webhook(self, headers, body) -> WebhookEvent | None: ...  # опц.
```

Прописать конфиг в `Settings`, зарегистрировать в
`build_registry()` — и провайдер появится в кнопках карточки товара.

## Стек

- Python 3.11+, `aiogram` 3.x
- `SQLAlchemy` 2 (async) + `aiosqlite` (dev) / `asyncpg` (prod)
- `aiohttp` (вебхук-сервер), `pydantic-settings`, `structlog`
- Опционально Redis для FSM (`RedisStorage`)

## Запуск (локально, SQLite)

```bash
cp .env.example .env
# открой .env, поставь BOT_TOKEN и свой ADMIN_IDS,
# при желании — токены платёжек.
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bot
```

## Запуск в Docker (Postgres + Redis)

```bash
cp .env.example .env
docker compose up -d --build
```

`docker-compose.yml` уже переопределяет `DATABASE_URL` и `REDIS_URL` для
сервисов `db` и `redis`. Если включены вебхуки, открой `WEBHOOK_PORT`
наружу (или поставь nginx перед сервисом).

## Конфигурация

| Переменная             | Назначение                                                |
| ---------------------- | --------------------------------------------------------- |
| `BOT_TOKEN`            | Токен от @BotFather                                       |
| `ADMIN_IDS`            | ID админов через запятую                                  |
| `DATABASE_URL`         | SQLAlchemy URL (sqlite/postgres)                          |
| `REDIS_URL`            | Redis для FSM                                             |
| `THROTTLE_RATE`        | Минимум секунд между апдейтами от пользователя            |
| `LOG_LEVEL`            | `DEBUG` / `INFO` / `WARNING` / `ERROR`                    |
| `WEBHOOK_ENABLED`      | `true` чтобы поднять aiohttp-сервер для платёжных хуков   |
| `WEBHOOK_HOST/PORT`    | Где слушает aiohttp                                       |
| `WEBHOOK_PUBLIC_URL`   | Куда могут прийти провайдеры (за TLS-прокси)              |
| `WEBHOOK_BASE_PATH`    | Префикс пути (по умолчанию `/payments`)                   |
| `CRYPTOBOT_TOKEN/ASSET/TESTNET` | Crypto Pay                                       |
| `LAVA_SECRET_KEY/SHOP_ID` | Lava.ru Business                                       |
| `LAVA_SUCCESS_URL/FAIL_URL` | Возврат пользователя после оплаты Lava               |

## Команды

- `/start` — главное меню (каталог, мои заказы).
- `/admin` — админ-панель (только для `ADMIN_IDS`).

## Архитектура платежей

```
bot/payments/
├── base.py          # ABC + dataclasses (InvoiceResult, WebhookEvent, PaymentStatus)
├── registry.py      # build_registry() — собирает провайдеров из настроек
├── fulfillment.py   # fulfill_paid_order() — идемпотентная выдача
├── stars.py         # Telegram Stars (XTR)
├── cryptobot.py     # CryptoBot Crypto Pay API
└── lava.py          # Lava.ru Business API

bot/webhook.py       # aiohttp /payments/<code> для каждой платёжки
```

Заказ хранит `(provider, external_id)` — по этому ключу ищется при
вебхуке и при ручной проверке. `fulfill_paid_order` использует
compare-and-swap UPDATE `status=PENDING_PAYMENT → AWAITING_DELIVERY`,
поэтому одновременный webhook и нажатие кнопки безопасны: только один
писатель выигрывает гонку, второй видит `already_done`.

## Масштабирование

- Перейти на Postgres + Redis (`docker compose up`).
- Запускать несколько воркеров **polling под одним токеном нельзя** —
  Telegram отдаёт апдейты только одному. Для горизонтального
  масштабирования переключиться на webhook + reverse proxy.
- При желании: вынести `ThrottlingMiddleware` в Redis-реализацию
  (token-bucket), чтобы лимиты были общие между воркерами.
