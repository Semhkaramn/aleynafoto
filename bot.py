import os
import asyncio
import json
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageEntityCustomEmoji
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from datetime import datetime
import asyncpg

# ═══════════════════════════════════════════════════════════════
# ORTAM DEĞİŞKENLERİ
# ═══════════════════════════════════════════════════════════════

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

# Çoklu Admin Desteği - virgülle ayrılmış ID'ler (örn: "123456,789012,345678")
_admin_ids_raw = os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "0"))
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]

# Heroku Postgres için URL düzeltmesi (postgres:// -> postgresql://)
_raw_db_url = os.getenv("DATABASE_URL", "")
DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql://", 1) if _raw_db_url.startswith("postgres://") else _raw_db_url

# ═══════════════════════════════════════════════════════════════
# TELEGRAM CLIENT (SESSION STRING)
# ═══════════════════════════════════════════════════════════════

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# ═══════════════════════════════════════════════════════════════
# GLOBAL DEĞİŞKENLER
# ═══════════════════════════════════════════════════════════════

db_pool = None
bot_aktif = True
islenen_mesajlar = set()
foto_cache = set()
gonderim_sayaci = 0
bekleyen_islem = {}  # Admin'den beklenen işlemler (admin_id -> (islem, veri))

# ═══════════════════════════════════════════════════════════════
# VERİTABANI FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════

async def init_db():
    """Veritabanı bağlantısı ve tabloları oluştur"""
    global db_pool

    # Heroku Postgres için SSL gerekli
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, ssl="require")

    async with db_pool.acquire() as conn:
        # Tablolar
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kaynak_kanallar (
                id SERIAL PRIMARY KEY,
                kanal_id BIGINT UNIQUE NOT NULL,
                kanal_adi TEXT,
                eklenen_tarih TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS hedef_kanal (
                id SERIAL PRIMARY KEY,
                kanal_id BIGINT NOT NULL,
                kanal_adi TEXT,
                guncelleme TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS yasak_kelimeler (
                id SERIAL PRIMARY KEY,
                kelime TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ayarlar (
                anahtar TEXT PRIMARY KEY,
                deger TEXT NOT NULL
            );
        """)

        # Yeni taslak sistemi - mesaj referansı ile
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS taslaklar_v2 (
                id SERIAL PRIMARY KEY,
                taslak_adi TEXT UNIQUE NOT NULL,
                source_chat_id BIGINT NOT NULL,
                source_message_id BIGINT NOT NULL,
                aktif BOOLEAN DEFAULT TRUE,
                sira INTEGER DEFAULT 0,
                eklenen_tarih TIMESTAMP DEFAULT NOW()
            );
        """)

        # Varsayılan ayarlar
        varsayilan_ayarlar = [
            ("taslak_sistemi", "sira"),  # sira veya rastgele
            ("taslak_degisim", "2"),
            ("gonderim_arasi", "1"),
            ("flood_bekleme", "30"),
            ("keepalive_sure", "180"),
            ("foto_cache_limit", "1000"),
            ("mesaj_cache_limit", "10000"),
            ("yasak_kelime_kontrol", "true"),
            ("ayni_foto_kontrol", "true"),
        ]

        for anahtar, deger in varsayilan_ayarlar:
            await conn.execute("""
                INSERT INTO ayarlar (anahtar, deger)
                VALUES ($1, $2)
                ON CONFLICT (anahtar) DO NOTHING
            """, anahtar, deger)

    print("[DB] ✅ Veritabanı hazır")

async def get_ayar(anahtar, varsayilan=""):
    """Ayar değeri getir"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT deger FROM ayarlar WHERE anahtar = $1", anahtar)
        return row['deger'] if row else varsayilan

async def set_ayar(anahtar, deger):
    """Ayar değeri kaydet"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ayarlar (anahtar, deger)
            VALUES ($1, $2)
            ON CONFLICT (anahtar) DO UPDATE SET deger = $2
        """, anahtar, str(deger))

async def get_kaynak_kanallar():
    """Kaynak kanalları getir"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT kanal_id, kanal_adi FROM kaynak_kanallar ORDER BY id")
        return [(row['kanal_id'], row['kanal_adi']) for row in rows]

async def add_kaynak_kanal(kanal_id, kanal_adi=""):
    """Kaynak kanal ekle"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute("""
                INSERT INTO kaynak_kanallar (kanal_id, kanal_adi) VALUES ($1, $2)
            """, kanal_id, kanal_adi)
            return True
        except:
            return False

async def remove_kaynak_kanal(kanal_id):
    """Kaynak kanal sil"""
    async with db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM kaynak_kanallar WHERE kanal_id = $1", kanal_id)
        return "DELETE 1" in result

async def get_hedef_kanal():
    """Hedef kanalı getir"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT kanal_id, kanal_adi FROM hedef_kanal ORDER BY id DESC LIMIT 1")
        return (row['kanal_id'], row['kanal_adi']) if row else (None, None)

