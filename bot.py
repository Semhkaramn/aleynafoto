import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import asyncpg
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION", "session.session")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))

client = TelegramClient(SESSION, API_ID, API_HASH)

# Kullanıcı state yönetimi
user_states = {}

# Debug modu
DEBUG = os.getenv("DEBUG", "false").lower() == "true"


########################################
# LOGGER
########################################

def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


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
# YARDIMCI FONKSİYONLAR
########################################

async def get_channel_info(channel_id: int):
    """Kanal bilgilerini al"""
    try:
        entity = await client.get_entity(channel_id)
        return {
            "id": entity.id,
            "title": getattr(entity, "title", "Bilinmiyor"),
            "username": getattr(entity, "username", None)
        }
    except Exception as e:
        log(f"Kanal bilgisi alınamadı {channel_id}: {e}", "ERROR")
        return {"id": channel_id, "title": "Bilinmiyor", "username": None}


def extract_photo_from_message(message):
    """Mesajdan fotoğraf çıkartma - GELİŞTİRİLMİŞ VERSİYON"""

    # 1. Direkt foto var mı?
    if message.photo:
        if DEBUG:
            log("Foto bulundu: message.photo", "DEBUG")
        return message.photo

    # 2. Media kontrolü
    if not message.media:
        return None

    # 3. MessageMediaPhoto
    if isinstance(message.media, MessageMediaPhoto):
        if DEBUG:
            log("Foto bulundu: MessageMediaPhoto", "DEBUG")
        return message.media.photo

    # 4. Document içinde resim
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            mime = getattr(doc, "mime_type", "")
            if mime.startswith("image/"):
                if DEBUG:
                    log(f"Foto bulundu: Document ({mime})", "DEBUG")
                return message.media

    # 5. Genel media.photo
    if hasattr(message.media, "photo"):
        if DEBUG:
            log("Foto bulundu: media.photo", "DEBUG")
        return message.media.photo

    # 6. WebPage içinde foto
    if hasattr(message.media, "webpage"):
        webpage = message.media.webpage
        if hasattr(webpage, "photo") and webpage.photo:
            if DEBUG:
                log("Foto bulundu: webpage.photo", "DEBUG")
            return webpage.photo

    return None


########################################
# YARDIM METNİ
########################################

def help_text():
    return (
        "🤖 **Telegram Fotoğraf Yönetim Sistemi**\n\n"
        "📋 **Kullanılabilir Komutlar:**\n\n"

        "📡 **Dinleme Kanalları:**\n"
        "• `kanal ekle` - Fotoğraf dinlenecek kanal ekle\n"
        "• `kanal sil` - Dinlenen kanalı sil\n"
        "• `kanallar` - Tüm dinlenen kanalları göster\n\n"

        "🎯 **Hedef Kanal:**\n"
        "• `hedef ayarla` - Fotoğrafların gönderileceği kanalı ayarla\n"
        "• `hedef göster` - Mevcut hedef kanalı göster\n"
        "• `hedef sil` - Hedef kanalı kaldır\n\n"

        "✉️ **Mesaj Taslakları:**\n"
        "• `taslak ekle` - Yeni mesaj taslağı ekle\n"
        "• `taslaklar` - Tüm taslakları göster\n"
        "• `taslak aktif` - Kullanılacak taslağı seç\n"
        "• `taslak sil` - Taslak sil\n\n"

        "🚫 **Yasak Kelimeler:**\n"
        "• `yasak ekle` - Yasak kelime ekle\n"
        "• `yasak sil` - Yasak kelime sil\n"
        "• `yasaklar` - Yasak kelime listesi\n\n"

        "📊 **Genel:**\n"
        "• `durum` - Sistem durumunu göster\n"
        "• `menü` veya `yardım` - Bu yardım metnini göster\n"
        "• `iptal` - Devam eden işlemi iptal et\n\n"

        "💡 **Nasıl Çalışır?**\n"
        "1. Dinleme kanalları ekle\n"
        "2. Hedef kanalı ayarla\n"
        "3. Taslak oluştur ve aktif et\n"
        "4. Dinlenen kanallara gelen fotoğraflar otomatik olarak hedef kanala gönderilir!"
    )


