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
    -1002379522248,
    -1002877621836
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

islenen = set()      # Aynı mesajı 2 kez işlemeyi engeller
foto_hash_cache = set()  # Aynı fotoğrafı 2 kez göndermemeyi engeller
bot_aktif = True     # /dur ve /devam için bot durumu

########################################
# HEROKU KEEPALIVE (İYİLEŞTİRİLDİ)
########################################

async def keepalive_loop():
    """Her 3 dakikada bir ping atar - Heroku uyumasın"""
    while True:
        try:
            await asyncio.sleep(180)  # 3 dk (daha sık kontrol)
            await client.get_dialogs(limit=1)  # Daha hafif işlem
            print(f"[KEEPALIVE] ✅ Ping OK - {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[KEEPALIVE HATA] ❌ {e}")
            await asyncio.sleep(60)  # Hata olursa 1 dk bekle

########################################
# YARDIMCI FONKS.
########################################

def normalize_channel_id(cid: int) -> int:
    cid = int(cid)
    if str(cid).startswith("-100"):
        return cid
    if cid > 0:
        return -1000000000000 - cid
    if cid < 0:
        return -1000000000000 - abs(cid)
    return cid

def extract_photo(msg):
    if msg.photo:
        return msg.photo

    if msg.media:
        if isinstance(msg.media, MessageMediaPhoto):
            return msg.media.photo

        if isinstance(msg.media, MessageMediaDocument):
            mime = getattr(msg.media.document, "mime_type", "")
            if mime.startswith("image/"):
                return msg.media

        if hasattr(msg.media, "photo"):
            return msg.media.photo

        if hasattr(msg.media, "webpage"):
            wp = msg.media.webpage
            if hasattr(wp, "photo") and wp.photo:
                return wp.photo

    return None

########################################
# DUR / DEVAM KOMUTLARI
########################################

@client.on(events.NewMessage(from_users=OWNER_ID, pattern="^(dur|stop)$"))
async def komut_dur(event):
    global bot_aktif
    bot_aktif = False
    await event.reply("⏸ Bot durduruldu.")
    print(f"[KOMUT] ⏸ Bot durduruldu - {datetime.now().strftime('%H:%M:%S')}")

@client.on(events.NewMessage(from_users=OWNER_ID, pattern="^(devam|start)$"))
async def komut_devam(event):
    global bot_aktif
    bot_aktif = True
    await event.reply("▶ Bot devam ediyor.")
    print(f"[KOMUT] ▶ Bot devam ediyor - {datetime.now().strftime('%H:%M:%S')}")

########################################
# FOTOĞRAF DİNLEYİCİ (İYİLEŞTİRİLDİ)
########################################

