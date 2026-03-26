import asyncio
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

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

-- Mesaj taslakları (premium emoji destekli)
CREATE TABLE IF NOT EXISTS taslaklar (
    id SERIAL PRIMARY KEY,
    taslak_adi TEXT UNIQUE NOT NULL,
    taslak_icerik TEXT NOT NULL,
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
        conn = await asyncpg.connect(DATABASE_URL)
        print("[✓] Bağlantı başarılı!")

        print("\n[*] Tablolar oluşturuluyor...")
        await conn.execute(SQL)

        print("[✓] Tablolar başarıyla oluşturuldu:")
        print("    - kaynak_kanallar")
        print("    - hedef_kanal")
        print("    - taslaklar")
        print("    - yasak_kelimeler")
        print("    - ayarlar")

        # Mevcut veri sayıları
        kanallar = await conn.fetchval("SELECT COUNT(*) FROM kaynak_kanallar")
        taslaklar = await conn.fetchval("SELECT COUNT(*) FROM taslaklar")
        yasak = await conn.fetchval("SELECT COUNT(*) FROM yasak_kelimeler")

        print(f"\n📊 Mevcut Veriler:")
        print(f"    - Kaynak Kanallar: {kanallar}")
        print(f"    - Taslaklar: {taslaklar}")
        print(f"    - Yasak Kelimeler: {yasak}")

        await conn.close()
        print("\n[✓] Bağlantı kapatıldı.")
        print("\n✅ Kurulum tamamlandı!")

    except Exception as e:
        print(f"\n[HATA] ❌ {e}")

if __name__ == "__main__":
    asyncio.run(main())