async def set_hedef_kanal(kanal_id, kanal_adi=""):
    """Hedef kanal ayarla"""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM hedef_kanal")
        await conn.execute("""
            INSERT INTO hedef_kanal (kanal_id, kanal_adi) VALUES ($1, $2)
        """, kanal_id, kanal_adi)

# ═══════════════════════════════════════════════════════════════
# YENİ TASLAK SİSTEMİ (MESAJ REFERANSI)
# ═══════════════════════════════════════════════════════════════

async def get_taslaklar(sadece_aktif=False):
    """Taslakları getir (yeni sistem)"""
    async with db_pool.acquire() as conn:
        if sadece_aktif:
            rows = await conn.fetch("SELECT * FROM taslaklar_v2 WHERE aktif = TRUE ORDER BY sira, id")
        else:
            rows = await conn.fetch("SELECT * FROM taslaklar_v2 ORDER BY sira, id")
        return rows

async def add_taslak(taslak_adi, source_chat_id, source_message_id):
    """Taslak ekle (mesaj referansı olarak)"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute("""
                INSERT INTO taslaklar_v2 (taslak_adi, source_chat_id, source_message_id)
                VALUES ($1, $2, $3)
            """, taslak_adi, source_chat_id, source_message_id)
            return True
        except:
            return False

async def update_taslak(taslak_adi, source_chat_id, source_message_id):
    """Taslak güncelle"""
    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE taslaklar_v2 SET source_chat_id = $2, source_message_id = $3
            WHERE taslak_adi = $1
        """, taslak_adi, source_chat_id, source_message_id)
        return "UPDATE 1" in result

async def delete_taslak(taslak_adi):
    """Taslak sil"""
    async with db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM taslaklar_v2 WHERE taslak_adi = $1", taslak_adi)
        return "DELETE 1" in result

async def toggle_taslak(taslak_adi):
    """Taslak aktif/pasif"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE taslaklar_v2 SET aktif = NOT aktif WHERE taslak_adi = $1
        """, taslak_adi)