@client.on(events.NewMessage(incoming=True, func=lambda e: not e.out))
async def dinleyici(event):

    if not bot_aktif:
        return

    if event.is_private and event.sender_id == OWNER_ID:
        return

    cid_norm = normalize_channel_id(event.chat_id)
    kaynaklar = [normalize_channel_id(ch) for ch in KAYNAK_KANALLAR]

    if cid_norm not in kaynaklar:
        return

    # Aynı mesajı 2 kez işleme
    key = (cid_norm, event.id)
    if key in islenen:
        print(f"[ATLA] ⏭ Mesaj zaten işlendi: Kanal {cid_norm}, Mesaj #{event.id}")
        return
    islenen.add(key)

    # Cache temizliği
    if len(islenen) > 10000:
        islenen.clear()
        print("[INFO] 🧹 İşlenen mesaj cache'i temizlendi")

    foto = extract_photo(event.message)
    if not foto:
        return

    # Fotoğraf hash kontrolü - aynı fotoğrafı tekrar gönderme
    foto_id = None
    if hasattr(foto, 'id'):
        foto_id = foto.id
    elif hasattr(foto, 'document') and hasattr(foto.document, 'id'):
        foto_id = foto.document.id

    if foto_id:
        if foto_id in foto_hash_cache:
            print(f"[ATLA] ⏭ Aynı fotoğraf zaten gönderildi (ID: {foto_id})")
            return
        foto_hash_cache.add(foto_id)

        # Cache'i temizle (son 1000 fotoğraf)
        if len(foto_hash_cache) > 1000:
            foto_hash_cache.clear()

    caption = (event.message.message or "").lower()
    for w in YASAK_KELIMELER:
        if w in caption:
            print(f"[ATLA] ⚠️ Yasak kelime bulundu: {w}")
            return

    try:
        await client.send_file(
            HEDEF_KANAL,
            file=foto,
            caption=MESAJ_TASLAGI,
            parse_mode="html"
        )
        print(f"[OK] ✅ Foto gönderildi -> Kaynak: {cid_norm} | Mesaj #{event.id} | {datetime.now().strftime('%H:%M:%S')}")

        # Rate limiting: Her gönderim arası 1 saniye bekle
        await asyncio.sleep(1)

    except Exception as e:
        err = str(e).lower()

        if "protected" in err or "can't forward" in err:
            try:
                print(f"[INFO] Protected içerik algılandı, indiriliyor...")
                data = await client.download_media(foto, file=bytes)
                await client.send_file(
                    HEDEF_KANAL,
                    file=data,
                    caption=MESAJ_TASLAGI,
                    parse_mode="html"
                )
                print(f"[OK] ✅ Protected çözüldü -> Kaynak: {cid_norm} | Mesaj #{event.id}")
                await asyncio.sleep(1)  # Rate limiting

            except Exception as e2:
                print(f"[HATA] ❌ Protected indirilemedi: {e2}")

        elif "flood" in err or "wait" in err:
            print(f"[UYARI] ⚠️ Telegram rate limit - 30 sn bekleniyor...")
            await asyncio.sleep(30)

        else:
            print(f"[HATA] ❌ Gönderim hatası: {e}")

########################################
# MAIN (OTOMATİK YENİDEN BAĞLANMA)
########################################

async def main():
    """Otomatik yeniden bağlanma ile ana loop"""
    yeniden_baglanti_sayisi = 0

    while True:
        try:
            print(f"\n{'='*50}")
            print(f"[BAŞLATILIYOR] Bot başlatılıyor...")
            print(f"{'='*50}\n")

            await client.start()
            print(f"[OK] ✅ Bot aktif! | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[INFO] İzlenen kanal sayısı: {len(KAYNAK_KANALLAR)}")
            print(f"[INFO] Hedef kanal: {HEDEF_KANAL}")
            print(f"[INFO] Keepalive: Her 3 dakikada bir\n")

            yeniden_baglanti_sayisi = 0  # Başarılı bağlantıda sıfırla

            # Keepalive task'ını başlat
            asyncio.create_task(keepalive_loop())

            # Sonsuz döngü - bot kapanana kadar çalışır
            await asyncio.Future()

        except KeyboardInterrupt:
            print("\n[DURDURULDU] ⏹ Bot manuel olarak durduruldu.")
            break

        except Exception as e:
            yeniden_baglanti_sayisi += 1
            print(f"\n{'='*50}")
            print(f"[HATA] ❌ Bağlantı koptu: {e}")
            print(f"[INFO] Yeniden bağlanma denemesi: {yeniden_baglanti_sayisi}")
            print(f"{'='*50}\n")

            # Bekleme süresi: Her denemede artan süre (max 60 sn)
            bekleme_suresi = min(10 * yeniden_baglanti_sayisi, 60)
            print(f"[BEKLE] ⏳ {bekleme_suresi} saniye sonra yeniden başlatılıyor...\n")

            await asyncio.sleep(bekleme_suresi)

            # Client'i yeniden başlat
            try:
                await client.disconnect()
            except:
                pass

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[SON] Program kapatıldı.")
