import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

API_ID = int(os.getenv("API_ID", "22758433"))
API_HASH = os.getenv("API_HASH", "63ea3a90dec2b1926f728fdd2db84e33")
SESSION = os.getenv("SESSION", "ejder.session")
OWNER_ID = int(os.getenv("OWNER_ID", "5725763398"))

client = TelegramClient(SESSION, API_ID, API_HASH)

########################################
# YAPILANDIRMA - BURADAN DÜZENLEYİN
########################################

# Dinlenecek kanallar (ID veya @username)
KAYNAK_KANALLAR = [
    -1002597541903,
    -1001702869083,
    -1002214278617,


]

# Hedef kanal (fotoğrafların gönderileceği yer)
HEDEF_KANAL = -1002560312226  

# Mesaj taslağı
MESAJ_TASLAGI = """<b>Uyarı :</b>  Lütfen Kendinizi Üzmeyecek Miktarda Bahis Alınız!

<i>Güvenilir Sponsorlar için mocobey4.com</i>"""

# Yasak kelimeler
YASAK_KELIMELER = [
    "bonus",
    "fırsat",
    "freespin",
    "kayıt",
    # Daha fazla ekleyebilirsiniz
]

########################################
# BOT DURUMU
########################################

bot_aktif = True  # Bot çalışıyor mu?

stats = {
    "total_messages": 0,
    "photos_detected": 0,
    "photos_sent": 0,
    "photos_blocked": 0,
    "last_activity": None
}

########################################
# LOGGER
########################################

def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

########################################
# ID NORMALIZE
########################################

def normalize_channel_id(channel_id: int) -> int:
    """Telegram kanal ID'lerini normalize et"""
    channel_id = int(channel_id)

    if str(channel_id).startswith("-100"):
        return channel_id

    if channel_id > 0:
        return -1000000000000 - channel_id

    if channel_id < 0 and not str(channel_id).startswith("-100"):
        return -1000000000000 - abs(channel_id)

    return channel_id

########################################
# FOTO ÇIKARTMA
########################################

def extract_photo_from_message(message):
    """Mesajdan fotoğraf çıkart"""

    # 1. Direkt foto
    if message.photo:
        return message.photo

    # 2. Media kontrolü
    if not message.media:
        return None

    # 3. MessageMediaPhoto
    if isinstance(message.media, MessageMediaPhoto):
        return message.media.photo

    # 4. Document içinde resim
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            mime = getattr(doc, "mime_type", "")
            if mime.startswith("image/"):
                return message.media

    # 5. Genel media.photo
    if hasattr(message.media, "photo"):
        return message.media.photo

    # 6. WebPage içinde foto
    if hasattr(message.media, "webpage"):
        webpage = message.media.webpage
        if hasattr(webpage, "photo") and webpage.photo:
            return webpage.photo

    return None

########################################
# OWNER KOMUTLARI
########################################

@client.on(events.NewMessage(from_users=OWNER_ID, pattern=r"^(durdur|dur|stop)$"))
async def durdur_komutu(event):
    global bot_aktif
    bot_aktif = False
    log("⏸️ Bot durduruldu!", "WARN")
    await event.reply(
        "⏸️ **Bot Durduruldu**\n\n"
        "Fotoğraf gönderimi durduruldu.\n"
        "Tekrar başlatmak için: `başlat`",
        parse_mode="markdown"
    )

@client.on(events.NewMessage(from_users=OWNER_ID, pattern=r"^(başlat|start|devam)$"))
async def baslat_komutu(event):
    global bot_aktif
    bot_aktif = True
    log("▶️ Bot başlatıldı!", "INFO")
    await event.reply(
        "▶️ **Bot Başlatıldı**\n\n"
        "Fotoğraf gönderimi aktif.\n"
        "Durdurmak için: `durdur`",
        parse_mode="markdown"
    )

