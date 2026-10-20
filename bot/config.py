"""Конфигурация бота из окружения. Никакого состояния в процессе:
диалоги без FSM, данные — в PostgreSQL, файлы — в MinIO.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: str = ""  # telegram id через запятую
    database_url: str

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "products"
    # Публичная база для ссылок на фото (совпадает с тем, что видит браузер)
    minio_public_base_url: str = "http://localhost:9000"
    # HTTPS-адрес каталога для кнопки Mini App (Telegram требует https)
    web_app_url: str = "https://example.com"


settings = Settings()

ADMIN_IDS = frozenset(
    int(x) for x in settings.admin_ids.replace(" ", "").split(",") if x
)
