import asyncio
import aiohttp
import json
import os
import re
import logging
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

# --- AYARLAR ---
CONCURRENT_REQUESTS = 100  # Hız için 100'e çektim (PC kasarsa 50 yap)
TIMEOUT_SEC = 5            # Hızlı tarasın, cevap vermeyenle uğraşmasın
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("AutoDiscovery")

# --- DEVASA SLUG LİSTESİ ---
BASE_SLUGS = [
    # Top Hits
    "one-piece", "jujutsu-kaisen", "my-hero-academia", "chainsaw-man", "black-clover", "bleach",
    "naruto", "boruto", "dragon-ball-super", "hunter-x-hunter", "one-punch-man", "demon-slayer",
    "attack-on-titan", "kagurabachi", "sakamoto-days", "dandadan", "spy-x-family", "kaiju-no-8",
    "blue-lock", "ao-ashi", "haikyuu", "kingdom", "vinland-saga", "vagabond", "berserk",
    "oyasumi-punpun", "tokyo-revengers", "jojo-bizarre-adventure", "gintama", "fullmetal-alchemist",
    "death-note", "fairy-tail", "seven-deadly-sins", "soul-eater", "fire-force", "dr-stone",
    "promised-neverland", "assassination-classroom", "tokyo-ghoul", "parasyte", "akame-ga-kill",
    
    # Manhwa
    "solo-leveling", "omniscient-readers-viewpoint", "tower-of-god", "god-of-highschool",
    "beginning-after-the-end", "eleceed", "nano-machine", "legend-of-the-northern-blade",
    "mercenary-enrollment", "lookism", "wind-breaker", "bastard", "sweet-home", "true-beauty",
    "sss-class-suicide-hunter", "return-of-the-mount-hua-sect", "greatest-estate-developer",
    
    # Classics & Others
    "monster", "20th-century-boys", "pluto", "akira", "claymore", "gantz", "inu-yashiki",
    "ajin", "blame", "sidonia-no-kishi", "dorohedoro", "golden-kamuy", "hells-paradise",
    "mashle", "undead-unluck", "shangri-la-frontier", "frieren-at-the-funeral", "apothecary-diaries",
    "rent-a-girlfriend", "kaguya-sama", "horimiya", "komi-san", "my-dress-up-darling",
    "nagatoro", "uzaki-chan", "oshi-no-ko", "5-toubun-no-hanayome", "nisekoi", "toradora",
    "mushoku-tensei", "slime-datta-ken", "overlord", "re-zero", "konosuba", "shield-hero",
    "goblin-slayer", "no-game-no-life", "made-in-abyss", "land-of-the-lustrous"
]

# Renkli Versiyonlar (Otomatik eklenir)
COLORED_SLUGS = [s + "-digital-colored-comics" for s in ["one-piece", "naruto", "bleach", "dragon-ball", "demon-slayer", "jojo-bizarre-adventure", "haikyuu"]]
FULL_LIST = BASE_SLUGS + COLORED_SLUGS

# --- PATTERNS ---
URL_PATTERNS = [
    "https://{slug}-manga-online.net",
    "https://ww1.{slug}-manga-online.net",
    "https://read-{slug}-manga.com",
    "https://{slug}-manga.com",
    "https://www.{slug}.net",
    "https://www.{slug}-manga.com",
    "https://read{slug}.com",
    "https://{slug}.online",
    "https://w1.read{slug}.com",
    "https://ww1.read{slug}.com"
]

async def analyze_structure(session, base_url):
    try:
        async with session.get(base_url, timeout=TIMEOUT_SEC) as response:
            if response.status != 200: return None
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                # "Chapter" kelimesi ve yanında bir sayı arıyoruz
                if "chapter" in href.lower() and re.search(r'\d+', href):
                    full_url = urljoin(base_url, href)
                    path = urlparse(full_url).path
                    
                    # Regex: chapter-123 veya chapter/123
                    match = re.search(r'(chapter[-/])(\d+)', path)
                    if match:
                        found_number = match.group(2)
                        # Sadece bulunan sayıyı {chapter} yap
                        pattern_path = path.replace(found_number, '{chapter}', 1)
                        url_pattern = "{mirror}" + pattern_path
                        return path, url_pattern
                    return None, None
    except:
        return None, None
    return None, None

async def check_site(session, name, url_pattern):
    url = url_pattern.format(slug=name)
    try:
        async with session.get(url, timeout=TIMEOUT_SEC, allow_redirects=True) as response:
            if response.status == 200:
                text = (await response.text()).lower()
                if "domain for sale" in text or "buy this domain" in text: return None
                if not ("chapter" in text or "manga" in text or name.replace("-", " ") in text): return None

                final_url = str(response.url).rstrip('/')
                test_path, dynamic_pattern = await analyze_structure(session, final_url)
                
                if test_path and dynamic_pattern:
                    print(f"✅ FOUND: {final_url}")
                    return name, final_url, test_path, dynamic_pattern
    except:
        pass
    return None

async def main():
    print(f"🚀 Taranıyor: {len(FULL_LIST)} seri x {len(URL_PATTERNS)} pattern...")
    
    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for slug in FULL_LIST:
            for pattern in URL_PATTERNS:
                tasks.append(check_site(session, slug, pattern))
        
        results = await asyncio.gather(*tasks)
        
    found_sites = {}
    for res in results:
        if res:
            key, base_url, test_path, url_pattern = res
            
            # Key çakışmasını önle (Renkli ise key değişsin)
            parsed_domain = urlparse(base_url).netloc
            final_key = key
            if "colored" in base_url or "colored" in key:
                final_key += "-colored"

            found_sites[final_key] = {
                "name": key.replace("-", " ").title(),
                "type": "dynamic",
                "base_domain": parsed_domain.replace("www.", ""),
                "test_path": test_path,
                "url_pattern": url_pattern
            }

    if found_sites:
        output_path = os.path.join(os.getcwd(), "sites_test.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(found_sites, f, indent=2)
        print(f"\n🔥 TOPLAM {len(found_sites)} SİTE BULUNDU VE KAYDEDİLDİ!")
    else:
        print("❌ Site bulunamadı.")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())