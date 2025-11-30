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

islenen = set()
bot_aktif = True


########################################
# HEROKU KEEPALIVE
########################################

async def keepalive_loop():
    while True:
        try:
            await asyncio.sleep(300)
            await client.get_me()
            print("[KEEPALIVE] Ping gönderildi.")
        except Exception as e:
            print("[KEEPALIVE HATA]", e)


########################################
# AUTO RECONNECT (KRAL BABASI)
########################################

async def reconnect():
    while True:
        try:
            print("[RECONNECT] Bağlantı kopmuş, yeniden bağlanılıyor...")
            await client.connect()

            if await client.is_user_authorized():
                print("[RECONNECT] Yeniden bağlanma başarılı!")
                return
            else:
                print("[RECONNECT] Oturum yetkisi yok!")
                await asyncio.sleep(5)

        except Exception as e:
            print("[RECONNECT HATA]", e)
            await asyncio.sleep(5)


# Telethon bağlantı kopunca otomatik olarak bu event'i fırlatır
@client.on(events.Disconnected)
async def disconnected_handler(event):
    print("[UYARI] Telegram bağlantısı kesildi!")
    await reconnect()


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

@client.on(events.NewMessage(from_users=OWNER_ID, pattern="^(devam|start)$"))
async def komut_devam(event):
    global bot_aktif
    bot_aktif = True
    await event.reply("▶ Bot devam ediyor.")


########################################
# FOTOĞRAF DİNLEYİCİ
########################################

@client.on(events.NewMessage)
async def dinleyici(event):

    if not bot_aktif:
        return

    if event.is_private and event.sender_id == OWNER_ID:
        return

    cid_norm = normalize_channel_id(event.chat_id)
    kaynaklar = [normalize_channel_id(ch) for ch in KAYNAK_KANALLAR]

    if cid_norm not in kaynaklar:
        return

    key = (event.chat_id, event.id)
    if key in islenen:
        return

    islenen.add(key)

    foto = extract_photo(event.message)
    if not foto:
        return

    caption = (event.message.message or "").lower()
    for w in YASAK_KELIMELER:
        if w in caption:
            return

    try:
        await client.send_file(
            HEDEF_KANAL,
            file=foto,
            caption=MESAJ_TASLAGI,
            parse_mode="html"
        )
        print(f"[OK] Foto gönderildi -> {event.id}")

    except Exception as e:
        err = str(e).lower()

        if "protected" in err or "can't forward" in err:
            try:
                data = await client.download_media(foto, file=bytes)
                await client.send_file(
                    HEDEF_KANAL,
                    file=data,
                    caption=MESAJ_TASLAGI,
                    parse_mode="html"
                )
                print(f"[OK] Protected çözüldü -> {event.id}")

            except Exception as e2:
                print("[HATA Protected]", e2)

        else:
            print("[HATA] Gönderim:", e)


########################################
# MAIN
########################################

async def main():
    await client.start()
    print("Bot aktif!")

    asyncio.create_task(keepalive_loop())
    asyncio.create_task(reconnect())  # Bağlantı giderse tekrar bağlanır

    await asyncio.Future()


if __name__ == "__main__":
    client.loop.run_until_complete(main())
