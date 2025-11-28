-- ================================
--  TELEGRAM BOT TABLO KURULUMU
-- ================================

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

-- Genel ayarlar (hedef kanal vs)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- İlk defa çalıştıranlar için varsayılan bilgi
INSERT INTO settings(key, value)
    VALUES ('setup_complete', 'true')
    ON CONFLICT (key) DO NOTHING;
