# Telegram Digital Shop

Простой Telegram-бот для продажи цифровых товаров (активационные ссылки,
аккаунты, ключи). Платежи — через **Telegram Stars** (валюта `XTR`), внешний
провайдер не нужен.

## Возможности

- Каталог товаров с описанием и ценой в Stars.
- Два типа выдачи:
  - **Авто** — товар хранится списком (склад) и выдаётся в момент оплаты.
  - **Ручная** — после оплаты заказ попадает в очередь, админ присылает
    содержимое из админ-панели.
- Админ-панель в боте: создание товара, редактирование названия/описания/цены,
  публикация/скрытие, добавление позиций в склад, выдача ручных заказов.
- История заказов у пользователя.
- Защита от спама (throttling) и атомарная резервация склада на Postgres
  (`SELECT ... FOR UPDATE SKIP LOCKED`) — заказы не задваиваются под нагрузкой.

## Стек

- Python 3.11+, `aiogram` 3.x
- `SQLAlchemy` 2 (async) + `aiosqlite` (dev) / `asyncpg` (prod)
- `pydantic-settings`, `structlog`
- Опционально Redis для FSM (`RedisStorage`)

## Запуск (локально, SQLite)

```bash
cp .env.example .env
# открой .env, поставь BOT_TOKEN и свой ADMIN_IDS
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bot
```

## Запуск в Docker (Postgres + Redis)

```bash
cp .env.example .env  # BOT_TOKEN, ADMIN_IDS
docker compose up -d --build
```

`docker-compose.yml` уже переопределяет `DATABASE_URL` и `REDIS_URL` для
сервисов `db` и `redis`.

## Конфигурация

| Переменная        | Назначение                                                |
| ----------------- | --------------------------------------------------------- |
| `BOT_TOKEN`       | Токен от @BotFather                                       |
| `ADMIN_IDS`       | ID админов через запятую (получить — у @userinfobot)      |
| `DATABASE_URL`    | SQLAlchemy URL (sqlite/postgres)                          |
| `REDIS_URL`       | Redis для FSM (пусто → MemoryStorage, только 1 воркер)    |
| `THROTTLE_RATE`   | Минимум секунд между апдейтами от пользователя            |
| `LOG_LEVEL`       | `DEBUG` / `INFO` / `WARNING` / `ERROR`                    |

## Команды

- `/start` — главное меню (каталог, мои заказы).
- `/admin` — админ-панель (только для `ADMIN_IDS`).

## Как масштабировать

- Перейти на Postgres + Redis (`docker compose up`).
- Запускать несколько воркеров polling под одним токеном **нельзя** —
  Telegram отдаёт апдейты только одному. Для горизонтального
  масштабирования переключиться на webhook + reverse proxy.
- При желании: вынести `ThrottlingMiddleware` в Redis-реализацию
  (token-bucket), чтобы лимиты были общие между воркерами.
