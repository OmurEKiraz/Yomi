import os
import json
import shutil
import logging
import asyncio
import random
import aiohttp
from rich.console import Console

# --- DOĞRU IMPORTLAR (Dosyalarına Bakılarak Düzeltildi) ---
from yomi.discovery import MirrorHunter
from yomi.extractors.common import AsyncGenericMangaExtractor
from yomi.utils.archive import create_cbz_archive, create_pdf_document
from yomi.utils.metadata import parse_chapter_metadata

# --- AYARLAR ---
TEST_DIR = "stress_test_output"
SITES_JSON = "sites_test.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')

async def test_single_site(site_key, site_data, hunter, session):
    """
    Tek bir siteyi test eder: URL Bul -> Bölüm Listele -> 1-2 Bölüm İndir -> Arşivle
    """
    site_name = site_data['name']
    target_format = random.choice(['cbz', 'pdf'])
    chapter_count = random.randint(1, 2) # Hız için az tuttum
    
    print(f"👉 {site_name} [{target_format.upper()}]...", end=" ", flush=True)

    try:
        # 1. AVCI: URL'İ BUL (Async)
        base_domain = site_data.get('base_domain')
        test_path = site_data.get('test_path', "/")
        
        active_url = await hunter.find_active_mirror(base_domain, test_path)
        
        if not active_url:
            print("❌ URL Yok (Site Ölü)")
            return False

        # 2. EXTRACTOR: BÖLÜMLERİ ÇEK
        # AsyncGenericMangaExtractor, session ile başlatılır
        extractor = AsyncGenericMangaExtractor(session)
        chapters = await extractor.get_chapters(active_url)

        if not chapters:
            print("❌ Bölüm Listesi Boş")
            return False

        # 3. İŞLEM: RASTGELE BÖLÜMLERİ İNDİR
        # Listenin başından (en yeni) bölümleri alıyoruz ki silinmiş olma ihtimali düşük olsun
        targets = chapters[:chapter_count]
        
        success_count = 0
        manga_clean = "".join([c for c in site_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        site_dir = os.path.join(TEST_DIR, manga_clean)
        os.makedirs(site_dir, exist_ok=True)

        for chapter in targets:
            try:
                # Metadata Hazırla
                meta = parse_chapter_metadata(chapter['title'], site_name, chapter['url'])
                chap_clean = "".join([c for c in chapter['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
                chap_dir = os.path.join(site_dir, chap_clean)
                os.makedirs(chap_dir, exist_ok=True)

                # Sayfaları Bul
                pages = await extractor.get_pages(chapter['url'])
                if not pages:
                    continue

                # Resimleri İndir (Parallel)
                download_tasks = []
                for idx, img_url in enumerate(pages):
                    ext = "jpg"
                    if ".png" in img_url.lower(): ext = "png"
                    elif ".webp" in img_url.lower(): ext = "webp"
                    
                    save_path = os.path.join(chap_dir, f"{idx+1:03d}.{ext}")
                    # extractor.download_image metodunu kullanıyoruz
                    download_tasks.append(extractor.download_image(img_url, save_path))
                
                # Hepsini indir
                await asyncio.gather(*download_tasks)

                # Arşivle (PDF veya CBZ)
                archive_success = False
                if target_format == 'pdf':
                    pdf_path = os.path.join(site_dir, f"{chap_clean}.pdf")
                    if create_pdf_document(chap_dir, pdf_path):
                        archive_success = True
                else: # cbz
                    cbz_path = os.path.join(site_dir, f"{chap_clean}.cbz")
                    if create_cbz_archive(chap_dir, cbz_path, meta):
                        archive_success = True
                
                if archive_success:
                    shutil.rmtree(chap_dir) # Klasörü temizle
                    success_count += 1
            except Exception:
                pass # Tekil bölüm hatası tüm testi yakmasın
        
        if success_count > 0:
            print(f"✅ PASS ({success_count}/{len(targets)} İndi)")
            return True
        else:
            print("❌ İndirme Başarısız")
            return False

    except Exception as e:
        print(f"❌ KRİTİK HATA: {str(e)[:50]}")
        return False

async def main():
    # 0. Dosya Kontrolü
    if not os.path.exists(SITES_JSON):
        print(f"❌ '{SITES_JSON}' bulunamadı! Önce 'python yomi/utils/auto_discovery.py' çalıştır.")
        return

    with open(SITES_JSON, 'r', encoding='utf-8') as f:
        sites = json.load(f)

    # Temizlik
    if os.path.exists(TEST_DIR):
        try: shutil.rmtree(TEST_DIR)
        except: pass
    os.makedirs(TEST_DIR)

    print(f"🔥 MASS TEST BAŞLIYOR: {len(sites)} Site")
    print("-" * 50)
    
    # 1. Avcıyı Başlat
    hunter = MirrorHunter()
    
    # 2. Session Başlat (Tüm işlemler için tek session, performans artırır)
    connector = aiohttp.TCPConnector(limit=20) # Aynı anda 20 bağlantı
    async with aiohttp.ClientSession(connector=connector) as session:
        passed = 0
        failed = 0
        
        for i, (key, data) in enumerate(sites.items(), 1):
            print(f"[{i}/{len(sites)}]", end=" ")
            res = await test_single_site(key, data, hunter, session)
            if res: passed += 1
            else: failed += 1

    print("-" * 50)
    print(f"📊 SONUÇ: {passed} Başarılı / {failed} Hatalı")
    print(f"✅ Başarı Oranı: %{(passed/len(sites))*100:.1f}")
    print(f"📂 Çıktı Klasörü: {TEST_DIR}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())