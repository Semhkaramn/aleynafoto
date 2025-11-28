import asyncio
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

SQL = """
-- Dinlenen kanallar
CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT UNIQUE NOT NULL,
    title TEXT
);

-- Yasak kelimeler
CREATE TABLE IF NOT EXISTS banned_words (
    id SERIAL PRIMARY KEY,
    word TEXT UNIQUE NOT NULL
);

-- Mesaj taslakları
CREATE TABLE IF NOT EXISTS templates (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

-- Genel ayarlar
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- İlk kurulum işaretleyicisi
INSERT INTO settings(key, value)
    VALUES ('setup_complete', 'true')
    ON CONFLICT (key) DO NOTHING;
"""

async def main():
    print("[*] Veritabanına bağlanılıyor…")
    conn = await asyncpg.connect(DATABASE_URL)

    print("[*] Tablolar oluşturuluyor…")
    try:
        await conn.execute(SQL)
        print("[✓] Tablolar başarıyla kuruldu.")
    except Exception as e:
        print("[HATA]", e)
    finally:
        await conn.close()
        print("[*] Bağlantı kapatıldı.")

asyncio.run(main())
