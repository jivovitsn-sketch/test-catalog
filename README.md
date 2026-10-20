# test-catalog — минимальный интернет-магазин (тестовое задание)

Прототип: каталог товаров + Telegram-бот (админ создаёт товары) + Mini App.
Требование отказоустойчивости выполнено архитектурно: **все сервисы stateless** —
состояние живёт только в PostgreSQL (данные) и MinIO (файлы), поэтому любой
компонент запускается в N экземпляров за балансировщиком.

## Стек (по ТЗ)

| Слой        | Технология            |
|-------------|-----------------------|
| Фронтенд    | Next.js 15 (App Router), React 19, TypeScript |
| Бэкенд      | FastAPI + asyncpg     |
| Бот         | aiogram 3.x           |
| БД          | PostgreSQL 16         |
| S3          | MinIO (бакет `products`) |
| Балансир    | nginx (round-robin по DNS Docker) |

## Функциональность

1. **Разместить товар** — админ бота отправляет *фото с подписью* одним
   сообщением: фото → MinIO, запись → PostgreSQL.
2. **Каталог** — страница Next.js «Каталог» со списком товаров; открывается
   и в обычном браузере, и как Telegram Mini App (кнопка в боте).
3. Бот на `/start` отвечает «У меня есть товары» и предлагает открыть каталог.

## Архитектура

```
Telegram ──polling──> bot (aiogram) ──> MinIO (фото) + PostgreSQL (запись)
                                          │
Браузер/TMA ──> nginx :8080 ──> web (Next.js) ──fetch no-store──> api (FastAPI) ──> PostgreSQL
                        └────────────>/api/ ──────────────> api x N реплик (round-robin)
```

- **web** — серверные компоненты, `fetch(..., { cache: "no-store" })`:
  страница всегда собирается из актуальных данных БД, реплики web
  взаимозаменяемы.
- **api** — только чтение, пул asyncpg; идентификатор инстанса возвращается
  в `/api/health` (`"instance"`), чтобы было видно балансировку.
- **bot** — состояние не хранит (FSM нет: «фото + подпись» — одно сообщение),
  админы задаются переменной окружения; процесс можно убить/перезапустить
  без потери данных.

## Запуск (docker compose)

```bash
cp bot/.env.example bot/.env        # вписать BOT_TOKEN, ADMIN_IDS, WEB_APP_URL
docker compose up --build -d
# каталог: http://localhost:8080      API: http://localhost:8080/api/products
```

### Демо отказоустойчивости API

```bash
docker compose up --scale api=3 --no-deps -d api
for i in 1 2 3 4 5 6; do curl -s http://localhost:8080/api/health | jq -r .instance; done
# имена контейнеров чередуются — nginx раскидывает по репликам;
# kill любой реплики не влияет на доступность
```

## Запуск без docker (как у меня локально)

PostgreSQL 16+ и MinIO можно поднять как угодно; сервисам нужны только
переменные окружения:

```bash
# API
cd api && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://catalog:catalog@127.0.0.1:5432/catalog
export MINIO_PUBLIC_BASE_URL=http://127.0.0.1:9000
uvicorn main:app --port 8010

# Бот
cd bot && pip install -r requirements.txt
cp .env.example .env   # заполнить
python -m bot.main

# Web
cd web && npm install && npm run build
API_BASE_URL=http://127.0.0.1:8010 npm start
```

## Переменные окружения

| Сервис | Переменная | Назначение |
|--------|-----------|------------|
| bot    | `BOT_TOKEN` | токен из BotFather |
| bot    | `ADMIN_IDS` | telegram id админов через запятую |
| bot    | `WEB_APP_URL` | HTTPS-адрес каталога для кнопки Mini App |
| bot/api| `DATABASE_URL` | `postgresql://user:pass@host:5432/catalog` |
| bot    | `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_SECURE` | подключение к S3 |
| api    | `MINIO_PUBLIC_BASE_URL` | база публичных ссылок на фото |
| web    | `API_BASE_URL` | адрес API для серверного fetch |

## Масштабирование бота (важная оговорка)

Long polling допускает **только одного читателя на токен** (второй получает
409). Поэтому так:

- MVP: один poller под systemd/compose с `restart: unless-stopped` — падение
  лечится перезапуском, данные не теряются (состояние в PG/MinIO).
- Горизонтальное масштабирование бота — переводом на webhook
  (`setWebhook` за балансировщиком) + дедупликация по `update_id`
  (`INSERT ... ON CONFLICT DO NOTHING`): доставка Telegram — at-least-once,
  повторная доставка превращается в no-op.

## Осознанные упрощения MVP (по ТЗ «максимальная простота»)

- Бакет `products` с публичным чтением — фото отдаются напрямую; в проде
  выдал бы presigned GET.
- Нет обратной связи БД↔S3: удаление записи не удаляет объект MinIO
  (очистка — фоновая сверка, вне рамок MVP).
- Схема — один идемпотентный `db/init.sql` (исполняется при первой
  инициализации тома БД), без миграционного журнала.
- Аутентификации в web/API нет: API только читает публичный каталог;
  запись — исключительно через бота с проверкой `ADMIN_IDS`.
- Корзина/оформление заказа — не входили в объём демо-функционала ТЗ
  (каталог + создание товара + Mini App).

## Что показано по вопросам теста

- Next.js: серверные компоненты, App Router, no-store для живых данных.
- FastAPI: async + Pydantic-валидация query-параметров (`Query(ge, le)`),
  lifespan-пул соединений.
- PostgreSQL: BIGINT IDENTITY PK, CHECK-констрейнты, UNIQUE на ключ объекта.
- Stateless/multi-instance: без памяти процесса, nginx round-robin,
  демонстрация `--scale`.
- Отказоустойчивость: restart-политики, healthchecks с `depends_on
  condition`, gracefully оговорённое масштабирование бота.
