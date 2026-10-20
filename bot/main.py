"""Telegram-бот каталога (aiogram 3.x).

Функции:
- /start: посетителю — приглашение и кнопка Mini App с каталогом;
  администратору (ADMIN_IDS) — подсказка, как создать товар.
- Фото с подписью (caption + photo одним сообщением) от администратора:
  фото кладётся в MinIO, запись о товаре — в PostgreSQL.

Stateless: FSM не используется, состояние — только в БД и S3;
процесс можно убить и перезапустить без потери данных.
"""

import asyncio
import io
import logging
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import asyncpg
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from minio import Minio
from python_socks import ProxyType
from aiohttp_socks import ProxyConnector

from bot.config import ADMIN_IDS, settings


class _RdnsSession(AiohttpSession):
    """AiohttpSession с принудительным rdns: DNS резолвится на стороне
    SOCKS-сервера. Локальный DNS может отдавать отравленные адреса
    Telegram — тогда socks5:// с локальным резолвом просто виснет."""

    def _setup_proxy_connector(self, proxy: str) -> None:
        parsed = urlparse(proxy)
        self._connector_type = ProxyConnector
        self._connector_init = {
            **self._connector_init,
            "proxy_type": ProxyType.SOCKS5,
            "host": parsed.hostname,
            "port": parsed.port or 1080,
            "rdns": True,
        }
        self._proxy = proxy

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

pool: asyncpg.Pool
s3: Minio


def catalog_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Открыть каталог",
                web_app=WebAppInfo(url=settings.web_app_url),
            )]
        ]
    )


async def ensure_bucket() -> None:
    if not await asyncio.to_thread(s3.bucket_exists, settings.minio_bucket):
        await asyncio.to_thread(s3.make_bucket, settings.minio_bucket)


@F.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user and message.from_user.id in ADMIN_IDS:
        await message.answer(
            "Привет, администратор!\n"
            "Чтобы создать товар, отправьте <b>фото с подписью</b> "
            "в одном сообщении: подпись станет названием товара.\n\n"
            "Каталог: кнопка ниже.",
            reply_markup=catalog_keyboard(),
        )
    else:
        await message.answer(
            "У меня есть товары 🛒\nОткройте каталог прямо здесь:",
            reply_markup=catalog_keyboard(),
        )


@F.message(F.photo)
async def photo_with_caption(message: Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        await message.answer("Создание товаров доступно только администратору.")
        return

    name = (message.caption or "").strip()
    if not name:
        await message.answer(
            "Нужна подпись к фото — она станет названием товара. "
            "Отправьте фото и название одним сообщением."
        )
        return
    if len(name) > 200:
        await message.answer("Название длиннее 200 символов, сократите его.")
        return

    photo = message.photo[-1]  # самый крупный размер
    buf = io.BytesIO()
    await bot.download(photo, destination=buf)

    key = f"{uuid.uuid4().hex}.jpg"
    size = buf.getbuffer().nbytes
    buf.seek(0)
    await asyncio.to_thread(
        s3.put_object,
        settings.minio_bucket,
        key,
        buf,
        length=size,
        content_type="image/jpeg",
    )
    product_id = await pool.fetchval(
        "INSERT INTO products (name, photo_key) VALUES ($1, $2) RETURNING id",
        name,
        key,
    )
    log.info("product created id=%s by=%s", product_id, message.from_user.id)
    await message.answer(f"Товар создан: #{product_id} «{name}».")


@F.message(F.text)
async def fallback_text(message: Message) -> None:
    await message.answer(
        "У меня есть товары 🛒",
        reply_markup=catalog_keyboard(),
    )


async def main() -> None:
    global pool, s3

    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    s3 = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    await ensure_bucket()

    session = _RdnsSession(proxy=settings.tg_proxy) if settings.tg_proxy else None
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Один poller на токен: параллельные getUpdates получают 409.
    # Масштабирование бота — webhook за балансировщиком + дедуп по
    # update_id (см. README). Состояние в процессе отсутствует.
    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)  # зачистка старых апдейтов
            break
        except Exception as e:  # сеть/прокси могли ещё не подняться
            log.warning("telegram not reachable yet: %s; retry in 10s", e)
            await asyncio.sleep(10)
    dp = Dispatcher()
    dp.include_router(Router())

    # Один poller на токен: параллельные getUpdates получают 409.
    # Масштабирование бота — webhook за балансировщиком + дедуп по
    # update_id (см. README). Состояние в процессе отсутствует.
    await bot.delete_webhook(drop_pending_updates=True)  # зачистка старых апдейтов
    try:
        await dp.start_polling(bot)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
