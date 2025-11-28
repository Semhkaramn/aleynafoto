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

# Soru-cevap akışları için basit state
# {user_id: {"action": "...", "step": int, "data": {...}}}
user_states = {}


########################################
# DB YARDIMCI FONKSİYONLAR
########################################

async def db_connect():
    return await asyncpg.connect(DATABASE_URL)


async def set_setting(key: str, value: str):
    conn = await db_connect()
    try:
        await conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key,
            value,
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

async def add_channel(channel_id: int, title: str | None = None):
    conn = await db_connect()
    try:
        await conn.execute(
            """
            INSERT INTO channels(channel_id, title)
            VALUES($1, $2)
            ON CONFLICT (channel_id) DO UPDATE SET title = EXCLUDED.title
            """,
            channel_id,
            title,
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
# YASAK KELİMELER
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
            word.lower(),
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
# TEMPLATES / TASLAKLAR
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
            name,
            content,
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
            name,
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
# YARDIM METNİ
########################################

def help_text():
    return (
        "🔧 Yönetim komutları (yazı ile kullan):\n\n"
        "📡 Kanallar:\n"
        "  • `kanal ekle` → Dinlenecek kanal ekler\n"
        "  • `kanal sil` → Dinlenecek kanal siler\n"
        "  • `kanalları göster` → Dinlenen kanalları listeler\n\n"
        "🎯 Hedef kanal:\n"
        "  • `hedef kanalı ayarla` → Fotoğrafların gideceği kanalı seçer\n\n"
        "✉ Taslaklar:\n"
        "  • `taslak ekle` → Yeni mesaj taslağı ekler\n"
        "  • `taslakları göster` → Kayıtlı taslakları listeler\n"
        "  • `taslağı aktif et` → Kullanılacak taslağı seçer\n"
        "  • `taslak sil` → Taslak siler\n\n"
        "🚫 Yasak kelimeler:\n"
        "  • `yasak kelime ekle`\n"
        "  • `yasak kelime sil`\n"
        "  • `yasak kelimeleri göster`\n\n"
        "❌ `iptal` → Devam eden işlemi iptal eder\n"
    )


########################################
# OWNER MESAJLARI (SENİNLE SOHBET)
########################################

@client.on(events.NewMessage(from_users=OWNER_ID))
async def owner_commands(event):
    user_id = event.sender_id
    raw_text = event.raw_text or ""
    text = raw_text.strip()
    text_lower = text.lower().lstrip("/")

    # iptal
    if text_lower in ["iptal", "cancel"]:
        user_states.pop(user_id, None)
        await event.reply("❌ İşlem iptal edildi.")
        return

    # devam eden akış varsa onu işleyelim
    state = user_states.get(user_id)
    if state:
        await handle_state(event, state)
        return

    # yardım / menü
    if text_lower in ["menu", "menü", "yardım", "help", "komutlar"]:
        await event.reply(help_text())
        return

    # Taslak ekle
    if text_lower in ["taslak ekle", "yeni taslak", "template ekle"]:
        user_states[user_id] = {"action": "add_template", "step": 1, "data": {}}
        await event.reply(
            "✉ Yeni taslak ekliyorsun.\nLütfen taslak için bir *isim* yaz.",
            parse_mode="markdown",
        )
        return

    # Taslakları göster
    if text_lower in ["taslakları göster", "taslak listesi", "taslak listesi göster", "template list"]:
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

    # Taslağı aktif et
    if text_lower in ["taslağı aktif et", "aktif taslak seç", "aktif taslak"]:
        templates = await list_templates()
        if not templates:
            await event.reply("Önce en az bir taslak ekle (`taslak ekle`).")
            return
        user_states[user_id] = {"action": "set_template", "step": 1, "data": {}}
        names = ", ".join([t["name"] for t in templates])
        await event.reply(
            "✅ Aktif yapmak istediğin taslağın *ismini* yaz.\n"
            f"Mevcut taslaklar: {names}",
            parse_mode="markdown",
        )
        return

    # Taslak sil
    if text_lower in ["taslak sil", "template sil"]:
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

    # Kanal ekle
    if text_lower in ["kanal ekle", "dinleme kanalı ekle"]:
        user_states[user_id] = {"action": "add_channel", "step": 1, "data": {}}
        await event.reply(
            "📡 Dinlenecek kanalı ekliyorsun.\n"
            "Kanal kullanıcı adını (`@kanaladi`) veya ID'sini (`-100...`) yaz."
        )
        return

    # Kanal sil
    if text_lower in ["kanal sil", "dinleme kanalı sil"]:
        user_states[user_id] = {"action": "del_channel", "step": 1, "data": {}}
        await event.reply(
            "🗑 Silmek istediğin kanalın kullanıcı adını (`@kanal`) veya ID'sini (`-100...`) yaz."
        )
        return

    # Kanalları göster
    if text_lower in ["kanalları göster", "kanal listesi", "dinleme kanalları"]:
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

    # Hedef kanal ayarla
    if text_lower in ["hedef kanalı ayarla", "hedef kanal ayarla", "hedef kanal"]:
        user_states[user_id] = {"action": "set_target", "step": 1, "data": {}}
        await event.reply(
            "🎯 Fotoğrafların gönderileceği kanalın kullanıcı adını (`@kanal`) "
            "veya ID'sini (`-100...`) yaz."
        )
        return

    # Yasak kelime ekle
    if text_lower in ["yasak kelime ekle", "ban kelime ekle"]:
        user_states[user_id] = {"action": "add_ban", "step": 1, "data": {}}
        await event.reply("🚫 Yasaklamak istediğin kelimeyi yaz.")
        return

    # Yasak kelime sil
    if text_lower in ["yasak kelime sil", "ban kelime sil"]:
        user_states[user_id] = {"action": "del_ban", "step": 1, "data": {}}
        await event.reply("🔓 Kaldırmak istediğin yasak kelimeyi yaz.")
        return

    # Yasak kelimeleri göster
    if text_lower in ["yasak kelimeleri göster", "yasak kelimeler", "ban listesi"]:
        banned = await get_banned_words()
        if not banned:
            await event.reply("🚫 Yasak kelime listesi boş.")
        else:
            msg = "🚫 *Yasak Kelimeler:*\n\n" + "\n".join([f"- {w}" for w in banned])
            await event.reply(msg, parse_mode="markdown")
        return

    # Tanınmayan mesaj
    await event.reply(
        "Ne yapmak istediğini anlamadım.\n"
        "`menü` yazıp kullanılabilir komutlara bakabilirsin."
    )


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
            await event.reply(
                f"Hata: kanalı bulamadım. ({e})\n"
                "Tekrar dene veya `iptal` yaz."
            )
            return

        await add_channel(cid, title)
        user_states.pop(user_id, None)
        await event.reply(
            f"✅ Dinlenecek kanala eklendi: `{cid}` | {title}",
            parse_mode="markdown",
        )
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
            await event.reply(
                f"Hata: kanalı bulamadım. ({e})\n"
                "Tekrar dene veya `iptal` yaz."
            )
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
            await event.reply(
                f"Hata: kanalı bulamadım. ({e})\n"
                "Tekrar dene veya `iptal` yaz."
            )
            return

        await set_setting("target_channel_id", str(cid))
        user_states.pop(user_id, None)
        await event.reply(f"🎯 Hedef kanal ayarlandı: `{cid}`", parse_mode="markdown")
        return

    # TASLAK EKLE: İSİM
    if action == "add_template" and step == 1:
        data["name"] = text
        state["step"] = 2
        await event.reply(
            "Şimdi bu taslak için kullanılacak *mesaj içeriğini* gönder.\n"
            "HTML / markdown / emoji / link hepsi serbest.\n\n"
            "_Gönderdiğin içerik fotoğrafın altına aynen yazılacak._",
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
            "Not: Kullanmak için `taslağı aktif et` yazıp seçebilirsin.",
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
            await event.reply("Boş kelime olmaz. Tekrar yaz veya `iptal` de.")
            return
        await add_banned_word(word)
        user_states.pop(user_id, None)
        await event.reply(
            f"🚫 Yasak kelime eklendi: `{word}`",
            parse_mode="markdown",
        )
        return

    # YASAK KELİME SİL
    if action == "del_ban" and step == 1:
        word = text.strip()
        await delete_banned_word(word)
        user_states.pop(user_id, None)
        await event.reply(
            f"🔓 Yasak kelime kaldırıldı: `{word}`",
            parse_mode="markdown",
        )
        return


########################################
# TÜM MESAJLARI DİNLE – FOTOĞRAF VARSA AL
########################################

@client.on(events.NewMessage)
async def photo_listener(event):
    # Sahibin özel sohbeti dinleme
    if event.is_private and event.sender_id == OWNER_ID:
        return

    # Dinlenen kanallar listesi
    channels = await get_channels()
    channel_ids = {c["id"] for c in channels}
    if event.chat_id not in channel_ids:
        return

    # Tüm fotoğraf kaynaklarını tek tek kontrol et
    photo = None

    # 1) Normal foto
    if event.photo:
        photo = event.photo

    # 2) Kanal postu fotoğrafı
    if not photo and event.media:
        photo = getattr(event.media, "photo", None)

    # 3) Eski Telegram versiyonları
    if not photo and hasattr(event.message, "media") and event.message.media:
        photo = getattr(event.message.media, "photo", None)

    # 4) Document içinde foto olabilir (jpg/png/pdf hariç)
    if not photo and event.message.document:
        if getattr(event.message.document, "mime_type", "").startswith("image"):
            photo = event.message.media

    # 5) Bazı kanallar web_page.thumb kullanır
    if not photo:
        wp = getattr(event.message, "media", None)
        if wp and hasattr(wp, "webpage") and hasattr(wp.webpage, "photo"):
            photo = wp.webpage.photo

    # Eğer hiçbir foto formatı yoksa pas geç
    if not photo:
        return

    # Yasak kelime kontrolü
    caption = (event.message.message or "").lower()
    banned = await get_banned_words()
    for w in banned:
        if w and w.lower() in caption:
            print(f"[FİLTRE] Yasak kelime geçti: {w}")
            return

    # Hedef kanal
    target_str = await get_setting("target_channel_id")
    if not target_str:
        print("[UYARI] hedef kanalı ayarlamadın.")
        return

    target_id = int(target_str)

    # Aktif taslak
    tpl = await get_active_template_content()
    if not tpl:
        tpl = "📸 Yeni fotoğraf"

    # Gönder
    try:
        await client.send_file(
            target_id,
            file=photo,
            caption=tpl,
            parse_mode="html"
        )
        print(f"[OK] Fotoğraf {event.chat_id} -> {target_id}")
    except Exception as e:
        print("[HATA] Gönderilemedi:", e)




########################################
# MAIN
########################################

async def main():
    print("[*] Telegram'a bağlanılıyor...")
    await client.start()
    me = await client.get_me()
    print(f"[+] Giriş yapıldı: {me.id} | @{me.username}")
    print("[*] Sistem çalışıyor. Yönetim için bana 'menü' yaz.")

    await asyncio.Future()  # sonsuza kadar dinle


client.loop.run_until_complete(main())
