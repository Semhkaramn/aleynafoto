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
# AYARLAR
########################################

KAYNAK_KANALLAR = [
    -1001702869083,
    -1002214278617,
    -1001885502015,
    -1002379522248
]

HEDEF_KANAL = -1002560312226

MESAJ_TASLAGI = """<b>Uyarı :</b>  Lütfen Kendinizi Üzmeyecek Miktarda Bahis Alınız!

<i>Güvenilir Sponsorlar için mocobey4.com</i>"""

YASAK_KELIMELER = [
    "bonus",
    "fırsat",
    "freespin",
    "kayıt",
]

islenen = set()
foto_hash_cache = set()
bot_aktif = True

########################################
# HEROKU KEEPALIVE
########################################

async def keepalive_loop():
    while True:
        try:
            await asyncio.sleep(180)
            await client.get_dialogs(limit=1)
            print(f"[KEEPALIVE] ✅ Ping - {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[KEEPALIVE HATA] {e}")
            await asyncio.sleep(60)

########################################
# FOTOĞRAF ÇIKART
########################################

def extract_photo(msg):
    if msg.photo:
        return msg.photo

    if msg.media:
        if isinstance(msg.media, MessageMediaPhoto):
            return msg.media.photo

        if isinstance(msg.media, MessageMediaDocument):
            if msg.media.document.mime_type.startswith("image/"):
                return msg.media

        if hasattr(msg.media, "photo"):
            return msg.media.photo

    return None

########################################
# KOMUTLAR
########################################

@client.on(events.NewMessage(from_users=OWNER_ID, pattern="^(dur|stop)$"))
async def komut_dur(event):
    global bot_aktif
    bot_aktif = False
    await event.reply("⏸ Bot durduruldu.")
    print(f"[KOMUT] ⏸ Durduruldu - {datetime.now().strftime('%H:%M:%S')}")

@client.on(events.NewMessage(from_users=OWNER_ID, pattern="^(devam|start)$"))
async def komut_devam(event):
    global bot_aktif
    bot_aktif = True
    await event.reply("▶ Bot devam ediyor.")
    print(f"[KOMUT] ▶ Devam - {datetime.now().strftime('%H:%M:%S')}")

########################################
# ANA DİNLEYİCİ
########################################

@client.on(events.NewMessage(incoming=True, func=lambda e: not e.out))
async def dinleyici(event):

    if not bot_aktif:
        return

    # Özel mesajları atla
    if event.is_private:
        return

        # Kaynak kanallardan değilse atla
    if event.chat_id not in KAYNAK_KANALLAR:
        return
    # DEBUG: Hangi kanaldan mesaj geldi?
    print(f"[DEBUG] Mesaj geldi -> Kanal: {event.chat_id} | #{event.id}")

    # Kaynak kanallardan değilse atla
    if event.chat_id not in KAYNAK_KANALLAR:
        return

    # Mesaj kontrolü
    key = (event.chat_id, event.id)
    if key in islenen:
        return
    islenen.add(key)

    if len(islenen) > 10000:
        islenen.clear()

    # Fotoğraf var mı?
    foto = extract_photo(event.message)
    if not foto:
        return

    # Fotoğraf hash kontrolü
    foto_id = getattr(foto, 'id', None)
    if not foto_id and hasattr(foto, 'document'):
        foto_id = getattr(foto.document, 'id', None)

    if foto_id:
        if foto_id in foto_hash_cache:
            print(f"[ATLA] ⏭ Aynı fotoğraf (ID: {foto_id})")
            return
        foto_hash_cache.add(foto_id)

        if len(foto_hash_cache) > 1000:
            foto_hash_cache.clear()

    # Yasak kelime kontrolü
    caption = (event.message.message or "").lower()
    for kelime in YASAK_KELIMELER:
        if kelime in caption:
            print(f"[ATLA] ⚠️ Yasak kelime: {kelime}")
            return

    # Gönder
    try:
        await client.send_file(
            HEDEF_KANAL,
            file=foto,
            caption=MESAJ_TASLAGI,
            parse_mode="html"
        )
        print(f"[OK] ✅ Foto gönderildi | Kanal: {event.chat_id} | #{event.id} | {datetime.now().strftime('%H:%M:%S')}")
        await asyncio.sleep(1)

    except Exception as e:
        err = str(e).lower()

        # Protected içerik
        if "protected" in err or "can't forward" in err:
            try:
                print(f"[INFO] 🔒 Protected içerik indiriliyor...")
                data = await client.download_media(foto, file=bytes)
                await client.send_file(
                    HEDEF_KANAL,
                    file=data,
                    caption=MESAJ_TASLAGI,
                    parse_mode="html"
                )
                print(f"[OK] ✅ Protected çözüldü | #{event.id}")
                await asyncio.sleep(1)
            except Exception as e2:
                print(f"[HATA] ❌ Protected indirilemedi: {e2}")

        # Flood
        elif "flood" in err or "wait" in err:
            print(f"[UYARI] ⚠️ Flood - 30 sn bekleniyor...")
            await asyncio.sleep(30)

        else:
            print(f"[HATA] ❌ {e}")

########################################
# MAIN
########################################

async def main():
    yeniden_baglanti = 0

    while True:
        try:
            print(f"\n{'='*50}")
            print(f"[BAŞLAT] Bot başlatılıyor...")
            print(f"{'='*50}\n")

            await client.start()

            print(f"[OK] ✅ Bot aktif! | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[INFO] İzlenen kanal: {len(KAYNAK_KANALLAR)} adet")
            print(f"[INFO] Kanal ID'leri:")
            for kanal in KAYNAK_KANALLAR:
                print(f"       - {kanal}")
            print(f"[INFO] Hedef: {HEDEF_KANAL}")
            print(f"[INFO] Keepalive: 3 dakika\n")

            yeniden_baglanti = 0

            asyncio.create_task(keepalive_loop())

            await asyncio.Future()

        except KeyboardInterrupt:
            print("\n[STOP] ⏹ Manuel durduruldu.")
            break

        except Exception as e:
            yeniden_baglanti += 1
            print(f"\n{'='*50}")
            print(f"[HATA] ❌ Bağlantı koptu: {e}")
            print(f"[INFO] Deneme #{yeniden_baglanti}")
            print(f"{'='*50}\n")

            bekle = min(10 * yeniden_baglanti, 60)
            print(f"[BEKLE] ⏳ {bekle} saniye...\n")
            await asyncio.sleep(bekle)

            try:
                await client.disconnect()
            except:
                pass

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[SON] Kapatıldı.")
