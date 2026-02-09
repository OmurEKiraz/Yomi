import asyncio
import aiohttp
import json
import os
import shutil
import warnings
import time
import zipfile
import stat
import logging 

# --- SUSTURUCU BÖLÜMÜ ---
# Kırmızı uyarı yazılarını ve kütüphane dırıltılarını kapatır
warnings.filterwarnings("ignore")
warnings.simplefilter('ignore')
logging.getLogger("duckduckgo_search").setLevel(logging.CRITICAL)
logging.getLogger("curl_cffi").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
# DuckDuckGo versiyon uyarısını sustur
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")
os.environ["RUST_LOG"] = "error"

from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

# Core modülü import (yolu bulamazsa ekle)
try:
    from yomi.core import YomiCore
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from yomi.core import YomiCore

console = Console()

# --- DOSYA YOLLARI ---

RAW_NAMES_PATH = os.path.join("yomi", "utils", "raw-names.json")
# TEST MODU: Sonuçları buraya yazar, ana veritabanını bozmaz
TARGET_DB_PATH = os.path.join("yomi", "sites_test.json") 
GRAVEYARD_PATH = os.path.join("yomi", "utils", "graveyard.json") 
TEMP_DIR = "temp_aggregator_zone"

# --- PERFORMANS AYARLARI (ETHERNET POWER) ---
CONCURRENT_TASKS = 30          # Aynı anda taranacak manga sayısı
SEARCH_LIMIT = 2               # Bulamazsa arama motorundan kaç sonuç denesin?
CONNECTION_TIMEOUT = 2.5       # Siteye bağlanma süresi (sn)
GLOBAL_CONNECTION_LIMIT = 500  # Modem limiti

# --- GÜÇLENDİRİLMİŞ ARAMA KALIPLARI ---
# %90 başarı oranı buradadır.
DOMAIN_PATTERNS = [
    "read{slug}.com", "read-{slug}.com", "{slug}-manga.com",
    "{slug}.com", "{slug}manga.com", "w1.read{slug}.com"
]

# --- AKILLI SUBDOMAIN LİSTESİ ---
# 1-6 arasını deneriz (en yaygınlar). 
# Eğer site w36 kullanıyorsa bunu buraya yazmayız, onu Arama Motoru bulur.
SUBDOMAINS = [
    "", "www", 
    "w1", "w2", "w3", "w4", "w5", "w6", 
    "read", "chap", "manga"
]

