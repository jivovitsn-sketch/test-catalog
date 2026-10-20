"""REST API каталога: только чтение. Товары создаются Telegram-ботом.

Stateless: состояние целиком в PostgreSQL (данные) и MinIO (файлы).
Пул соединений — ресурс процесса, не бизнес-состояние; любой инстанс
взаимозаменяем, что позволяет запускать N реплик за балансировщиком.
"""

import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Query

DATABASE_URL = os.environ["DATABASE_URL"]
MINIO_PUBLIC_BASE_URL = os.environ.get("MINIO_PUBLIC_BASE_URL", "http://localhost:9000")
INSTANCE = os.environ.get("INSTANCE_NAME", os.environ.get("HOSTNAME", "unknown"))

pool: asyncpg.Pool


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    yield
    await pool.close()


app = FastAPI(title="test-catalog API", lifespan=lifespan)


def _to_item(row: asyncpg.Record) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "photo_url": f"{MINIO_PUBLIC_BASE_URL}/products/{row['photo_key']}",
        "created_at": row["created_at"].isoformat(),
    }


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    await pool.fetchval("SELECT 1")  # readiness: БД отвечает
    return {"status": "ok", "instance": INSTANCE}


@app.get("/api/products")
async def list_products(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    rows = await pool.fetch(
        "SELECT id, name, photo_key, created_at"
        " FROM products ORDER BY id DESC LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return {"items": [_to_item(r) for r in rows]}


@app.get("/api/products/{product_id}")
async def get_product(product_id: int) -> dict:
    row = await pool.fetchrow(
        "SELECT id, name, photo_key, created_at FROM products WHERE id = $1",
        product_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return _to_item(row)
