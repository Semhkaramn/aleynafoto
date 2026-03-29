import asyncio
import asyncpg
import os

# Heroku Postgres için URL düzeltmesi (postgres:// -> postgresql://)
_raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql://", 1) if _raw_db_url and _raw_db_url.startswith("postgres://") else _raw_db_url

SQL = """
-- Kaynak kanallar (dinlenen kanallar)
CREATE TABLE IF NOT EXISTS kaynak_kanallar (
    id SERIAL PRIMARY KEY,
    kanal_id BIGINT UNIQUE NOT NULL,
    kanal_adi TEXT,
    eklenen_tarih TIMESTAMP DEFAULT NOW()
);

-- Hedef kanal (fotoğrafların gönderileceği kanal)
CREATE TABLE IF NOT EXISTS hedef_kanal (
    id SERIAL PRIMARY KEY,
    kanal_id BIGINT NOT NULL,
    kanal_adi TEXT,
    guncelleme TIMESTAMP DEFAULT NOW()
);

-- YENİ TASLAK SİSTEMİ (Mesaj Referansı)
-- Taslak = Mesaj Referansı
-- Artık taslak içeriği metin olarak değil, mesajın kendisi (chat_id + message_id) olarak saklanıyor
-- Premium emoji'ler, linkler, bold/italic HER ŞEY korunur!
-- ⚠️ Taslak mesajını silmeyin, yoksa taslak çalışmaz
CREATE TABLE IF NOT EXISTS taslaklar_v2 (
    id SERIAL PRIMARY KEY,
    taslak_adi TEXT UNIQUE NOT NULL,
    source_chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    aktif BOOLEAN DEFAULT TRUE,
    sira INTEGER DEFAULT 0,
    eklenen_tarih TIMESTAMP DEFAULT NOW()
);

-- Yasak kelimeler
CREATE TABLE IF NOT EXISTS yasak_kelimeler (
    id SERIAL PRIMARY KEY,
    kelime TEXT UNIQUE NOT NULL
);

-- Genel ayarlar
CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar TEXT PRIMARY KEY,
    deger TEXT NOT NULL
);

-- Varsayılan ayarları ekle
INSERT INTO ayarlar (anahtar, deger) VALUES
    ('taslak_sistemi', 'sira'),
    ('taslak_degisim', '2'),
    ('gonderim_arasi', '1'),
    ('flood_bekleme', '30'),
    ('keepalive_sure', '180'),
    ('foto_cache_limit', '1000'),
    ('mesaj_cache_limit', '10000'),
    ('yasak_kelime_kontrol', 'true'),
    ('ayni_foto_kontrol', 'true')
ON CONFLICT (anahtar) DO NOTHING;
"""

async def main():
    print("="*50)
    print("🗄️ Veritabanı Kurulum Scripti")
    print("="*50)

    if not DATABASE_URL:
        print("[HATA] ❌ DATABASE_URL bulunamadı!")
        print("Lütfen .env dosyasında DATABASE_URL'yi ayarlayın.")
        return

    print("\n[*] Veritabanına bağlanılıyor...")

    try:
        # Heroku Postgres için SSL gerekli
        conn = await asyncpg.connect(DATABASE_URL, ssl="require")
        print("[✓] Bağlantı başarılı!")

        print("\n[*] Tablolar oluşturuluyor...")
        await conn.execute(SQL)

        print("[✓] Tablolar başarıyla oluşturuldu:")
        print("    - kaynak_kanallar")
        print("    - hedef_kanal")
        print("    - taslaklar_v2 (YENİ - Mesaj Referansı)")
        print("    - yasak_kelimeler")
        print("    - ayarlar")

        print("\n🆕 YENİ TASLAK SİSTEMİ:")
        print("    • Taslak = Mesaj Referansı")
        print("    • Premium emoji'ler ✅")
        print("    • Linkler tıklanabilir ✅")
        print("    • Bold, italic, underline ✅")
        print("    • ⚠️ Taslak mesajlarını silmeyin!")

        # Mevcut veri sayıları
        kanallar = await conn.fetchval("SELECT COUNT(*) FROM kaynak_kanallar")

        # Yeni taslak tablosunu kontrol et
        try:
            taslaklar = await conn.fetchval("SELECT COUNT(*) FROM taslaklar_v2")
        except:
            taslaklar = 0

        yasak = await conn.fetchval("SELECT COUNT(*) FROM yasak_kelimeler")

        print(f"\n📊 Mevcut Veriler:")
        print(f"    - Kaynak Kanallar: {kanallar}")
        print(f"    - Taslaklar (v2): {taslaklar}")
        print(f"    - Yasak Kelimeler: {yasak}")

        await conn.close()
        print("\n[✓] Bağlantı kapatıldı.")
        print("\n✅ Kurulum tamamlandı!")

        print("\n" + "="*50)
        print("👥 ÇOKLU ADMİN DESTEĞİ:")
        print("    ADMIN_IDS = \"id1,id2,id3\" formatında")
        print("    Örnek: ADMIN_IDS = \"123456,789012\"")
        print("="*50)

    except Exception as e:
        print(f"\n[HATA] ❌ {e}")

if __name__ == "__main__":
    asyncio.run(main())
