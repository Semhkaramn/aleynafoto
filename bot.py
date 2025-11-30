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

# ÖNEMLİ: Keepalive ayarları (bot hiç durmasın)
KEEPALIVE_INTERVAL = 300  # 5 dakikada bir ping at (saniye)
AUTO_RECONNECT = True      # Bağlantı kopunca otomatik yeniden bağlan

########################################
# BOT DURUMU
########################################

bot_aktif = True  # Bot çalışıyor mu?
last_ping = None  # Son ping zamanı

stats = {
    "total_messages": 0,
    "photos_detected": 0,
    "photos_sent": 0,
    "photos_blocked": 0,
    "last_activity": None,
    "reconnect_count": 0,
    "keepalive_count": 0,
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
# KEEPALIVE - BOT HİÇ DURMASIN
########################################

async def keepalive_loop():
    """Botu canlı tut - Heroku dyno uyumasın"""
    global last_ping

    while True:
        try:
            await asyncio.sleep(KEEPALIVE_INTERVAL)

            # Ping gönder
            me = await client.get_me()
            last_ping = datetime.now()
            stats["keepalive_count"] += 1

            log(f"💓 Keepalive #{stats['keepalive_count']} - Bot aktif | User: {me.id}", "DEBUG")

            # Heroku dyno uyumasın diye kendine mesaj at (opsiyonel)
            # await client.send_message(OWNER_ID, f"💓 Ping #{stats['keepalive_count']}")

        except Exception as e:
            log(f"⚠️ Keepalive hatası: {e}", "WARN")

            if AUTO_RECONNECT:
                await reconnect_bot()

########################################
# AUTO RECONNECT - BAĞLANTI KOPUNCA YENİDEN BAĞLAN
########################################

async def reconnect_bot():
    """Bağlantı kopunca otomatik yeniden bağlan"""
    global client

    try:
        stats["reconnect_count"] += 1
        log(f"🔄 Yeniden bağlanılıyor... (#{stats['reconnect_count']})", "WARN")

        # Bağlantıyı kes
        if client.is_connected():
            await client.disconnect()

        # Biraz bekle
        await asyncio.sleep(5)

        # Yeniden bağlan
        await client.connect()

        # Doğrula
        me = await client.get_me()
        log(f"✅ Yeniden bağlandı: {me.id} | @{me.username or 'yok'}", "INFO")

        # Sahibine bildir
        try:
            await client.send_message(
                OWNER_ID,
                f"🔄 **Bot Yeniden Bağlandı**\n\n"
                f"• Bağlantı kopmuştu, otomatik düzeltildi\n"
                f"• Yeniden bağlanma sayısı: {stats['reconnect_count']}\n"
                f"• Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="markdown"
            )
        except:
            pass

    except Exception as e:
        log(f"❌ Yeniden bağlanma hatası: {e}", "ERROR")
        # 30 saniye sonra tekrar dene
        await asyncio.sleep(30)
        await reconnect_bot()

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
    uptime = datetime.now() - stats.get("start_time", datetime.now())

    msg = "📊 **Bot Durumu**\n\n"
    msg += f"🔄 Durum: {'✅ Aktif' if bot_aktif else '⏸️ Durdu'}\n"
    msg += f"🌐 Bağlantı: {'✅ Bağlı' if client.is_connected() else '❌ Kopuk'}\n"
    msg += f"⏱ Çalışma Süresi: {uptime.days}g {uptime.seconds//3600}s\n"
    msg += f"📡 Dinlenen Kanal: **{len(KAYNAK_KANALLAR)}**\n"
    msg += f"🎯 Hedef Kanal: `{HEDEF_KANAL}`\n"
    msg += f"🚫 Yasak Kelime: **{len(YASAK_KELIMELER)}**\n\n"

    msg += "📈 **İstatistikler:**\n"
    msg += f"📨 Toplam Mesaj: {stats['total_messages']}\n"
    msg += f"📷 Algılanan Foto: {stats['photos_detected']}\n"
    msg += f"✅ Gönderilen Foto: {stats['photos_sent']}\n"
    msg += f"🚫 Engellenen Foto: {stats['photos_blocked']}\n"
    msg += f"💓 Keepalive: {stats['keepalive_count']}\n"
    msg += f"🔄 Yeniden Bağlanma: {stats['reconnect_count']}\n"

    if stats['last_activity']:
        time_diff = datetime.now() - stats['last_activity']
        minutes = time_diff.seconds // 60
        msg += f"\n🕐 Son Aktivite: {minutes} dakika önce"

    if last_ping:
        ping_diff = datetime.now() - last_ping
        msg += f"\n💓 Son Ping: {ping_diff.seconds} saniye önce"

    await event.reply(msg, parse_mode="markdown")

@client.on(events.NewMessage(from_users=OWNER_ID, pattern=r"^(ping|test)$"))
async def ping_komutu(event):
    """Bot canlı mı kontrol et"""
    start = datetime.now()
    msg = await event.reply("🏓 Pong!")
    end = datetime.now()

    ping_time = (end - start).total_seconds() * 1000

    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"• Gecikme: {ping_time:.0f}ms\n"
        f"• Durum: {'✅ Çalışıyor' if bot_aktif else '⏸️ Durdu'}\n"
        f"• Bağlantı: {'✅ Aktif' if client.is_connected() else '❌ Yok'}",
        parse_mode="markdown"
    )

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

    # Gönder (hata yakalama ile)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            log(f"📤 Gönderiliyor: {HEDEF_KANAL} (Deneme {attempt + 1}/{max_retries})", "INFO")

            await client.send_file(
                HEDEF_KANAL,
                file=photo,
                caption=MESAJ_TASLAGI,
                parse_mode="html"
            )

            stats["photos_sent"] += 1
            log(f"✅ Gönderildi! Toplam: {stats['photos_sent']}", "INFO")
            break  # Başarılı, döngüden çık

        except Exception as e:
            log(f"❌ Gönderme hatası (Deneme {attempt + 1}): {e}", "ERROR")

            if attempt < max_retries - 1:
                await asyncio.sleep(5)  # 5 saniye bekle
            else:
                log("❌ Maksimum deneme aşıldı, foto gönderilemedi", "ERROR")

                # Bağlantı sorunu olabilir, yeniden bağlan
                if AUTO_RECONNECT:
                    await reconnect_bot()

