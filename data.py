CREATE TABLE channels (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT UNIQUE NOT NULL,
    title TEXT
);

CREATE TABLE banned_words (
    id SERIAL PRIMARY KEY,
    word TEXT UNIQUE NOT NULL
);

CREATE TABLE templates (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
