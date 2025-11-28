import os
import asyncio
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PhotoSize
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

# Soru-cevap akışları için basit state
user_states = {}

# Debug mode
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
# MENÜ SİSTEMİ
########################################

async def show_main_menu(event):
    """Ana menüyü göster"""
    text = (
        "🤖 **Telegram Fotoğraf Yönetim Botu**\n\n"
        "Aşağıdaki butonları kullanarak botu yönetebilirsin.\n"
        "Fotoğraf dinleme, yasak kelime filtreleme ve otomatik paylaşım özellikleri mevcut."
    )

    buttons = [
        [Button.inline("📡 Kanallar", b"menu_channels")],
        [Button.inline("🎯 Hedef Kanal", b"menu_target")],
        [Button.inline("✉️ Mesaj Taslakları", b"menu_templates")],
        [Button.inline("🚫 Yasak Kelimeler", b"menu_banned")],
        [Button.inline("📊 Sistem Durumu", b"menu_status")],
        [Button.inline("❓ Yardım", b"menu_help")]
    ]

    await event.reply(text, buttons=buttons, parse_mode="markdown")


async def show_channels_menu(event):
    """Kanal yönetim menüsü"""
    channels = await get_channels()

    text = "📡 **Dinlenen Kanallar**\n\n"
    if channels:
        for c in channels:
            text += f"• `{c['id']}` - {c['title'] or 'İsimsiz'}\n"
    else:
        text += "_Henüz dinlenen kanal yok._\n"

    text += f"\n**Toplam:** {len(channels)} kanal"

    buttons = [
        [Button.inline("➕ Kanal Ekle", b"add_channel")],
        [Button.inline("➖ Kanal Sil", b"del_channel")],
        [Button.inline("🔄 Listeyi Yenile", b"menu_channels")],
        [Button.inline("◀️ Ana Menü", b"menu_main")]
    ]

    await event.edit(text, buttons=buttons, parse_mode="markdown")


async def show_target_menu(event):
    """Hedef kanal menüsü"""
    target_str = await get_setting("target_channel_id")

    text = "🎯 **Hedef Kanal Ayarları**\n\n"

    if target_str:
        target_id = int(target_str)
        info = await get_channel_info(target_id)
        text += f"✅ **Mevcut Hedef Kanal:**\n"
        text += f"• ID: `{info['id']}`\n"
        text += f"• İsim: {info['title']}\n"
        if info['username']:
            text += f"• Kullanıcı Adı: @{info['username']}\n"
    else:
        text += "❌ Hedef kanal ayarlanmamış.\n\n"
        text += "Dinlenen kanallardan gelen fotoğraflar buraya gönderilecek."

    buttons = [
        [Button.inline("✏️ Hedef Kanalı Değiştir", b"set_target")],
    ]

    if target_str:
        buttons.append([Button.inline("🗑 Hedef Kanalı Kaldır", b"remove_target")])

    buttons.append([Button.inline("◀️ Ana Menü", b"menu_main")])

    await event.edit(text, buttons=buttons, parse_mode="markdown")


async def show_templates_menu(event):
    """Taslak menüsü"""
    templates = await list_templates()

    text = "✉️ **Mesaj Taslakları**\n\n"

    if templates:
        for t in templates:
            status = "✅" if t["is_active"] else "▫️"
            text += f"{status} **{t['name']}**\n"
            preview = t['content'][:50] + "..." if len(t['content']) > 50 else t['content']
            text += f"   _{preview}_\n\n"
    else:
        text += "_Henüz taslak yok._\n"

    text += f"\n**Toplam:** {len(templates)} taslak"

    buttons = [
        [Button.inline("➕ Taslak Ekle", b"add_template")],
        [Button.inline("✅ Aktif Taslak Seç", b"set_template")],
        [Button.inline("🗑 Taslak Sil", b"del_template")],
        [Button.inline("🔄 Listeyi Yenile", b"menu_templates")],
        [Button.inline("◀️ Ana Menü", b"menu_main")]
    ]

    await event.edit(text, buttons=buttons, parse_mode="markdown")


