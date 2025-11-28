import os
import asyncio
from telethon import TelegramClient, events
import asyncpg
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION", "session.session")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))

client = TelegramClient(SESSION, API_ID, API_HASH)

# Kullanıcıya soru sorup cevap beklemek için state tutacağız
user_states = {}  # {user_id: {"action": "...", "step": int, "data": {...}}}


########################################
# DB BAĞLANTI
########################################
async def db_connect():
    return await asyncpg.connect(DATABASE_URL)


########################################
# SETTINGS
########################################
async def set_setting(key: str, value: str):
    conn = await db_connect()
    try:
        await conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key, value
        )
    finally:
        await conn.close()


async def get_setting(key: str):
    conn = await db_connect()
    try:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row["value"] if row else None
    finally:
        await conn.close()


########################################
# KANAL İŞLEMLERİ
########################################
async def add_channel(channel_id: int, title: str = None):
    conn = await db_connect()
    try:
        await conn.execute(
            """
            INSERT INTO channels(channel_id, title)
            VALUES($1, $2)
            ON CONFLICT (channel_id) DO UPDATE SET title = EXCLUDED.title
            """,
            channel_id, title
        )
    finally:
        await conn.close()


async def delete_channel(channel_id: int):
    conn = await db_connect()
    try:
        await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
    finally:
        await conn.close()


async def get_channels():
    conn = await db_connect()
    try:
        rows = await conn.fetch("SELECT channel_id, title FROM channels ORDER BY id")
        return [{"id": r["channel_id"], "title": r["title"]} for r in rows]
    finally:
        await conn.close()


########################################
# YASAK KELİME İŞLEMLERİ
########################################
async def add_banned_word(word: str):
    conn = await db_connect()
    try:
        await conn.execute(
            """
            INSERT INTO banned_words(word)
            VALUES($1)
            ON CONFLICT (word) DO NOTHING
            """,
            word.lower()
        )
    finally:
        await conn.close()


async def delete_banned_word(word: str):
    conn = await db_connect()
    try:
        await conn.execute("DELETE FROM banned_words WHERE word = $1", word.lower())
    finally:
        await conn.close()


async def get_banned_words():
    conn = await db_connect()
    try:
        rows = await conn.fetch("SELECT word FROM banned_words ORDER BY word")
        return [r["word"] for r in rows]
    finally:
        await conn.close()


########################################
# TEMPLATES (MESAJ TASLAKLARI)
########################################
async def add_template(name: str, content: str):
    conn = await db_connect()
    try:
        await conn.execute(
            """
            INSERT INTO templates(name, content)
            VALUES($1, $2)
            ON CONFLICT (name)
            DO UPDATE SET content = EXCLUDED.content
            """,
            name, content
        )
    finally:
        await conn.close()


async def delete_template(name: str):
    conn = await db_connect()
    try:
        await conn.execute("DELETE FROM templates WHERE name = $1", name)
    finally:
        await conn.close()


async def list_templates():
    conn = await db_connect()
    try:
        rows = await conn.fetch(
            "SELECT id, name, content, is_active FROM templates ORDER BY id"
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "content": r["content"],
                "is_active": r["is_active"],
            }
            for r in rows
        ]
    finally:
        await conn.close()


async def set_active_template(name: str):
    conn = await db_connect()
    try:
        await conn.execute("UPDATE templates SET is_active = FALSE")
        await conn.execute(
            "UPDATE templates SET is_active = TRUE WHERE name = $1",
            name
        )
    finally:
        await conn.close()


async def get_active_template_content():
    conn = await db_connect()
    try:
        row = await conn.fetchrow(
            "SELECT content FROM templates WHERE is_active = TRUE LIMIT 1"
        )
        return row["content"] if row else None
    finally:
        await conn.close()


