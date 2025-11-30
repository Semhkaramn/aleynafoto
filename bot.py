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
# AYARLAR - HEPSİ BURADAN DÜZENLENİR
########################################

# KANAL AYARLARI
KAYNAK_KANALLAR = [
    -1001702869083,
    -1002214278617,
    -1001885502015,
    -1002379522248,
]

HEDEF_KANAL = -1002560312226

# MESAJ TASLAK AYARLARI
TASLAK_SISTEMI_AKTIF = True  # True = Taslaklar sırayla, False = Rastgele taslak
TASLAK_DEGISIM_SAYISI = 2    # Kaç foto başına taslak değişsin (örn: 2 = her 2 fotoda bir)

MESAJ_TASLAKLARI = [
    # Taslak 1 (İlk 2 foto için)
    """‼️2 ALANDAN BIZIM REFERANSTAN UYE OL MİN. 500TL KUPONU OYNA YATARSADA TUTARSADA BONUS BUY I KAP BENDEN ‼️

🔴 HAFTALIK YATIRIM KAPSAMINDA HER ALAN ICIN 1 KERE FAYDALANABILIRSINIZ

🟠<a href="https://cutt.ly/Ne5YHGAq">SUPERTOTO HEMEN KAYIT 1000TL ANINDA SENIN</a> 🟠

🟠<a href="https://cutt.ly/deKcYP81">MATADOR HEMEN KAYIT 1000TL ANINDA SENIN</a>  🟠""",

]

# FİLTRE AYARLARI
YASAK_KELIMELER = [
    "bonus",
    "fırsat",
    "freespin",
    "kayıt",
]

YASAK_KELIME_KONTROLU = True  # True = Yasak kelimeleri kontrol et, False = Kontrol etme

# HASH KONTROLÜ
AYNI_FOTO_KONTROLU = True     # True = Aynı fotoğrafı tekrar gönderme, False = Gönder
FOTO_CACHE_LIMIT = 1000       # Kaç fotoğraf hatırlansın
MESAJ_CACHE_LIMIT = 10000     # Kaç mesaj hatırlansın

# RATE LIMITING
GONDERIM_ARASI_BEKLE = 1      # Her gönderim arası kaç saniye bekle
FLOOD_BEKLE = 30              # Flood hatası alınca kaç saniye bekle

# KEEPALIVE
KEEPALIVE_SURE = 180          # Kaç saniyede bir ping (180 = 3 dakika)

# SİSTEM (DOKUNMAYIN)
islenen = set()
foto_hash_cache = set()
gonderim_sayaci = 0  # Taslak seçimi için
bot_aktif = True

########################################
# HEROKU KEEPALIVE
########################################

async def keepalive_loop():
    while True:
        try:
            await asyncio.sleep(KEEPALIVE_SURE)
            await client.get_dialogs(limit=1)
            print(f"[KEEPALIVE] ✅ Ping - {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[KEEPALIVE HATA] {e}")
            await asyncio.sleep(60)

########################################
# TASLAK SEÇİMİ
########################################

def taslak_sec():
    """Sıradaki mesaj taslağını seç"""
    global gonderim_sayaci

    if not MESAJ_TASLAKLARI:
        return "Taslak bulunamadı!"

    if not TASLAK_SISTEMI_AKTIF:
        # Rastgele taslak
        import random
        return random.choice(MESAJ_TASLAKLARI)

    # Sıralı taslak sistemi
    taslak_index = (gonderim_sayaci // TASLAK_DEGISIM_SAYISI) % len(MESAJ_TASLAKLARI)
    gonderim_sayaci += 1

    return MESAJ_TASLAKLARI[taslak_index]

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

    # DEBUG: Kaynak kanaldan mesaj geldi
    print(f"[DEBUG] 📩 Mesaj geldi -> Kanal: {event.chat_id} | #{event.id}")

    # Mesaj kontrolü
    key = (event.chat_id, event.id)
    if key in islenen:
        return
    islenen.add(key)

    if len(islenen) > MESAJ_CACHE_LIMIT:
        islenen.clear()

    # Fotoğraf var mı?
    foto = extract_photo(event.message)
    if not foto:
        return

    # Fotoğraf hash kontrolü
    if AYNI_FOTO_KONTROLU:
        foto_id = getattr(foto, 'id', None)
        if not foto_id and hasattr(foto, 'document'):
            foto_id = getattr(foto.document, 'id', None)

        if foto_id:
            if foto_id in foto_hash_cache:
                print(f"[ATLA] ⏭ Aynı fotoğraf (ID: {foto_id})")
                return
            foto_hash_cache.add(foto_id)

            if len(foto_hash_cache) > FOTO_CACHE_LIMIT:
                foto_hash_cache.clear()

    # Yasak kelime kontrolü
    if YASAK_KELIME_KONTROLU:
        caption = (event.message.message or "").lower()
        for kelime in YASAK_KELIMELER:
            if kelime in caption:
                print(f"[ATLA] ⚠️ Yasak kelime: {kelime}")
                return

    # Taslak seç
    mesaj_taslagi = taslak_sec()
    taslak_no = ((gonderim_sayaci - 1) // TASLAK_DEGISIM_SAYISI) % len(MESAJ_TASLAKLARI) + 1

    # Gönder
    try:
        await client.send_file(
            HEDEF_KANAL,
            file=foto,
            caption=mesaj_taslagi,
            parse_mode="html"
        )
        print(f"[OK] ✅ Foto gönderildi | Taslak #{taslak_no} | Kanal: {event.chat_id} | #{event.id} | {datetime.now().strftime('%H:%M:%S')}")
        await asyncio.sleep(GONDERIM_ARASI_BEKLE)

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
                    caption=mesaj_taslagi,
                    parse_mode="html"
                )
                print(f"[OK] ✅ Protected çözüldü | Taslak #{taslak_no} | #{event.id}")
                await asyncio.sleep(GONDERIM_ARASI_BEKLE)
            except Exception as e2:
                print(f"[HATA] ❌ Protected indirilemedi: {e2}")

        # Flood
        elif "flood" in err or "wait" in err:
            print(f"[UYARI] ⚠️ Flood - {FLOOD_BEKLE} sn bekleniyor...")
            await asyncio.sleep(FLOOD_BEKLE)

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
            print(f"\n[TASLAK] 📝 Taslak sistemi: {'AKTIF ✅' if TASLAK_SISTEMI_AKTIF else 'RASTGELE 🎲'}")
            print(f"[TASLAK] 📊 Toplam taslak: {len(MESAJ_TASLAKLARI)} adet")
            print(f"[TASLAK] 🔄 Her {TASLAK_DEGISIM_SAYISI} fotoda bir taslak değişir")
            print(f"\n[FİLTRE] ⚙️ Yasak kelime kontrolü: {'AÇIK ✅' if YASAK_KELIME_KONTROLU else 'KAPALI ❌'}")
            print(f"[FİLTRE] ⚙️ Aynı foto kontrolü: {'AÇIK ✅' if AYNI_FOTO_KONTROLU else 'KAPALI ❌'}")
            print(f"[FİLTRE] ⚙️ Gönderim arası: {GONDERIM_ARASI_BEKLE}s | Flood: {FLOOD_BEKLE}s")
            print(f"[FİLTRE] ⚙️ Keepalive: {KEEPALIVE_SURE}s ({KEEPALIVE_SURE//60} dakika)\n")

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