async def show_banned_menu(event):
    """Yasak kelime menüsü"""
    banned = await get_banned_words()

    text = "🚫 **Yasak Kelime Listesi**\n\n"

    if banned:
        for word in banned:
            text += f"• `{word}`\n"
    else:
        text += "_Yasak kelime yok._\n"

    text += f"\n**Toplam:** {len(banned)} kelime"

    buttons = [
        [Button.inline("➕ Kelime Ekle", b"add_banned")],
        [Button.inline("➖ Kelime Sil", b"del_banned")],
        [Button.inline("🔄 Listeyi Yenile", b"menu_banned")],
        [Button.inline("◀️ Ana Menü", b"menu_main")]
    ]

    await event.edit(text, buttons=buttons, parse_mode="markdown")


async def show_status_menu(event):
    """Sistem durumu"""
    channels = await get_channels()
    templates = await list_templates()
    banned = await get_banned_words()
    target_str = await get_setting("target_channel_id")
    active_tpl = await get_active_template_content()

    text = "📊 **Sistem Durumu**\n\n"

    text += f"📡 Dinlenen Kanal: **{len(channels)}**\n"
    text += f"🎯 Hedef Kanal: {'✅ Ayarlı' if target_str else '❌ Yok'}\n"
    text += f"✉️ Mesaj Taslağı: **{len(templates)}**\n"
    text += f"✅ Aktif Taslak: {'Var' if active_tpl else 'Yok'}\n"
    text += f"🚫 Yasak Kelime: **{len(banned)}**\n"
    text += f"🤖 Bot Durumu: ✅ Çalışıyor\n"
    text += f"🔧 Debug Mode: {'🟢 Açık' if DEBUG else '🔴 Kapalı'}\n"

    buttons = [
        [Button.inline("🔄 Yenile", b"menu_status")],
        [Button.inline("◀️ Ana Menü", b"menu_main")]
    ]

    await event.edit(text, buttons=buttons, parse_mode="markdown")


async def show_help_menu(event):
    """Yardım menüsü"""
    text = (
        "❓ **Yardım ve Kullanım Kılavuzu**\n\n"
        "**🎯 Bot Nasıl Çalışır?**\n"
        "1. Dinlenen kanallara fotoğraf geldiğinde algılar\n"
        "2. Yasak kelime kontrolü yapar\n"
        "3. Fotoğrafı hedef kanala aktif taslakla gönderir\n\n"

        "**📋 Hızlı Başlangıç:**\n"
        "• Dinlenecek kanalları ekle\n"
        "• Hedef kanalı ayarla\n"
        "• Mesaj taslağı oluştur ve aktif et\n"
        "• İsteğe bağlı yasak kelime ekle\n\n"

        "**💡 Metin Komutları:**\n"
        "`menü` - Ana menüyü göster\n"
        "`iptal` - İşlemi iptal et\n"
        "`durum` - Sistem durumunu göster\n\n"

        "**⚠️ Önemli Notlar:**\n"
        "• Bot sadece fotoğraf içeren mesajları algılar\n"
        "• Yasak kelime caption içinde aranır\n"
        "• Taslak HTML/Markdown destekler\n"
    )

    buttons = [
        [Button.inline("◀️ Ana Menü", b"menu_main")]
    ]

    await event.edit(text, buttons=buttons, parse_mode="markdown")


########################################
# CALLBACK QUERY HANDLER (BUTONLAR)
########################################