########################################
# MAIN
########################################

async def main():
    global stats

    log("=" * 60)
    log("🚀 Bot başlatılıyor...")
    log("=" * 60)

    # Başlangıç zamanı
    stats["start_time"] = datetime.now()

    # Telegram'a bağlan
    try:
        log("📡 Telegram'a bağlanılıyor...")
        await client.start()
        me = await client.get_me()

        log(f"✅ Giriş yapıldı: {me.id} | @{me.username or 'yok'}")
    except Exception as e:
        log(f"❌ Bağlantı hatası: {e}", "ERROR")
        return

    log("=" * 60)
    log("📋 YAPILANDIRMA")
    log("=" * 60)
    log(f"📡 Dinlenen kanal: {len(KAYNAK_KANALLAR)}")
    for i, ch in enumerate(KAYNAK_KANALLAR, 1):
        log(f"   {i}. {ch}")
    log(f"🎯 Hedef kanal: {HEDEF_KANAL}")
    log(f"🚫 Yasak kelime: {len(YASAK_KELIMELER)}")
    log(f"💓 Keepalive: Her {KEEPALIVE_INTERVAL} saniyede bir")
    log(f"🔄 Auto-reconnect: {'✅ Aktif' if AUTO_RECONNECT else '❌ Kapalı'}")
    log("=" * 60)
    log("📝 KOMUTLAR")
    log("=" * 60)
    log("   • durdur - Fotoğraf göndermeyi durdur")
    log("   • başlat - Fotoğraf göndermeyi başlat")
    log("   • durum  - Bot durumunu göster")
    log("   • ping   - Bot canlı mı test et")
    log("=" * 60)
    log("✅ Bot aktif ve çalışıyor!")
    log("💓 Keepalive aktif - Bot hiç durmayacak!")
    log("🔄 Auto-reconnect aktif - Bağlantı kopunca otomatik düzelir!")
    log("=" * 60)

    # Sahibine bildirim gönder
    try:
        await client.send_message(
            OWNER_ID,
            f"🤖 **Bot Başlatıldı!**\n\n"
            f"• Dinlenen Kanal: {len(KAYNAK_KANALLAR)}\n"
            f"• Hedef Kanal: `{HEDEF_KANAL}`\n"
            f"• Keepalive: ✅ Aktif\n"
            f"• Auto-reconnect: ✅ Aktif\n\n"
            f"Bot hiç durmayacak ve bağlantı kopunca otomatik düzelecek! 🚀",
            parse_mode="markdown"
        )
    except:
        pass

    # Keepalive loop'u başlat (arka planda)
    asyncio.create_task(keepalive_loop())

    # Sonsuz döngü - bot hiç kapanmasın
    await asyncio.Future()

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        log("⚠️ Bot manuel olarak durduruldu (Ctrl+C)", "WARN")
    except Exception as e:
        log(f"❌ Kritik hata: {e}", "ERROR")
        # Hata olsa bile yeniden başlat
        if AUTO_RECONNECT:
            log("🔄 5 saniye sonra yeniden başlatılıyor...", "INFO")
            import time
            time.sleep(5)
            os.execv(__file__, [__file__])  # Kendini yeniden başlat
