import requests
import json
import re
import time
import os

# --- AYARLAR ---
SKIP_FIRST_N = 20000  # İlk 20.000 taneyi (Zaten yaptıklarımızı) atla
TARGET_COUNT = 30000  # Üzerine 30.000 daha çek (Toplam 50k'ya varacağız)
PER_PAGE = 50         # Sayfa başı veri
OUTPUT_PATH = "yomi/utils/raw-names-deep.json"

# Başlangıç Sayfası Hesabı: 20000 / 50 = 400. sayfa
START_PAGE = (SKIP_FIRST_N // PER_PAGE) + 1

def slugify(text):
    if not text: return None
    text = text.lower()
    text = text.replace(" (", "-").replace(")", "")
    text = text.replace(" [", "-").replace("]", "")
    text = re.sub(r'[^a-z0-9\s-]', '', text) 
    text = re.sub(r'[\s]+', '-', text)
    return text.strip('-')

def fetch_deep_manga_list():
    print(f"📡 AniList API'ye Bağlanılıyor...")
    print(f"🕳️  DERİN DALIŞ MODU: İlk {SKIP_FIRST_N} popüler manga ATLANIYOR.")
    print(f"🎯 Hedef: {SKIP_FIRST_N} - {SKIP_FIRST_N + TARGET_COUNT} arası (Mezarlık Bölgesi)")
    
    url = 'https://graphql.anilist.co'
    slugs = []
    seen = set()
    page = START_PAGE
    retry_count = 0

    query = '''
    query ($page: Int, $perPage: Int) {
      Page (page: $page, perPage: $perPage) {
        pageInfo {
          hasNextPage
          total
        }
        media (type: MANGA, sort: POPULARITY_DESC) {
          title {
            romaji
            english
            userPreferred
          }
          isAdult
          format
        }
      }
    }
    '''

    start_time = time.time()

    while len(slugs) < TARGET_COUNT:
        variables = {'page': page, 'perPage': PER_PAGE}

        try:
            response = requests.post(url, json={'query': query, 'variables': variables}, timeout=15)
            
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", 60))
                print(f"⏳ Hız Limiti! {wait}sn bekleniyor...")
                time.sleep(wait + 2)
                continue
            
            if response.status_code != 200:
                print(f"❌ Hata (Sayfa {page}): {response.status_code}")
                retry_count += 1
                if retry_count > 10: break
                time.sleep(5)
                continue

            data = response.json()
            media_list = data.get('data', {}).get('Page', {}).get('media', [])
            has_next = data.get('data', {}).get('Page', {}).get('pageInfo', {}).get('hasNextPage', False)
            
            if not media_list: break

            count_on_page = 0
            for item in media_list:
                titles = []
                if item['title']['english']: titles.append(item['title']['english'])
                if item['title']['romaji']: titles.append(item['title']['romaji'])
                if item['title']['userPreferred']: titles.append(item['title']['userPreferred'])
                
                for t in set(titles):
                    slug = slugify(t)
                    if slug and slug not in seen and len(slug) > 2:
                        slugs.append(slug)
                        seen.add(slug)
                        count_on_page += 1

            elapsed = time.time() - start_time
            total_scanned = (page * PER_PAGE)
            print(f"📄 Sayfa {page:<4} | Bulunan: {len(slugs):<6} | Sıralama: #{total_scanned} civarı | Geçen: {int(elapsed)}s")
            
            if not has_next:
                print("⚠️ Veritabanı sonu.")
                break
                
            page += 1
            time.sleep(0.8) # Nezaket beklemesi

        except Exception as e:
            print(f"⚠️ Hata: {e}")
            time.sleep(5)

    # Klasör kontrol
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(slugs, f, indent=2)
    
    print("=" * 60)
    print(f"💀 DERİN DALIŞ TAMAMLANDI!")
    print(f"📦 Toplam: {len(slugs)} nadir manga ismi.")
    print(f"📂 Kayıt: {OUTPUT_PATH}")
    print("👉 Aggregator'da 'RAW_NAMES_PATH' ayarını bu dosya ile değiştirmeyi unutma!")
    print("=" * 60)

if __name__ == "__main__":
    fetch_deep_manga_list()