########################################
# MENÜ METNİ
########################################
def menu_text():
    return (
        "🔧 *Yönetim Menüsü*\n\n"
        "📌 Kanal İşlemleri:\n"
        "  • `/add_channel` → Dinlenecek kanal ekle\n"
        "  • `/del_channel` → Dinlenecek kanalı sil\n"
        "  • `/list_channels` → Dinlenen kanalları listele\n\n"
        "🎯 Hedef Kanal:\n"
        "  • `/set_target` → Fotoğrafların gönderileceği kanalı ayarla\n\n"
        "✉ Mesaj Taslakları:\n"
        "  • `/add_template` → Yeni mesaj taslağı ekle\n"
        "  • `/list_templates` → Taslakları listele\n"
        "  • `/set_template` → Aktif taslağı seç\n"
        "  • `/del_template` → Taslak sil\n\n"
        "🚫 Yasak Kelimeler:\n"
        "  • `/add_ban` → Yasak kelime ekle\n"
        "  • `/del_ban` → Yasak kelime sil\n"
        "  • `/banlist` → Yasak kelimeleri listele\n\n"
        "❌ `/cancel` → Devam eden işlemi iptal et\n"
    )


########################################
# OWNER MESAJLARI & STATE MAKİNESİ
########################################
@client.on(events.NewMessage(from_users=OWNER_ID))
async def owner_commands(event):
    user_id = event.sender_id
    text = (event.raw_text or "").strip()

    # Önce iptal kontrolü
    if text == "/cancel":
        user_states.pop(user_id, None)
        await event.reply("❌ İşlem iptal edildi.")
        return

    # Eğer kullanıcı bir akışın ortasındaysa, onu devam ettir
    state = user_states.get(user_id)
    if state:
        await handle_state(event, state)
        return

    # Yeni komutlar
    if text == "/menu" or text == "/start":
        await event.reply(menu_text(), parse_mode="markdown")
        return

    # Kanal ekleme akışı
    if text == "/add_channel":
        user_states[user_id] = {"action": "add_channel", "step": 1, "data": {}}
        await event.reply(
            "📡 Dinlenecek kanalı ekliyorsun.\n"
            "Kanal *kullanıcı adını* (`@kanaladi`) veya *ID*’sini (`-100...`) gönder.",
            parse_mode="markdown",
        )
        return

    if text == "/del_channel":
        user_states[user_id] = {"action": "del_channel", "step": 1, "data": {}}
        await event.reply(
            "🗑 Silmek istediğin kanalın kullanıcı adını (`@kanal`) veya ID’sini (`-100...`) gönder."
        )
        return

    if text == "/list_channels":
        channels = await get_channels()
        if not channels:
            await event.reply("📭 Dinlenen kanal yok.")
        else:
            msg = "📡 *Dinlenen Kanallar:*\n\n"
            for c in channels:
                line = f"- `{c['id']}`"
                if c["title"]:
                    line += f" | {c['title']}"
                msg += line + "\n"
            await event.reply(msg, parse_mode="markdown")
        return

    # Hedef kanal ayarı
    if text == "/set_target":
        user_states[user_id] = {"action": "set_target", "step": 1, "data": {}}
        await event.reply(
            "🎯 Fotoğrafların gönderileceği kanalın kullanıcı adını (`@kanal`) veya ID’sini (`-100...`) gönder."
        )
        return

    # Taslak ekleme
    if text == "/add_template":
        user_states[user_id] = {"action": "add_template", "step": 1, "data": {}}
        await event.reply(
            "✉ Yeni taslak ekliyorsun.\n"
            "Önce taslak için bir *isim* gönder (örnek: `standart`, `kampanya1` gibi).",
            parse_mode="markdown",
        )
        return

    if text == "/list_templates":
        templates = await list_templates()
        if not templates:
            await event.reply("✉ Kayıtlı taslak yok.")
        else:
            msg = "✉ *Mesaj Taslakları:*\n\n"
            for t in templates:
                mark = "✅" if t["is_active"] else "▫️"
                msg += f"{mark} `{t['name']}`\n"
            await event.reply(msg, parse_mode="markdown")
        return

    if text == "/set_template":
        templates = await list_templates()
        if not templates:
            await event.reply("Önce en az bir taslak ekle (`/add_template`).")
            return
        user_states[user_id] = {"action": "set_template", "step": 1, "data": {}}
        names = ", ".join([t["name"] for t in templates])
        await event.reply(
            "✅ Aktif yapmak istediğin taslağın *ismini* yaz.\n"
            f"Mevcut taslaklar: {names}",
            parse_mode="markdown",
        )
        return

    if text == "/del_template":
        templates = await list_templates()
        if not templates:
            await event.reply("Silinecek taslak yok.")
            return
        user_states[user_id] = {"action": "del_template", "step": 1, "data": {}}
        names = ", ".join([t["name"] for t in templates])
        await event.reply(
            "🗑 Silmek istediğin taslağın *ismini* yaz.\n"
            f"Mevcut taslaklar: {names}",
            parse_mode="markdown",
        )
        return

    # Yasak kelime
    if text == "/add_ban":
        user_states[user_id] = {"action": "add_ban", "step": 1, "data": {}}
        await event.reply("🚫 Yasaklamak istediğin kelimeyi yaz.")
        return

    if text == "/del_ban":
        user_states[user_id] = {"action": "del_ban", "step": 1, "data": {}}
        await event.reply("🔓 Serbest bırakmak istediğin (kaldırılacak) kelimeyi yaz.")
        return

    if text == "/banlist":
        banned = await get_banned_words()
        if not banned:
            await event.reply("🚫 Yasak kelime listesi boş.")
        else:
            msg = "🚫 *Yasak Kelimeler:*\n\n" + "\n".join([f"- {w}" for w in banned])
            await event.reply(msg, parse_mode="markdown")
        return

    # Tanınmayan komut
    if text.startswith("/"):
        await event.reply("Komutu anlamadım. Menüyü görmek için `/menu` yaz.")
        return