# --- TARAYICI KİMLİĞİ ---
REAL_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# --- YARDIMCI FONKSİYONLAR ---
def force_delete(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except: pass

def nuke_dir(path):
    """Geçici klasörü zorla temizler"""
    if os.path.exists(path):
        try: shutil.rmtree(path, onerror=force_delete)
        except: pass

# --- AŞAMA 1: URL CANLI MI? ---
async def check_url_basic(session, url):
    try:
        # Önce HEAD (Hızlı), olmazsa GET
        async with session.head(url, timeout=CONNECTION_TIMEOUT) as resp:
            if resp.status == 200: return str(resp.url).rstrip('/')
    except:
        try:
            async with session.get(url, timeout=CONNECTION_TIMEOUT) as resp:
                if resp.status == 200: return str(resp.url).rstrip('/')
        except: pass
    return None

# --- AŞAMA 2: İÇERİK ANALİZİ (HTML) ---
async def pre_validate_content(session, url, slug):
    """
    İndirmeden önce siteye girip 'Bu bir manga sitesi mi?' diye bakar.
    """
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status != 200: return False
            
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            text_content = soup.get_text().lower()
            
            # Cloudflare engeli veya boş sayfa kontrolü
            if "just a moment" in text_content or "challenge" in text_content: return False
            if "chapter" not in text_content and "vol" not in text_content: return False

            # Başlıkta manga adı geçiyor mu?
            page_title = soup.title.string.lower() if soup.title else ""
            clean_slug_name = slug.replace("-", " ")
            
            if clean_slug_name not in page_title and slug not in page_title: return False

            return True
    except: return False

# --- AŞAMA 3: İNDİRME TESTİ (KESİN KANIT) ---
async def verify_download_success(slug, base_url, verify_sem):
    async with verify_sem: # Disk koruması için limitli
        safe_slug = "".join([c for c in slug if c.isalnum() or c in ('-','_')])
        task_temp_dir = os.path.join(TEMP_DIR, safe_slug)
        nuke_dir(task_temp_dir)
        os.makedirs(task_temp_dir, exist_ok=True)

        success = False
        core = None
        try:
            # YomiCore loglarını sustur
            logging.getLogger("YomiCore").setLevel(logging.CRITICAL)
            
            core = YomiCore(output_dir=task_temp_dir, debug=False, format="cbz")
            core.console.quiet = True 
            
            # Dinamik Config
            temp_config = {
                slug: {
                    "name": slug.title().replace("-", " "),
                    "type": "static", 
                    "url": base_url 
                }
            }
            core.sites_config.update(temp_config)
            
            # İNDİR (Output vermeden)
            await core._download_manga_async(slug, chapter_range="1-1")
            
            # KONTROL (XML veya Resim var mı?)
            for root, _, files in os.walk(task_temp_dir):
                for file in files:
                    if file.endswith(".cbz"):
                        with zipfile.ZipFile(os.path.join(root, file), 'r') as z:
                            file_list = z.namelist()
                            has_xml = "ComicInfo.xml" in file_list
                            img_count = sum(1 for f in file_list if f.lower().endswith(('jpg','jpeg','png','webp')))
                            
                            if (has_xml and img_count > 0) or (img_count > 2):
                                success = True
        except: pass
        
        # Temizlik
        if core and hasattr(core, 'db'):
            try: core.db.close()
            except: pass
        nuke_dir(task_temp_dir)
        return success

# --- ARAMA MOTORU (DuckDuckGo) ---
def search_web(query, limit=2):
    try:
        # Arka planda arama yapar (w36 vb. bulmak için)
        results = DDGS().text(query, max_results=limit)
        return [r['href'] for r in results]
    except: return []

# --- ANA İŞLEM DÖNGÜSÜ ---
async def process_manga(session, original_slug, existing, graveyard, progress, main_task, stats, verify_sem):
    if original_slug in existing or original_slug in graveyard:
        progress.advance(main_task)
        return

    progress.update(main_task, description=f"[cyan]Hunting:[/cyan] {original_slug}")
    
    found_entry = None
    candidate_urls = []

    # 1. YÖNTEM: Kalıp ve Subdomain Tahmini (Hızlı)
    clean = original_slug.replace("-", "")
    vars = [original_slug, clean]
    
    for v in vars:
        for ptr in DOMAIN_PATTERNS:
            base_domain = ptr.format(slug=v)
            for sub in SUBDOMAINS:
                prefix = f"{sub}." if sub else ""
                url = f"https://{prefix}{base_domain}"
                candidate_urls.append(url)

    # Tahmin edilen URL'leri kontrol et
    valid_candidates = []
    for url in candidate_urls:
        if found_entry: break
        # Önce URL yaşıyor mu diye bak (Hızlı)
        if await check_url_basic(session, url):
            # Sonra içeriği manga mı diye bak (Orta)
            if await pre_validate_content(session, url, original_slug):
                valid_candidates.append(url)
                break # İlk bulduğun geçerli adayı al ve teste git

    # 2. YÖNTEM: Arama Motoru (Eğer tahmin tutmazsa)
    if not valid_candidates:
        progress.update(main_task, description=f"[yellow]Web Search:[/yellow] {original_slug}")
        await asyncio.sleep(0.5) # Rate limit yememek için bekleme
        loop = asyncio.get_running_loop()
        query = f"read {original_slug.replace('-', ' ')} manga chapter 1 online"
        web_links = await loop.run_in_executor(None, search_web, query, SEARCH_LIMIT)
        
        for link in web_links:
            if await pre_validate_content(session, link, original_slug):
                valid_candidates.append(link)

    # 3. YÖNTEM: İndirme Testi (En son ve en kesin)
    for valid_url in valid_candidates:
        if found_entry: break
        
        # URL'yi temizle (chapter kısmını at)
        base_test_url = valid_url
        if "/chapter" in valid_url:
            base_test_url = valid_url.split("/chapter")[0]
        
        progress.update(main_task, description=f"[blue]Verifying:[/blue] {original_slug}")
        
        # İNDİRİP BAK
        if await verify_download_success(original_slug, base_test_url, verify_sem):
            parsed_domain = valid_url.split("//")[1].split("/")[0].replace("www.", "")
            
            url_pattern = "{mirror}/chapter-{chapter}"
            if "/manga/" in valid_url:
                url_pattern = "{mirror}/manga/" + original_slug + "/chapter-{chapter}"
            
            found_entry = {
                "name": original_slug.title().replace("-", " "),
                "type": "dynamic",
                "base_domain": parsed_domain,
                "url": base_test_url,
                "url_pattern": url_pattern,
                "verified": True
            }

    # SONUÇ KAYDI
    if found_entry:
        existing[original_slug] = found_entry
        # Anlık kaydet (Elektrik gitse bile kaybolmasın)
        try:
            with open(TARGET_DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2)
        except: pass
            
        stats["added"] += 1
        progress.console.print(f"   ✅ [bold green]SECURED:[/bold green] {original_slug} -> [dim]{found_entry['base_domain']}[/dim]")
    else:
        graveyard[original_slug] = "dead"
        stats["failed"] += 1
        # Her 20 başarısızda bir kaydet
        if len(graveyard) % 20 == 0:
            try:
                with open(GRAVEYARD_PATH, 'w', encoding='utf-8') as f:
                    json.dump(graveyard, f, indent=2)
            except: pass
    
    progress.advance(main_task)

async def main():
    console.rule("[bold red]YOMI AGGREGATOR v9 (RESURRECTION)[/]")
    console.print(f"[yellow]Mode:[/yellow] Enhanced Subdomains (w1-w6) + Smart Search | [yellow]Threads:[/yellow] {CONCURRENT_TASKS}")

    nuke_dir(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    if not os.path.exists(RAW_NAMES_PATH): 
        console.print("[red]Hata: raw-names.json bulunamadı![/]")
        return
    
    def load(p): return json.load(open(p, 'r', encoding='utf-8')) if os.path.exists(p) else {}
    
    raw_names = load(RAW_NAMES_PATH)
    existing = load(TARGET_DB_PATH)
    graveyard = load(GRAVEYARD_PATH)
    
    # Graveyard silindiği için raw_names'deki her şeye tekrar bakacak (mevcutlar hariç)
    queue = [s for s in raw_names if s not in existing and s not in graveyard]
    
    console.print(f"[green]Database:[/green] {len(existing)} | [dim]Graveyard:[/dim] {len(graveyard)} | [cyan]Queue:[/cyan] [bold white]{len(queue)}[/bold white]")
    
    connector = aiohttp.TCPConnector(limit=GLOBAL_CONNECTION_LIMIT, ttl_dns_cache=300)
    stats = {"added": 0, "failed": 0}
    
    main_sem = asyncio.Semaphore(CONCURRENT_TASKS)
    verify_sem = asyncio.Semaphore(5) # Disk yazma limiti (PC donmasın diye)

    async with aiohttp.ClientSession(connector=connector, headers=REAL_BROWSER_HEADERS) as session:
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
            TextColumn("{task.completed}/{task.total}"), TimeRemainingColumn()
        ) as progress:
            main_task = progress.add_task("Hunting...", total=len(queue))
            
            async def worker(slug):
                async with main_sem:
                    await process_manga(session, slug, existing, graveyard, progress, main_task, stats, verify_sem)
            
            tasks = [worker(slug) for slug in queue]
            await asyncio.gather(*tasks)

    # Son temizlik
    with open(GRAVEYARD_PATH, 'w', encoding='utf-8') as f: json.dump(graveyard, f, indent=2)
    nuke_dir(TEMP_DIR)
    
    console.rule("[bold green]SESSION COMPLETE[/]")
    console.print(f"Captured: {stats['added']}")
    console.print(f"Dead: {stats['failed']}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        nuke_dir(TEMP_DIR)