########################################
# KOMUT YÖNETİMİ
########################################

@client.on(events.NewMessage(from_users=OWNER_ID))
async def owner_commands(event):
    user_id = event.sender_id
    raw_text = event.raw_text or ""
    text = raw_text.strip()
    text_lower = text.lower().lstrip("/")

    # İptal
    if text_lower in ["iptal", "cancel", "vazgeç"]:
        user_states.pop(user_id, None)
        await event.reply("❌ İşlem iptal edildi.")
        return

    # Devam eden akış varsa işle
    state = user_states.get(user_id)
    if state:
        await handle_state(event, state)
        return

    # YARDIM / MENÜ
    if text_lower in ["menu", "menü", "start", "başlat", "/start", "yardım", "help", "?"]:
        await event.reply(help_text(), parse_mode="markdown")
        return

    # DURUM
    if text_lower in ["durum", "status", "info"]:
        channels = await get_channels()
        templates = await list_templates()
        banned = await get_banned_words()
        target_str = await get_setting("target_channel_id")
        active_tpl = await get_active_template_content()

        msg = "📊 **Sistem Durumu**\n\n"
        msg += f"📡 Dinlenen Kanal: **{len(channels)}**\n"
        msg += f"🎯 Hedef Kanal: {'✅ Ayarlı' if target_str else '❌ Yok'}\n"
        msg += f"✉️ Mesaj Taslağı: **{len(templates)}**\n"
        msg += f"✅ Aktif Taslak: {'✅ Var' if active_tpl else '❌ Yok'}\n"
        msg += f"🚫 Yasak Kelime: **{len(banned)}**\n"
        msg += f"🤖 Bot: ✅ Çalışıyor\n"

        await event.reply(msg, parse_mode="markdown")
        return

    # KANAL İŞLEMLERİ
    if text_lower in ["kanal ekle", "dinleme ekle", "kaynak ekle"]:
        user_states[user_id] = {"action": "add_channel", "step": 1, "data": {}}
        await event.reply(
            "📡 **Dinleme Kanalı Ekleme**\n\n"
            "Kanal kullanıcı adını (`@kanaladi`) veya ID'sini (`-100...`) yaz.\n\n"
            "_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["kanal sil", "dinleme sil", "kaynak sil"]:
        channels = await get_channels()
        if not channels:
            await event.reply("❌ Silinecek kanal yok!")
            return
        user_states[user_id] = {"action": "del_channel", "step": 1, "data": {}}
        await event.reply(
            "🗑 **Dinleme Kanalı Silme**\n\n"
            "Silmek istediğin kanalın kullanıcı adını veya ID'sini yaz.\n\n"
            "_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["kanallar", "kanal listesi", "dinlenenler"]:
        channels = await get_channels()
        if not channels:
            await event.reply("📭 Henüz dinlenen kanal yok.\n\n`kanal ekle` yazarak ekleyebilirsin.")
            return

        msg = "📡 **Dinlenen Kanallar:**\n\n"
        for c in channels:
            msg += f"• `{c['id']}` - {c['title'] or 'İsimsiz'}\n"
        msg += f"\n**Toplam:** {len(channels)} kanal"

        await event.reply(msg, parse_mode="markdown")
        return

    # HEDEF KANAL İŞLEMLERİ
    if text_lower in ["hedef ayarla", "hedef kanal", "hedef kanal ayarla"]:
        user_states[user_id] = {"action": "set_target", "step": 1, "data": {}}
        await event.reply(
            "🎯 **Hedef Kanal Ayarlama**\n\n"
            "Fotoğrafların gönderileceği kanalın kullanıcı adını veya ID'sini yaz.\n\n"
            "_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["hedef göster", "hedef", "hedef kanal göster"]:
        target_str = await get_setting("target_channel_id")
        if not target_str:
            await event.reply("❌ Hedef kanal ayarlanmamış.\n\n`hedef ayarla` yazarak ayarlayabilirsin.")
            return

        target_id = int(target_str)
        info = await get_channel_info(target_id)

        msg = "🎯 **Hedef Kanal:**\n\n"
        msg += f"• ID: `{info['id']}`\n"
        msg += f"• İsim: {info['title']}\n"
        if info['username']:
            msg += f"• Kullanıcı Adı: @{info['username']}\n"

        await event.reply(msg, parse_mode="markdown")
        return

    if text_lower in ["hedef sil", "hedef kaldır"]:
        await set_setting("target_channel_id", "")
        await event.reply("✅ Hedef kanal kaldırıldı!")
        return

    # TASLAK İŞLEMLERİ
    if text_lower in ["taslak ekle", "yeni taslak", "template ekle"]:
        user_states[user_id] = {"action": "add_template", "step": 1, "data": {}}
        await event.reply(
            "✉️ **Taslak Ekleme**\n\n"
            "**Adım 1/2:** Taslak için bir isim yaz.\n\n"
            "_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["taslaklar", "taslak listesi", "template listesi"]:
        templates = await list_templates()
        if not templates:
            await event.reply("📭 Henüz taslak yok.\n\n`taslak ekle` yazarak ekleyebilirsin.")
            return

        msg = "✉️ **Mesaj Taslakları:**\n\n"
        for t in templates:
            status = "✅" if t["is_active"] else "▫️"
            msg += f"{status} **{t['name']}**\n"
            preview = t['content'][:40] + "..." if len(t['content']) > 40 else t['content']
            msg += f"   _{preview}_\n\n"
        msg += f"**Toplam:** {len(templates)} taslak"

        await event.reply(msg, parse_mode="markdown")
        return

    if text_lower in ["taslak aktif", "aktif taslak", "taslak seç"]:
        templates = await list_templates()
        if not templates:
            await event.reply("❌ Önce taslak eklemelisin!")
            return
        user_states[user_id] = {"action": "set_template", "step": 1, "data": {}}
        names = "\n".join([f"• `{t['name']}`" for t in templates])
        await event.reply(
            f"✅ **Aktif Taslak Seçimi**\n\nAktif yapmak istediğin taslağın ismini yaz:\n\n{names}\n\n_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["taslak sil", "template sil"]:
        templates = await list_templates()
        if not templates:
            await event.reply("❌ Silinecek taslak yok!")
            return
        user_states[user_id] = {"action": "del_template", "step": 1, "data": {}}
        names = "\n".join([f"• `{t['name']}`" for t in templates])
        await event.reply(
            f"🗑 **Taslak Silme**\n\nSilmek istediğin taslağın ismini yaz:\n\n{names}\n\n_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    # YASAK KELİME İŞLEMLERİ
    if text_lower in ["yasak ekle", "ban ekle", "yasak kelime ekle"]:
        user_states[user_id] = {"action": "add_ban", "step": 1, "data": {}}
        await event.reply(
            "🚫 **Yasak Kelime Ekleme**\n\n"
            "Yasaklamak istediğin kelimeyi yaz.\n\n"
            "_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["yasak sil", "ban sil", "yasak kelime sil"]:
        banned = await get_banned_words()
        if not banned:
            await event.reply("❌ Silinecek yasak kelime yok!")
            return
        user_states[user_id] = {"action": "del_ban", "step": 1, "data": {}}
        words = "\n".join([f"• `{w}`" for w in banned])
        await event.reply(
            f"🔓 **Yasak Kelime Kaldırma**\n\nKaldırmak istediğin kelimeyi yaz:\n\n{words}\n\n_İptal: `iptal`_",
            parse_mode="markdown"
        )
        return

    if text_lower in ["yasaklar", "yasak listesi", "ban listesi"]:
        banned = await get_banned_words()
        if not banned:
            await event.reply("📭 Yasak kelime listesi boş.")
            return

        msg = "🚫 **Yasak Kelimeler:**\n\n"
        msg += "\n".join([f"• `{w}`" for w in banned])
        msg += f"\n\n**Toplam:** {len(banned)} kelime"

        await event.reply(msg, parse_mode="markdown")
        return

    # Tanınmayan komut
    await event.reply(
        "❓ Komutu anlamadım.\n\n"
        "`menü` yazarak tüm komutları görebilirsin."
    )


########################################
# STATE HANDLER
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
                f"❌ **Hata:** Kanal bulunamadı.\n\n`{str(e)}`\n\n"
                "Tekrar dene veya `iptal` yaz.",
                parse_mode="markdown"
            )
            log(f"Kanal eklenemedi: {e}", "ERROR")
            return

        await add_channel(cid, title)
        user_states.pop(user_id, None)
        log(f"Kanal eklendi: {cid} ({title})")
        await event.reply(
            f"✅ **Kanal eklendi!**\n\n"
            f"• ID: `{cid}`\n"
            f"• İsim: {title}",
            parse_mode="markdown"
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
                f"❌ **Hata:** Kanal bulunamadı.\n\n`{str(e)}`\n\n"
                "Tekrar dene veya `iptal` yaz.",
                parse_mode="markdown"
            )
            return

        await delete_channel(cid)
        user_states.pop(user_id, None)
        log(f"Kanal silindi: {cid}")
        await event.reply(
            f"🗑 **Kanal silindi!**\n\n• ID: `{cid}`",
            parse_mode="markdown"
        )
        return

    # HEDEF KANAL
    if action == "set_target" and step == 1:
        try:
            if text.startswith("@"):
                entity = await client.get_entity(text)
                cid = entity.id
                title = getattr(entity, "title", "Bilinmiyor")
            else:
                cid = int(text)
                entity = await client.get_entity(cid)
                title = getattr(entity, "title", "Bilinmiyor")
        except Exception as e:
            await event.reply(
                f"❌ **Hata:** Kanal bulunamadı.\n\n`{str(e)}`\n\n"
                "Tekrar dene veya `iptal` yaz.",
                parse_mode="markdown"
            )
            return

        await set_setting("target_channel_id", str(cid))
        user_states.pop(user_id, None)
        log(f"Hedef kanal ayarlandı: {cid} ({title})")
        await event.reply(
            f"🎯 **Hedef kanal ayarlandı!**\n\n"
            f"• ID: `{cid}`\n"
            f"• İsim: {title}",
            parse_mode="markdown"
        )
        return

    # TASLAK EKLE: İSİM
    if action == "add_template" and step == 1:
        data["name"] = text
        state["step"] = 2
        await event.reply(
            "✉️ **Taslak Ekleme**\n\n"
            f"**Adım 2/2:** `{text}` taslağı için mesaj içeriğini gönder.\n\n"
            "HTML, Markdown, emoji, link kullanabilirsin.\n"
            "Bu metin fotoğrafın caption'ı olarak kullanılacak.\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )
        return

    # TASLAK EKLE: İÇERİK
    if action == "add_template" and step == 2:
        name = data["name"]
        content = text
        await add_template(name, content)
        user_states.pop(user_id, None)
        log(f"Taslak eklendi: {name}")
        await event.reply(
            f"✅ **Taslak kaydedildi!**\n\n"
            f"• İsim: `{name}`\n\n"
            f"💡 Kullanmak için `taslak aktif` yazarak aktif etmeyi unutma.",
            parse_mode="markdown"
        )
        return

    # TASLAK AKTİF ET
    if action == "set_template" and step == 1:
        name = text
        await set_active_template(name)
        user_states.pop(user_id, None)
        log(f"Aktif taslak: {name}")
        await event.reply(
            f"✅ **Aktif taslak ayarlandı!**\n\n• `{name}`",
            parse_mode="markdown"
        )
        return

    # TASLAK SİL
    if action == "del_template" and step == 1:
        name = text
        await delete_template(name)
        user_states.pop(user_id, None)
        log(f"Taslak silindi: {name}")
        await event.reply(
            f"🗑 **Taslak silindi!**\n\n• `{name}`",
            parse_mode="markdown"
        )
        return

    # YASAK KELİME EKLE
    if action == "add_ban" and step == 1:
        word = text.strip()
        if not word:
            await event.reply("❌ Boş kelime olmaz. Tekrar yaz veya `iptal` et.")
            return
        await add_banned_word(word)
        user_states.pop(user_id, None)
        log(f"Yasak kelime eklendi: {word}")
        await event.reply(
            f"🚫 **Yasak kelime eklendi!**\n\n• `{word}`",
            parse_mode="markdown"
        )
        return

    # YASAK KELİME SİL
    if action == "del_ban" and step == 1:
        word = text.strip()
        await delete_banned_word(word)
        user_states.pop(user_id, None)
        log(f"Yasak kelime kaldırıldı: {word}")
        await event.reply(
            f"🔓 **Yasak kelime kaldırıldı!**\n\n• `{word}`",
            parse_mode="markdown"
        )
        return


########################################
# FOTOĞRAF DİNLEYİCİ - İYİLEŞTİRİLMİŞ
########################################

@client.on(events.NewMessage)
async def photo_listener(event):
    # Owner'ın özel mesajlarını dinleme
    if event.is_private and event.sender_id == OWNER_ID:
        return

    # Dinlenen kanallar
    channels = await get_channels()
    channel_ids = {c["id"] for c in channels}

    if event.chat_id not in channel_ids:
        return

    # FOTOĞRAF ÇIKART
    photo = extract_photo_from_message(event.message)

    if not photo:
        if DEBUG:
            log(f"Mesaj fotoğraf içermiyor (chat: {event.chat_id})", "DEBUG")
        return

    log(f"Fotoğraf algılandı: {event.chat_id} (msg: {event.id})")

    # YASAK KELİME KONTROLÜ
    caption = (event.message.message or "").lower()
    banned = await get_banned_words()

    for word in banned:
        if word and word.lower() in caption:
            log(f"ENGELLENDI - Yasak kelime: '{word}' | Chat: {event.chat_id}")
            return

    # HEDEF KANAL KONTROLÜ
    target_str = await get_setting("target_channel_id")
    if not target_str:
        log("UYARI: Hedef kanal ayarlanmamış!", "WARN")
        return

    target_id = int(target_str)

    # AKTİF TASLAK
    template = await get_active_template_content()
    if not template:
        template = "📸 Yeni fotoğraf"
        log("UYARI: Aktif taslak yok, varsayılan mesaj kullanılıyor", "WARN")

    # GÖNDER
    try:
        await client.send_file(
            target_id,
            file=photo,
            caption=template,
            parse_mode="html"
        )
        log(f"✓ GÖNDERILDI: {event.chat_id} → {target_id}")
    except Exception as e:
        log(f"HATA - Gönderilemedi: {e}", "ERROR")


########################################
# MAIN
########################################

async def main():
    log("Telegram'a bağlanılıyor...")
    await client.start()
    me = await client.get_me()
    log(f"Giriş yapıldı: {me.id} | @{me.username or 'yok'}")
    log("=" * 50)
    log("🤖 Bot aktif! Yönetim için 'menü' yaz.")
    log(f"Debug Mode: {DEBUG}")
    log("=" * 50)

    await asyncio.Future()


if __name__ == "__main__":
    client.loop.run_until_complete(main())