@client.on(events.NewMessage(from_users=OWNER_ID, pattern=r"^(durum|status|info)$"))
async def durum_komutu(event):
    msg = "📊 **Bot Durumu**\n\n"
    msg += f"🔄 Durum: {'✅ Aktif' if bot_aktif else '⏸️ Durdu'}\n"
    msg += f"📡 Dinlenen Kanal: **{len(KAYNAK_KANALLAR)}**\n"
    msg += f"🎯 Hedef Kanal: `{HEDEF_KANAL}`\n"
    msg += f"🚫 Yasak Kelime: **{len(YASAK_KELIMELER)}**\n\n"

    msg += "📈 **İstatistikler:**\n"
    msg += f"📨 Toplam Mesaj: {stats['total_messages']}\n"
    msg += f"📷 Algılanan Foto: {stats['photos_detected']}\n"
    msg += f"✅ Gönderilen Foto: {stats['photos_sent']}\n"
    msg += f"🚫 Engellenen Foto: {stats['photos_blocked']}\n"

    if stats['last_activity']:
        time_diff = datetime.now() - stats['last_activity']
        msg += f"\n🕐 Son Aktivite: {time_diff.seconds} saniye önce"

    await event.reply(msg, parse_mode="markdown")

########################################
# FOTOĞRAF DİNLEYİCİ
########################################

@client.on(events.NewMessage)
async def photo_listener(event):
    # Owner'ın özel mesajlarını dinleme
    if event.is_private and event.sender_id == OWNER_ID:
        return

    # İstatistik
    stats["total_messages"] += 1
    stats["last_activity"] = datetime.now()

    # Bot durdu mu?
    if not bot_aktif:
        return

    # Kaynak kanalları normalize et
    normalized_sources = [normalize_channel_id(ch) for ch in KAYNAK_KANALLAR]
    normalized_chat_id = normalize_channel_id(event.chat_id)

    # Kanal kontrolü
    if normalized_chat_id not in normalized_sources:
        return

    log(f"✅ Kanal mesajı: {normalized_chat_id}", "INFO")

    # Fotoğraf çıkart
    photo = extract_photo_from_message(event.message)

    if not photo:
        return

    stats["photos_detected"] += 1
    log(f"📷 Fotoğraf algılandı: Mesaj {event.id}", "INFO")

    # Yasak kelime kontrolü
    caption = (event.message.message or "").lower()

    for word in YASAK_KELIMELER:
        if word and word.lower() in caption:
            stats["photos_blocked"] += 1
            log(f"🚫 Engellendi: Yasak kelime '{word}'", "WARN")
            return

    # Gönder
    try:
        log(f"📤 Gönderiliyor: {HEDEF_KANAL}", "INFO")

        await client.send_file(
            HEDEF_KANAL,
            file=photo,
            caption=MESAJ_TASLAGI,
            parse_mode="html"
        )

        stats["photos_sent"] += 1
        log(f"✅ Gönderildi! Toplam: {stats['photos_sent']}", "INFO")

    except Exception as e:
        log(f"❌ Hata: {e}", "ERROR")

########################################
# MAIN
########################################

async def main():
    log("Telegram'a bağlanılıyor...")
    await client.start()
    me = await client.get_me()

    log(f"Giriş yapıldı: {me.id} | @{me.username or 'yok'}")
    log("=" * 60)
    log("🤖 Bot aktif!")
    log(f"📡 Dinlenen kanal: {len(KAYNAK_KANALLAR)}")
    log(f"🎯 Hedef kanal: {HEDEF_KANAL}")
    log(f"🚫 Yasak kelime: {len(YASAK_KELIMELER)}")
    log("")
    log("📝 Komutlar:")
    log("   • durdur - Fotoğraf göndermeyi durdur")
    log("   • başlat - Fotoğraf göndermeyi başlat")
    log("   • durum - Bot durumunu göster")
    log("=" * 60)

    await asyncio.Future()

if __name__ == "__main__":
    client.loop.run_until_complete(main())