async def get_taslak_message(taslak):
    """Taslak mesajını al (orijinal formatıyla)"""
    try:
        source_chat_id = taslak['source_chat_id']
        source_message_id = taslak['source_message_id']

        # Orijinal mesajı al
        message = await client.get_messages(source_chat_id, ids=source_message_id)

        if message is None:
            print(f"[HATA] ❌ Taslak mesajı bulunamadı: {taslak['taslak_adi']}")
            return None

        return message
    except Exception as e:
        print(f"[HATA] ❌ Taslak mesajı alınamadı: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# YASAK KELİME FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════

async def get_yasak_kelimeler():
    """Yasak kelimeleri getir"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT kelime FROM yasak_kelimeler")
        return [row['kelime'] for row in rows]

async def add_yasak_kelime(kelime):
    """Yasak kelime ekle"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute("INSERT INTO yasak_kelimeler (kelime) VALUES ($1)", kelime.lower())
            return True
        except:
            return False

async def remove_yasak_kelime(kelime):
    """Yasak kelime sil"""
    async with db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM yasak_kelimeler WHERE kelime = $1", kelime.lower())
        return "DELETE 1" in result

# ═══════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════

def extract_photo(msg):
    """Mesajdan fotoğraf çıkart"""
    if msg.photo:
        return msg.photo
    if msg.media:
        if isinstance(msg.media, MessageMediaPhoto):
            return msg.media.photo
        if isinstance(msg.media, MessageMediaDocument):
            if hasattr(msg.media.document, 'mime_type'):
                if msg.media.document.mime_type.startswith("image/"):
                    return msg.media
    return None

def is_admin(user_id):
    """Kullanıcının admin olup olmadığını kontrol et"""
    return user_id in ADMIN_IDS

async def parse_kanal_input(text):
    """Kanal linkini veya ID'sini parse et"""
    text = text.strip()

    # t.me/joinchat/HASH formatı
    joinchat_match = re.search(r't\.me/joinchat/([a-zA-Z0-9_-]+)', text)
    if joinchat_match:
        return ("invite", joinchat_match.group(1))

    # t.me/+HASH formatı
    plus_match = re.search(r't\.me/\+([a-zA-Z0-9_-]+)', text)
    if plus_match:
        return ("invite", plus_match.group(1))

    # t.me/username formatı
    username_match = re.search(r't\.me/([a-zA-Z0-9_]+)', text)
    if username_match:
        return ("username", username_match.group(1))

    # @username formatı
    if text.startswith("@"):
        return ("username", text[1:])

    # Direkt ID
    try:
        kanal_id = int(text)
        if not str(kanal_id).startswith("-100"):
            kanal_id = int(f"-100{abs(kanal_id)}")
        return ("id", kanal_id)
    except:
        pass

    # Username olarak dene
    if text.isalnum() or "_" in text:
        return ("username", text)

    return (None, None)

async def kanal_katil_ve_id_al(kanal_input):
    """Kanala katıl ve ID'sini al"""
    tip, deger = await parse_kanal_input(kanal_input)

    if tip is None:
        return None, "❌ Geçersiz kanal formatı"

    try:
        if tip == "invite":
            # Davet linki ile katıl
            updates = await client(ImportChatInviteRequest(deger))
            chat = updates.chats[0]
            kanal_id = int(f"-100{chat.id}")
            return kanal_id, chat.title

        elif tip == "username":
            # Username ile katıl
            await client(JoinChannelRequest(deger))
            entity = await client.get_entity(deger)
            kanal_id = int(f"-100{entity.id}")
            return kanal_id, entity.title

        elif tip == "id":
            # ID ile bilgi al
            try:
                entity = await client.get_entity(deger)
                return deger, getattr(entity, 'title', 'Bilinmiyor')
            except:
                return deger, "Bilinmiyor"

    except Exception as e:
        return None, f"❌ Hata: {str(e)}"

async def taslak_sec():
    """Sıradaki taslağı seç ve mesajı getir"""
    global gonderim_sayaci

    taslaklar = await get_taslaklar(sadece_aktif=True)
    if not taslaklar:
        return None, None

    sistem = await get_ayar("taslak_sistemi", "sira")
    degisim = int(await get_ayar("taslak_degisim", "2"))

    if sistem == "rastgele":
        import random
        taslak = random.choice(taslaklar)
    else:
        # Sıralı sistem
        index = (gonderim_sayaci // degisim) % len(taslaklar)
        taslak = taslaklar[index]

    gonderim_sayaci += 1

    # Taslak mesajını al
    message = await get_taslak_message(taslak)

    return message, taslak['taslak_adi']

# ═══════════════════════════════════════════════════════════════
# ADMİN KOMUTLARI
# ═══════════════════════════════════════════════════════════════

YARDIM_MESAJI = """
<b>🤖 Bot Yönetim Paneli</b>

<b>📊 Genel Komutlar:</b>
├ <code>/durum</code> - Bot durumunu göster
├ <code>/aktif</code> - Botu aktifleştir
├ <code>/pasif</code> - Botu durdur
└ <code>/yardim</code> - Bu menü

<b>📝 Taslak Yönetimi (Yeni Sistem):</b>
├ <code>/taslak liste</code> - Taslakları listele
├ <code>/taslak ekle [isim]</code> - Yeni taslak ekle (sonra mesaj gönder)
├ <code>/taslak sil [isim]</code> - Taslak sil
├ <code>/taslak duzenle [isim]</code> - Taslak düzenle
├ <code>/taslak toggle [isim]</code> - Aktif/Pasif yap
└ <code>/taslak test [isim]</code> - Taslağı test et

<b>⚠️ Yeni Taslak Sistemi:</b>
<i>Taslak = Mesaj Referansı
• /taslak ekle isim yazıp mesajı gönderdiğinizde, mesajın ID'si kaydedilir
• Gönderim sırasında mesaj orijinal formatıyla kopyalanır
• Premium emoji, linkler, bold/italic HER ŞEY korunur!
• ⚠️ Taslak mesajını silmeyin, yoksa taslak çalışmaz!</i>

<b>📡 Kanal Yönetimi:</b>
├ <code>/kanal liste</code> - Dinlenen kanallar
├ <code>/kanal ekle [link/id]</code> - Kanal ekle
├ <code>/kanal sil [id]</code> - Kanal sil
└ <code>/hedef [link/id]</code> - Hedef kanal ayarla

<b>🚫 Yasak Kelimeler:</b>
├ <code>/yasak liste</code> - Yasak kelimeleri göster
├ <code>/yasak ekle [kelime]</code> - Kelime ekle
└ <code>/yasak sil [kelime]</code> - Kelime sil

<b>⚙️ Ayarlar:</b>
├ <code>/ayar liste</code> - Tüm ayarları göster
└ <code>/ayar [anahtar] [deger]</code> - Ayar değiştir

<b>👥 Admin Sistemi:</b>
<i>Birden fazla admin desteklenir!
ADMIN_IDS = "id1,id2,id3" formatında</i>

<b>📌 Ayar Anahtarları:</b>
<code>taslak_sistemi</code> = sira / rastgele
<code>taslak_degisim</code> = Kaç fotoda taslak değişsin
<code>gonderim_arasi</code> = Gönderimler arası saniye
<code>flood_bekleme</code> = Flood'da bekleme süresi
<code>yasak_kelime_kontrol</code> = true / false
<code>ayni_foto_kontrol</code> = true / false
"""

@client.on(events.NewMessage(pattern=r'^[/!](yardim|help|menu|komutlar)$'))
async def cmd_yardim(event):
    if not is_admin(event.sender_id):
        return
    await event.reply(YARDIM_MESAJI, parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]durum$'))
async def cmd_durum(event):
    if not is_admin(event.sender_id):
        return

    hedef_id, hedef_adi = await get_hedef_kanal()
    kanallar = await get_kaynak_kanallar()
    taslaklar = await get_taslaklar(sadece_aktif=True)
    yasak = await get_yasak_kelimeler()

    durum = "✅ AKTİF" if bot_aktif else "⏸ DURDURULDU"

    admin_list = ", ".join([f"<code>{a}</code>" for a in ADMIN_IDS])

    mesaj = f"""
<b>📊 Bot Durumu</b>

<b>Durum:</b> {durum}
<b>Gönderilen:</b> {gonderim_sayaci} foto

<b>👥 Adminler:</b> {admin_list}

<b>📡 Dinlenen Kanallar:</b> {len(kanallar)} adet
<b>🎯 Hedef Kanal:</b> {hedef_adi or 'Ayarlanmadı'} (<code>{hedef_id or '-'}</code>)

<b>📝 Aktif Taslak:</b> {len(taslaklar)} adet
<b>🚫 Yasak Kelime:</b> {len(yasak)} adet

<b>⚙️ Ayarlar:</b>
├ Taslak Sistemi: {await get_ayar('taslak_sistemi')}
├ Taslak Değişim: {await get_ayar('taslak_degisim')} foto
├ Gönderim Arası: {await get_ayar('gonderim_arasi')}s
├ Yasak Kontrol: {await get_ayar('yasak_kelime_kontrol')}
└ Foto Kontrol: {await get_ayar('ayni_foto_kontrol')}

<b>⏰ Zaman:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    await event.reply(mesaj, parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!](aktif|start|baslat)$'))
async def cmd_aktif(event):
    if not is_admin(event.sender_id):
        return
    global bot_aktif
    bot_aktif = True
    await event.reply("✅ Bot aktifleştirildi!")
    print(f"[KOMUT] ▶ Bot aktif - {datetime.now().strftime('%H:%M:%S')}")

@client.on(events.NewMessage(pattern=r'^[/!](pasif|stop|dur|durdur)$'))
async def cmd_pasif(event):
    if not is_admin(event.sender_id):
        return
    global bot_aktif
    bot_aktif = False
    await event.reply("⏸ Bot durduruldu!")
    print(f"[KOMUT] ⏸ Bot pasif - {datetime.now().strftime('%H:%M:%S')}")

# ═══════════════════════════════════════════════════════════════
# TASLAK KOMUTLARI (YENİ SİSTEM)
# ═══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(pattern=r'^[/!]taslak liste$'))
async def cmd_taslak_liste(event):
    if not is_admin(event.sender_id):
        return

    taslaklar = await get_taslaklar()

    if not taslaklar:
        await event.reply(
            "📝 Henüz taslak eklenmemiş.\n\n"
            "Eklemek için: <code>/taslak ekle [isim]</code>\n"
            "Sonra taslak mesajını gönderin.",
            parse_mode="html"
        )
        return

    mesaj = "<b>📝 Taslak Listesi (Yeni Sistem)</b>\n\n"
    for i, t in enumerate(taslaklar, 1):
        durum = "✅" if t['aktif'] else "❌"
        mesaj += f"{i}. {durum} <b>{t['taslak_adi']}</b>\n"
        mesaj += f"   📍 Chat: <code>{t['source_chat_id']}</code>\n"
        mesaj += f"   📩 Mesaj ID: <code>{t['source_message_id']}</code>\n\n"

    mesaj += "\n<i>⚠️ Taslak mesajlarını silmeyin!</i>"
    await event.reply(mesaj, parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]taslak ekle (.+)$'))
async def cmd_taslak_ekle(event):
    if not is_admin(event.sender_id):
        return

    taslak_adi = event.pattern_match.group(1).strip()
    bekleyen_islem[event.sender_id] = ("taslak_ekle", taslak_adi)

    await event.reply(
        f"📝 <b>{taslak_adi}</b> için taslak mesajını gönder.\n\n"
        "💡 <b>Yeni Sistem:</b>\n"
        "• Mesajınız olduğu gibi kaydedilecek\n"
        "• Premium emoji'ler ✅\n"
        "• Linkler ✅\n"
        "• Bold, italic, underline ✅\n"
        "• Gönderim sırasında mesaj kopyalanacak\n\n"
        "⚠️ <b>Önemli:</b> Bu mesajı silmeyin!\n\n"
        "İptal için: <code>/iptal</code>",
        parse_mode="html"
    )

@client.on(events.NewMessage(pattern=r'^[/!]taslak sil (.+)$'))
async def cmd_taslak_sil(event):
    if not is_admin(event.sender_id):
        return

    taslak_adi = event.pattern_match.group(1).strip()

    if await delete_taslak(taslak_adi):
        await event.reply(f"✅ <b>{taslak_adi}</b> taslağı silindi.", parse_mode="html")
    else:
        await event.reply(f"❌ <b>{taslak_adi}</b> bulunamadı.", parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]taslak duzenle (.+)$'))
async def cmd_taslak_duzenle(event):
    if not is_admin(event.sender_id):
        return

    taslak_adi = event.pattern_match.group(1).strip()
    bekleyen_islem[event.sender_id] = ("taslak_duzenle", taslak_adi)

    await event.reply(
        f"✏️ <b>{taslak_adi}</b> için yeni mesajı gönder.\n\n"
        "⚠️ Eski mesajı silmeden önce yeni mesajı gönderin!\n\n"
        "İptal için: <code>/iptal</code>",
        parse_mode="html"
    )

@client.on(events.NewMessage(pattern=r'^[/!]taslak toggle (.+)$'))
async def cmd_taslak_toggle(event):
    if not is_admin(event.sender_id):
        return

    taslak_adi = event.pattern_match.group(1).strip()
    await toggle_taslak(taslak_adi)
    await event.reply(f"🔄 <b>{taslak_adi}</b> durumu değiştirildi.", parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]taslak test (.+)$'))
async def cmd_taslak_test(event):
    if not is_admin(event.sender_id):
        return

    taslak_adi = event.pattern_match.group(1).strip()

    # Taslağı bul
    taslaklar = await get_taslaklar()
    taslak = None
    for t in taslaklar:
        if t['taslak_adi'] == taslak_adi:
            taslak = t
            break

    if not taslak:
        await event.reply(f"❌ <b>{taslak_adi}</b> bulunamadı.", parse_mode="html")
        return

    # Mesajı al
    message = await get_taslak_message(taslak)

    if not message:
        await event.reply(
            f"❌ <b>{taslak_adi}</b> taslak mesajı bulunamadı!\n\n"
            "Mesaj silinmiş olabilir. Lütfen yeniden ekleyin.",
            parse_mode="html"
        )
        return

    # Test için kopyala
    try:
        await message.forward_to(event.chat_id)
        await event.reply(
            f"✅ <b>{taslak_adi}</b> taslağı yukarıda!\n\n"
            f"📍 Kaynak: <code>{taslak['source_chat_id']}</code>\n"
            f"📩 Mesaj ID: <code>{taslak['source_message_id']}</code>",
            parse_mode="html"
        )
    except Exception as e:
        await event.reply(f"❌ Test hatası: {e}", parse_mode="html")

# ═══════════════════════════════════════════════════════════════
# KANAL KOMUTLARI
# ═══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(pattern=r'^[/!]kanal liste$'))
async def cmd_kanal_liste(event):
    if not is_admin(event.sender_id):
        return

    kanallar = await get_kaynak_kanallar()

    if not kanallar:
        await event.reply("📡 Henüz kanal eklenmemiş.\n\nEklemek için: <code>/kanal ekle [link veya ID]</code>", parse_mode="html")
        return

    mesaj = "<b>📡 Dinlenen Kanallar</b>\n\n"
    for i, (kanal_id, kanal_adi) in enumerate(kanallar, 1):
        mesaj += f"{i}. <b>{kanal_adi or 'İsimsiz'}</b>\n"
        mesaj += f"   ID: <code>{kanal_id}</code>\n\n"

    mesaj += "\n<i>Silmek için:</i> <code>/kanal sil [ID]</code>"
    await event.reply(mesaj, parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]kanal ekle (.+)$'))
async def cmd_kanal_ekle(event):
    if not is_admin(event.sender_id):
        return

    kanal_input = event.pattern_match.group(1).strip()

    await event.reply("⏳ Kanal ekleniyor...")

    kanal_id, sonuc = await kanal_katil_ve_id_al(kanal_input)

    if kanal_id is None:
        await event.reply(sonuc)
        return

    if await add_kaynak_kanal(kanal_id, sonuc):
        await event.reply(
            f"✅ Kanal eklendi!\n\n"
            f"<b>Kanal:</b> {sonuc}\n"
            f"<b>ID:</b> <code>{kanal_id}</code>",
            parse_mode="html"
        )
    else:
        await event.reply("⚠️ Bu kanal zaten ekli.")

@client.on(events.NewMessage(pattern=r'^[/!]kanal sil (.+)$'))
async def cmd_kanal_sil(event):
    if not is_admin(event.sender_id):
        return

    kanal_input = event.pattern_match.group(1).strip()

    try:
        kanal_id = int(kanal_input)
        if not str(kanal_id).startswith("-100"):
            kanal_id = int(f"-100{abs(kanal_id)}")
    except:
        await event.reply("❌ Geçerli bir kanal ID'si gir.")
        return

    if await remove_kaynak_kanal(kanal_id):
        await event.reply(f"✅ Kanal silindi: <code>{kanal_id}</code>", parse_mode="html")
    else:
        await event.reply("❌ Kanal bulunamadı.")

@client.on(events.NewMessage(pattern=r'^[/!]hedef (.+)$'))
async def cmd_hedef(event):
    if not is_admin(event.sender_id):
        return

    kanal_input = event.pattern_match.group(1).strip()

    await event.reply("⏳ Hedef kanal ayarlanıyor...")

    kanal_id, sonuc = await kanal_katil_ve_id_al(kanal_input)

    if kanal_id is None:
        await event.reply(sonuc)
        return

    await set_hedef_kanal(kanal_id, sonuc)
    await event.reply(
        f"🎯 Hedef kanal ayarlandı!\n\n"
        f"<b>Kanal:</b> {sonuc}\n"
        f"<b>ID:</b> <code>{kanal_id}</code>",
        parse_mode="html"
    )

# ═══════════════════════════════════════════════════════════════
# YASAK KELİME KOMUTLARI
# ═══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(pattern=r'^[/!]yasak liste$'))
async def cmd_yasak_liste(event):
    if not is_admin(event.sender_id):
        return

    kelimeler = await get_yasak_kelimeler()

    if not kelimeler:
        await event.reply("🚫 Yasak kelime yok.\n\nEklemek için: <code>/yasak ekle [kelime]</code>", parse_mode="html")
        return

    mesaj = "<b>🚫 Yasak Kelimeler</b>\n\n"
    mesaj += ", ".join([f"<code>{k}</code>" for k in kelimeler])

    await event.reply(mesaj, parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]yasak ekle (.+)$'))
async def cmd_yasak_ekle(event):
    if not is_admin(event.sender_id):
        return

    kelime = event.pattern_match.group(1).strip().lower()

    if await add_yasak_kelime(kelime):
        await event.reply(f"✅ Yasak kelime eklendi: <code>{kelime}</code>", parse_mode="html")
    else:
        await event.reply("⚠️ Bu kelime zaten ekli.")

@client.on(events.NewMessage(pattern=r'^[/!]yasak sil (.+)$'))
async def cmd_yasak_sil(event):
    if not is_admin(event.sender_id):
        return

    kelime = event.pattern_match.group(1).strip().lower()

    if await remove_yasak_kelime(kelime):
        await event.reply(f"✅ Yasak kelime silindi: <code>{kelime}</code>", parse_mode="html")
    else:
        await event.reply("❌ Kelime bulunamadı.")

# ═══════════════════════════════════════════════════════════════
# AYAR KOMUTLARI
# ═══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(pattern=r'^[/!]ayar liste$'))
async def cmd_ayar_liste(event):
    if not is_admin(event.sender_id):
        return

    ayarlar = [
        "taslak_sistemi", "taslak_degisim", "gonderim_arasi",
        "flood_bekleme", "yasak_kelime_kontrol", "ayni_foto_kontrol"
    ]

    mesaj = "<b>⚙️ Ayarlar</b>\n\n"
    for ayar in ayarlar:
        deger = await get_ayar(ayar)
        mesaj += f"<code>{ayar}</code> = <b>{deger}</b>\n"

    mesaj += "\n<i>Değiştirmek için:</i>\n<code>/ayar [anahtar] [değer]</code>"
    await event.reply(mesaj, parse_mode="html")

@client.on(events.NewMessage(pattern=r'^[/!]ayar (\S+) (.+)$'))
async def cmd_ayar_degistir(event):
    if not is_admin(event.sender_id):
        return

    anahtar = event.pattern_match.group(1).strip()
    deger = event.pattern_match.group(2).strip()

    await set_ayar(anahtar, deger)
    await event.reply(f"✅ Ayar güncellendi:\n<code>{anahtar}</code> = <b>{deger}</b>", parse_mode="html")

# ═══════════════════════════════════════════════════════════════
# İPTAL VE BEKLEYEN İŞLEM
# ═══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(pattern=r'^[/!]iptal$'))
async def cmd_iptal(event):
    if not is_admin(event.sender_id):
        return

    if event.sender_id in bekleyen_islem:
        del bekleyen_islem[event.sender_id]
        await event.reply("❌ İşlem iptal edildi.")
    else:
        await event.reply("ℹ️ İptal edilecek işlem yok.")

@client.on(events.NewMessage())
async def bekleyen_islem_handler(event):
    # Admin değilse atla
    if not is_admin(event.sender_id):
        return

    # Komut değilse ve bekleyen işlem varsa
    if event.text and event.text.startswith(('/', '!')):
        return

    if event.sender_id not in bekleyen_islem:
        return

    islem, veri = bekleyen_islem[event.sender_id]
    del bekleyen_islem[event.sender_id]

    if islem == "taslak_ekle":
        taslak_adi = veri
        # Mesaj referansını kaydet (chat_id + message_id)
        source_chat_id = event.chat_id
        source_message_id = event.id

        if await add_taslak(taslak_adi, source_chat_id, source_message_id):
            await event.reply(
                f"✅ Taslak eklendi: <b>{taslak_adi}</b>\n\n"
                f"📍 Chat ID: <code>{source_chat_id}</code>\n"
                f"📩 Mesaj ID: <code>{source_message_id}</code>\n\n"
                f"💎 <b>Yeni Sistem Aktif!</b>\n"
                f"• Premium emoji'ler ✅\n"
                f"• Linkler tıklanabilir ✅\n"
                f"• Tüm formatlamalar korunur ✅\n\n"
                f"⚠️ <b>Bu mesajı silmeyin!</b>",
                parse_mode="html"
            )
        else:
            await event.reply(f"❌ <b>{taslak_adi}</b> zaten mevcut.", parse_mode="html")

    elif islem == "taslak_duzenle":
        taslak_adi = veri
        # Mesaj referansını güncelle
        source_chat_id = event.chat_id
        source_message_id = event.id

        if await update_taslak(taslak_adi, source_chat_id, source_message_id):
            await event.reply(
                f"✅ <b>{taslak_adi}</b> güncellendi.\n\n"
                f"📍 Yeni Chat ID: <code>{source_chat_id}</code>\n"
                f"📩 Yeni Mesaj ID: <code>{source_message_id}</code>\n\n"
                f"⚠️ <b>Bu mesajı silmeyin!</b>",
                parse_mode="html"
            )
        else:
            await event.reply(f"❌ <b>{taslak_adi}</b> bulunamadı.", parse_mode="html")

# ═══════════════════════════════════════════════════════════════
# ANA DİNLEYİCİ
# ═══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(incoming=True))
async def dinleyici(event):
    global islenen_mesajlar, foto_cache

    if not bot_aktif:
        return

    # Admin mesajlarını atla (komut olabilir)
    if is_admin(event.sender_id):
        return

    # Özel mesajları atla
    if event.is_private:
        return

    # Kaynak kanalları kontrol et
    kaynak_kanallar = await get_kaynak_kanallar()
    kanal_idler = [k[0] for k in kaynak_kanallar]

    if event.chat_id not in kanal_idler:
        return

    # Mesaj tekrar kontrolü
    key = (event.chat_id, event.id)
    if key in islenen_mesajlar:
        return
    islenen_mesajlar.add(key)

    mesaj_limit = int(await get_ayar("mesaj_cache_limit", "10000"))
    if len(islenen_mesajlar) > mesaj_limit:
        islenen_mesajlar.clear()

    # Fotoğraf kontrolü
    foto = extract_photo(event.message)
    if not foto:
        return

    # Aynı foto kontrolü
    ayni_foto_kontrol = await get_ayar("ayni_foto_kontrol", "true") == "true"
    if ayni_foto_kontrol:
        foto_id = getattr(foto, 'id', None)
        if not foto_id and hasattr(foto, 'document'):
            foto_id = getattr(foto.document, 'id', None)

        if foto_id:
            if foto_id in foto_cache:
                print(f"[ATLA] ⏭ Aynı fotoğraf")
                return
            foto_cache.add(foto_id)

            foto_limit = int(await get_ayar("foto_cache_limit", "1000"))
            if len(foto_cache) > foto_limit:
                foto_cache.clear()

    # Yasak kelime kontrolü
    yasak_kontrol = await get_ayar("yasak_kelime_kontrol", "true") == "true"
    if yasak_kontrol:
        caption = (event.message.message or "").lower()
        yasak_kelimeler = await get_yasak_kelimeler()
        for kelime in yasak_kelimeler:
            if kelime in caption:
                print(f"[ATLA] ⚠️ Yasak kelime: {kelime}")
                return

    # Hedef kanal kontrolü
    hedef_id, hedef_adi = await get_hedef_kanal()
    if not hedef_id:
        print("[HATA] ❌ Hedef kanal ayarlanmamış!")
        return

    # Taslak seç (yeni sistem - mesaj referansı)
    taslak_mesaj, taslak_adi = await taslak_sec()
    if not taslak_mesaj:
        print("[HATA] ❌ Aktif taslak yok veya taslak mesajı bulunamadı!")
        return

    # Taslak mesajından caption ve entities al
    caption = taslak_mesaj.text or ""
    entities = taslak_mesaj.entities or []

    # Gönder (Premium emoji ve tüm formatlamalar korunur)
    try:
        await client.send_file(
            hedef_id,
            file=foto,
            caption=caption,
            formatting_entities=entities,
            parse_mode=None  # Entity'leri doğrudan kullan
        )
        print(f"[OK] ✅ Gönderildi | Taslak: {taslak_adi} | {datetime.now().strftime('%H:%M:%S')}")

        gonderim_arasi = int(await get_ayar("gonderim_arasi", "1"))
        await asyncio.sleep(gonderim_arasi)

    except Exception as e:
        err = str(e).lower()

        if "protected" in err or "forward" in err:
            try:
                print(f"[INFO] 🔒 Protected içerik indiriliyor...")
                data = await client.download_media(foto, file=bytes)
                await client.send_file(
                    hedef_id,
                    file=data,
                    caption=caption,
                    formatting_entities=entities,
                    parse_mode=None
                )
                print(f"[OK] ✅ Protected çözüldü | {taslak_adi}")

                gonderim_arasi = int(await get_ayar("gonderim_arasi", "1"))
                await asyncio.sleep(gonderim_arasi)
            except Exception as e2:
                print(f"[HATA] ❌ Protected: {e2}")

        elif "flood" in err or "wait" in err:
            flood_bekle = int(await get_ayar("flood_bekleme", "30"))
            print(f"[UYARI] ⚠️ Flood - {flood_bekle}s bekleniyor...")
            await asyncio.sleep(flood_bekle)

        else:
            print(f"[HATA] ❌ {e}")

# ═══════════════════════════════════════════════════════════════
# KEEPALIVE
# ═══════════════════════════════════════════════════════════════

async def keepalive():
    while True:
        try:
            sure = int(await get_ayar("keepalive_sure", "180"))
            await asyncio.sleep(sure)
            await client.get_dialogs(limit=1)
            print(f"[KEEPALIVE] ✅ Ping - {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[KEEPALIVE] ❌ {e}")
            await asyncio.sleep(60)

# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════

async def main():
    print("\n" + "="*60)
    print("🚀 Bot başlatılıyor...")
    print("="*60 + "\n")

    # Veritabanı
    await init_db()

    # Telegram bağlantısı
    await client.start()

    me = await client.get_me()
    print(f"[OK] ✅ Giriş yapıldı: {me.first_name} (@{me.username})")
    print(f"[OK] ✅ Admin ID'ler: {ADMIN_IDS}")

    # Bilgi
    kanallar = await get_kaynak_kanallar()
    hedef_id, hedef_adi = await get_hedef_kanal()
    taslaklar = await get_taslaklar(sadece_aktif=True)

    print(f"\n[INFO] 📡 Dinlenen kanal: {len(kanallar)} adet")
    print(f"[INFO] 🎯 Hedef: {hedef_adi or 'Ayarlanmadı'}")
    print(f"[INFO] 📝 Aktif taslak: {len(taslaklar)} adet")
    print(f"\n[INFO] 💬 Admin'e /yardim yaz komutları görmek için")
    print("\n[INFO] 🆕 YENİ TASLAK SİSTEMİ AKTİF!")
    print("[INFO] 💎 Premium emoji, link ve formatlamalar korunur")
    print("\n" + "="*60 + "\n")

    # Keepalive başlat
    asyncio.create_task(keepalive())

    # Çalışmaya devam et
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[SON] ⏹ Bot kapatıldı.")
