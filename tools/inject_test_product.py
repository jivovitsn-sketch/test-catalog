import asyncio, datetime, os

import asyncpg
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Chat, Message, User, FSInputFile
from minio import Minio

import bot.main as bm

ADMIN = 7666974894

async def main():
    bot = Bot(token=os.environ["BOT_TOKEN"],
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    probe = await bot.send_message(ADMIN, "Связь есть. Досылаю тестовый товар через обработчик — ответ ниже.")
    print("PROBE sent, message_id:", probe.message_id)

    sent = await bot.send_photo(ADMIN, photo=FSInputFile("/tmp/product.png"))
    await asyncio.sleep(1)

    bm.pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    bm.s3 = Minio(os.environ.get("MINIO_ENDPOINT", "minio:9000"),
                  access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
                  secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
                  secure=False)
    msg = Message(
        message_id=sent.message_id + 500,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=Chat(id=ADMIN, type="private"),
        from_user=User(id=ADMIN, is_bot=False, first_name="Sergey"),
        photo=sent.photo,
        caption="Смартфон Astra X1",
    )
    await bm.photo_with_caption(msg, bot)
    print("HANDLER_DONE")
    n = await bm.pool.fetchval("SELECT count(*) FROM products")
    print("products in DB:", n)
    await bm.pool.close()
    await bot.session.close()

asyncio.run(main())