########################################
# STATE HANDLER (SORU-CEVAP AKIŞLARI)
########################################
async def handle_state(event, state):
    user_id = event.sender_id
    text = (event.raw_text or "").strip()
    action = state["action"]
    step = state["step"]
    data = state["data"]

    # KANAL EKLE
    if action == "add_channel" and step == 1:
        # kullanıcı adı mı ID mi kontrol
        try:
            if text.startswith("@"):
                entity = await client.get_entity(text)
                cid = entity.id
                title = getattr(entity, "title", None)
            else:
                cid = int(text)
                entity = await client.get_entity(cid)
                title = getattr(entity, "title", None)
        except Exception as e:
            await event.reply(f"Hata: kanalı bulamadım. ({e})\nTekrar dene veya `/cancel` yaz.")
            return

        await add_channel(cid, title)
        user_states.pop(user_id, None)
        await event.reply(f"✅ Dinlenecek kanala eklendi: `{cid}` | {title}", parse_mode="markdown")
        return

    # KANAL SİL
    if action == "del_channel" and step == 1:
        try:
            if text.startswith("@"):
                entity = await client.get_entity(text)
                cid = entity.id
            else:
                cid = int(text)
        except Exception as e:
            await event.reply(f"Hata: kanalı bulamadım. ({e})\nTekrar dene veya `/cancel` yaz.")
            return

        await delete_channel(cid)
        user_states.pop(user_id, None)
        await event.reply(f"🗑 Silindi: `{cid}`", parse_mode="markdown")
        return

    # HEDEF KANAL
    if action == "set_target" and step == 1:
        try:
            if text.startswith("@"):
                entity = await client.get_entity(text)
                cid = entity.id
            else:
                cid = int(text)
        except Exception as e:
            await event.reply(f"Hata: kanalı bulamadım. ({e})\nTekrar dene veya `/cancel` yaz.")
            return

        await set_setting("target_channel_id", str(cid))
        user_states.pop(user_id, None)
        await event.reply(f"🎯 Hedef kanal ayarlandı: `{cid}`", parse_mode="markdown")
        return

    # TASLAK EKLE: ISIM
    if action == "add_template" and step == 1:
        data["name"] = text
        state["step"] = 2
        await event.reply(
            "Şimdi bu taslak için kullanılacak *mesaj içeriğini* gönder.\n"
            "Emoji, link, markdown/HTML kullanabilirsin.\n\n"
            "_Gönderdiğin mesaj olduğu gibi fotoğrafın altına yazılacak._",
            parse_mode="markdown",
        )
        return

    # TASLAK EKLE: İÇERİK
    if action == "add_template" and step == 2:
        name = data["name"]
        content = text
        await add_template(name, content)
        user_states.pop(user_id, None)
        await event.reply(
            f"✉ Taslak kaydedildi: `{name}`\n"
            "Not: Aktif yapmak için `/set_template` ile seçebilirsin.",
            parse_mode="markdown",
        )
        return

    # TASLAK AKTİF ET
    if action == "set_template" and step == 1:
        name = text
        await set_active_template(name)
        user_states.pop(user_id, None)
        await event.reply(f"✅ Aktif taslak: `{name}`", parse_mode="markdown")
        return

    # TASLAK SİL
    if action == "del_template" and step == 1:
        name = text
        await delete_template(name)
        user_states.pop(user_id, None)
        await event.reply(f"🗑 Taslak silindi: `{name}`", parse_mode="markdown")
        return

    # YASAK KELİME EKLE
    if action == "add_ban" and step == 1:
        word = text.strip()
        if not word:
            await event.reply("Boş kelime olmaz. Tekrar yaz veya `/cancel` de.")
            return
        await add_banned_word(word)
        user_states.pop(user_id, None)
        await event.reply(f"🚫 Yasak kelime eklendi: `{word}`", parse_mode="markdown")
        return

    # YASAK KELİME SİL
    if action == "del_ban" and step == 1:
        word = text.strip()
        await delete_banned_word(word)
        user_states.pop(user_id, None)
        await event.reply(f"🔓 Yasak kelime kaldırıldı: `{word}`", parse_mode="markdown")
        return


