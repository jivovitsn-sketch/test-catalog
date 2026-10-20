-- Схема каталога. Состояние живёт только здесь и в MinIO —
-- сервисы stateless и масштабируются горизонтально.
-- Известный компромисс MVP: связи photo_key -> объект MinIO нет
-- (удаление строки не удаляет объект), см. README.
BEGIN;

CREATE TABLE IF NOT EXISTS public.products (
    id         BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       VARCHAR(200)  NOT NULL CHECK (name <> ''),
    photo_key  VARCHAR(200)  NOT NULL CHECK (photo_key <> '') UNIQUE,  -- uuid4-hex.jpg (36 симв.)
    created_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMIT;