@client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")
    user_id = event.sender_id

    # Sadece owner kullanabilir
    if user_id != OWNER_ID:
        await event.answer("⛔ Bu botu sadece sahibi kullanabilir!", alert=True)
        return

    # Menüler
    if data == "menu_main":
        await show_main_menu(event)
    elif data == "menu_channels":
        await show_channels_menu(event)
    elif data == "menu_target":
        await show_target_menu(event)
    elif data == "menu_templates":
        await show_templates_menu(event)
    elif data == "menu_banned":
        await show_banned_menu(event)
    elif data == "menu_status":
        await show_status_menu(event)
    elif data == "menu_help":
        await show_help_menu(event)

    # İşlemler
    elif data == "add_channel":
        user_states[user_id] = {"action": "add_channel", "step": 1, "data": {}}
        await event.edit(
            "📡 **Kanal Ekleme**\n\n"
            "Dinlenecek kanalın kullanıcı adını (`@kanaladi`) veya ID'sini (`-100...`) yaz.\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "del_channel":
        channels = await get_channels()
        if not channels:
            await event.answer("❌ Silinecek kanal yok!", alert=True)
            return
        user_states[user_id] = {"action": "del_channel", "step": 1, "data": {}}
        await event.edit(
            "🗑 **Kanal Silme**\n\n"
            "Silmek istediğin kanalın kullanıcı adını (`@kanal`) veya ID'sini (`-100...`) yaz.\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "set_target":
        user_states[user_id] = {"action": "set_target", "step": 1, "data": {}}
        await event.edit(
            "🎯 **Hedef Kanal Ayarlama**\n\n"
            "Fotoğrafların gönderileceği kanalın kullanıcı adını (`@kanal`) veya ID'sini (`-100...`) yaz.\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "remove_target":
        await set_setting("target_channel_id", "")
        await event.answer("✅ Hedef kanal kaldırıldı!", alert=True)
        await show_target_menu(event)

    elif data == "add_template":
        user_states[user_id] = {"action": "add_template", "step": 1, "data": {}}
        await event.edit(
            "✉️ **Taslak Ekleme**\n\n"
            "**Adım 1/2:** Taslak için bir isim yaz.\n\n"
            "Örnek: `VIP Taslak`, `Standart Mesaj`\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "set_template":
        templates = await list_templates()
        if not templates:
            await event.answer("❌ Önce taslak eklemelisin!", alert=True)
            return
        user_states[user_id] = {"action": "set_template", "step": 1, "data": {}}
        names = "\n".join([f"• `{t['name']}`" for t in templates])
        await event.edit(
            "✅ **Aktif Taslak Seçimi**\n\n"
            f"Aktif yapmak istediğin taslağın ismini yaz:\n\n{names}\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "del_template":
        templates = await list_templates()
        if not templates:
            await event.answer("❌ Silinecek taslak yok!", alert=True)
            return
        user_states[user_id] = {"action": "del_template", "step": 1, "data": {}}
        names = "\n".join([f"• `{t['name']}`" for t in templates])
        await event.edit(
            "🗑 **Taslak Silme**\n\n"
            f"Silmek istediğin taslağın ismini yaz:\n\n{names}\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "add_banned":
        user_states[user_id] = {"action": "add_ban", "step": 1, "data": {}}
        await event.edit(
            "🚫 **Yasak Kelime Ekleme**\n\n"
            "Yasaklamak istediğin kelimeyi yaz.\n\n"
            "Bu kelime caption içinde geçerse fotoğraf paylaşılmaz.\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    elif data == "del_banned":
        banned = await get_banned_words()
        if not banned:
            await event.answer("❌ Silinecek kelime yok!", alert=True)
            return
        user_states[user_id] = {"action": "del_ban", "step": 1, "data": {}}
        words = "\n".join([f"• `{w}`" for w in banned])
        await event.edit(
            "🔓 **Yasak Kelime Kaldırma**\n\n"
            f"Kaldırmak istediğin kelimeyi yaz:\n\n{words}\n\n"
            "_İptal etmek için: `iptal`_",
            parse_mode="markdown"
        )

    await event.answer()


########################################
# OWNER MESAJLARI
########################################

@client.on(events.NewMessage(from_users=OWNER_ID))
async def owner_commands(event):
    user_id = event.sender_id
    raw_text = event.raw_text or ""
    text = raw_text.strip()
    text_lower = text.lower().lstrip("/")

    # İptal
    if text_lower in ["iptal", "cancel"]:
        user_states.pop(user_id, None)
        await event.reply("❌ İşlem iptal edildi.", buttons=[[Button.inline("◀️ Ana Menü", b"menu_main")]])
        return

    # Devam eden akış varsa işle
    state = user_states.get(user_id)
    if state:
        await handle_state(event, state)
        return

    # Menü komutları
    if text_lower in ["menu", "menü", "start", "baslat", "/start"]:
        await show_main_menu(event)
        return

    if text_lower in ["durum", "status", "info"]:
        # Buton olmadan durum göster
        channels = await get_channels()
        templates = await list_templates()
        banned = await get_banned_words()
        target_str = await get_setting("target_channel_id")

        msg = "📊 **Hızlı Durum:**\n"
        msg += f"📡 {len(channels)} kanal dinleniyor\n"
        msg += f"🎯 Hedef: {'✅' if target_str else '❌'}\n"
        msg += f"✉️ {len(templates)} taslak\n"
        msg += f"🚫 {len(banned)} yasak kelime\n"

        await event.reply(msg, parse_mode="markdown", buttons=[[Button.inline("📊 Detaylı Durum", b"menu_status")]])
        return

    if text_lower in ["yardım", "help", "?", "yardim"]:
        await show_help_menu(event)
        return

    # Tanınmayan komut
    await event.reply(
        "❓ Ne yapmak istediğini anlamadım.\n\n"
        "Menüyü görmek için `menü` yaz.",
        buttons=[[Button.inline("🤖 Menüyü Aç", b"menu_main")]]
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
            f"ID: `{cid}`\n"
            f"İsim: {title}",
            parse_mode="markdown",
            buttons=[[Button.inline("📡 Kanallara Dön", b"menu_channels")]]
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
            f"🗑 **Kanal silindi!**\n\nID: `{cid}`",
            parse_mode="markdown",
            buttons=[[Button.inline("📡 Kanallara Dön", b"menu_channels")]]
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
            f"ID: `{cid}`\n"
            f"İsim: {title}",
            parse_mode="markdown",
            buttons=[[Button.inline("🎯 Hedef Kanala Dön", b"menu_target")]]
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
            f"İsim: `{name}`\n\n"
            f"Kullanmak için aktif etmeyi unutma.",
            parse_mode="markdown",
            buttons=[[Button.inline("✉️ Taslak Menüsü", b"menu_templates")]]
        )
        return

    # TASLAK AKTİF ET
    if action == "set_template" and step == 1:
        name = text
        await set_active_template(name)
        user_states.pop(user_id, None)
        log(f"Aktif taslak: {name}")
        await event.reply(
            f"✅ **Aktif taslak ayarlandı!**\n\n`{name}`",
            parse_mode="markdown",
            buttons=[[Button.inline("✉️ Taslak Menüsü", b"menu_templates")]]
        )
        return

    # TASLAK SİL
    if action == "del_template" and step == 1:
        name = text
        await delete_template(name)
        user_states.pop(user_id, None)
        log(f"Taslak silindi: {name}")
        await event.reply(
            f"🗑 **Taslak silindi!**\n\n`{name}`",
            parse_mode="markdown",
            buttons=[[Button.inline("✉️ Taslak Menüsü", b"menu_templates")]]
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
            f"🚫 **Yasak kelime eklendi!**\n\n`{word}`",
            parse_mode="markdown",
            buttons=[[Button.inline("🚫 Yasak Kelimeler", b"menu_banned")]]
        )
        return

    # YASAK KELİME SİL
    if action == "del_ban" and step == 1:
        word = text.strip()
        await delete_banned_word(word)
        user_states.pop(user_id, None)
        log(f"Yasak kelime kaldırıldı: {word}")
        await event.reply(
            f"🔓 **Yasak kelime kaldırıldı!**\n\n`{word}`",
            parse_mode="markdown",
            buttons=[[Button.inline("🚫 Yasak Kelimeler", b"menu_banned")]]
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