########################################
# FOTOĞRAF DİNLER (KANALLAR)
########################################
@client.on(events.NewMessage)
async def photo_listener(event):
    # Owner private mesajlarını dinleme burada
    if event.is_private and event.sender_id == OWNER_ID:
        return

    # Dinlenen kanallar
    channels = await get_channels()
    channel_ids = {c["id"] for c in channels}
    if event.chat_id not in channel_ids:
        return

    # Fotoğraf yoksa bye
    if not event.photo:
        return

    # Yasak kelime kontrolü
    caption = (event.message.message or "").lower()
    banned = await get_banned_words()
    for w in banned:
        if w in caption:
            print(f"[FİLTRE] Yasak kelime geçti: {w}")
            return

    # Hedef kanal
    target_str = await get_setting("target_channel_id")
    if not target_str:
        print("[UYARI] target_channel_id ayarlanmamış. `/set_target` kullan.")
        return

    target_id = int(target_str)

    # Aktif taslak
    tpl = await get_active_template_content()
    if not tpl:
        tpl = "📸 Yeni fotoğraf"

    try:
        await client.send_file(
            target_id,
            file=event.photo,
            caption=tpl
        )
        print(f"[OK] Fotoğraf {event.chat_id} -> {target_id}")
    except Exception as e:
        print("[HATA] Fotoğraf gönderilemedi:", e)


########################################
# MAIN
########################################
async def main():
    print("[*] Telegram'a bağlanılıyor...")
    await client.start()
    me = await client.get_me()
    print(f"[+] Giriş yapıldı: {me.id} | @{me.username}")
    print("[*] Sistem çalışıyor. Komutlar için Telegram'da /menu yaz.")

    await asyncio.Future()  # sonsuza kadar dinle


client.loop.run_until_complete(main())
