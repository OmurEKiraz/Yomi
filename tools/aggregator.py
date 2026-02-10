import asyncio
import aiohttp
import json
import os
import shutil
import zipfile
import warnings
from functools import partial

# --- SUSTURUCU MODU ---
warnings.filterwarnings("ignore")

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, TaskID
from rich.table import Table

try:
    from yomi.core import YomiCore
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from yomi.core import YomiCore

console = Console()

# --- AYARLAR ---
RAW_NAMES_PATH = os.path.join("tools", "raw-names.json")
TARGET_DB_PATH = os.path.join("yomi", "sites.json")
TEMP_DIR = "temp_test_zone"

# --- HIZ AYARLARI ---
CONCURRENT_MANGAS = 30        
GLOBAL_CONNECTION_LIMIT = 300 

# --- TANRI MODU HEADERS ---
REAL_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://google.com",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1"
}

_original_init = aiohttp.ClientSession.__init__
def patched_init(self, *args, **kwargs):
    if "headers" not in kwargs: kwargs["headers"] = {}
    kwargs["headers"].update(REAL_BROWSER_HEADERS)
    _original_init(self, *args, **kwargs)
aiohttp.ClientSession.__init__ = patched_init

# --- EN POPÜLER KORSAN KALIPLARI ---
DOMAIN_PATTERNS = [
    # 1. Aşama: En Olası
    "read{slug}.com", 
    "read-{slug}.com",
    "{slug}-manga.com",
    "read-{slug}-manga.com",
    "{slug}.com",
    
    # 2. Aşama: "Online" ve "Free"
    "{slug}-online.com",
    "{slug}online.com",
    "read{slug}free.com",
    "read-{slug}-free.com",
    "{slug}-free.com",
    
    # 3. Aşama: Uzantı Değişiklikleri
    "{slug}.net",
    "read{slug}.net",
    "{slug}-manga.net",
    "{slug}.to",
    "read{slug}.to",
    "{slug}.gg",
    "{slug}.org",
    "{slug}.cc",
    "{slug}.io",
    "{slug}.xyz",
    
    # 4. Aşama: Son Çareler
    "{slug}scans.com",
    "manga-{slug}.com",
    "read-{slug}-online.com",
    "manga{slug}online.com",
    "my{slug}.com",
    "the{slug}.com"
]

SUBDOMAINS = ["", "www"]

async def check_url_exists(session, url):
    """Hızlı HTTP Kontrolü"""
    try:
        async with session.head(url, timeout=3, allow_redirects=True) as response:
            if response.status == 200: return str(response.url).rstrip('/')
    except:
        try:
            async with session.get(url, timeout=3, allow_redirects=True) as response:
                if response.status == 200: return str(response.url).rstrip('/')
        except:
            pass
    return None

async def verify_download_success(slug, base_url):
    """Quality Control"""
    # Slug içinde özel karakter varsa temizle (dosya sistemi hatası olmasın)
    safe_slug = "".join([c for c in slug if c.isalnum() or c in ('-','_')])
    task_temp_dir = os.path.join(TEMP_DIR, safe_slug)

    if os.path.exists(task_temp_dir):
        try: shutil.rmtree(task_temp_dir)
        except: pass
    os.makedirs(task_temp_dir, exist_ok=True)

    try:
        core = YomiCore(output_dir=task_temp_dir, debug=False, format="cbz")
        if hasattr(core, 'headers') and isinstance(core.headers, dict):
            core.headers.update(REAL_BROWSER_HEADERS)

        temp_config = {
            slug: {
                "name": slug.title().replace("-", " "),
                "type": "static", 
                "url": base_url + "/manga/" + slug
            }
        }
        core.sites_config.update(temp_config)
    except Exception: return False

    success = False
    try:
        await core._download_manga_async(slug, chapter_range="1-1")
        for root, dirs, files in os.walk(task_temp_dir):
            for file in files:
                if file.endswith(".cbz"):
                    try:
                        with zipfile.ZipFile(os.path.join(root, file), 'r') as z:
                            file_list = z.namelist()
                            has_xml = "ComicInfo.xml" in file_list
                            image_count = sum(1 for f in file_list if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
                            if (has_xml and image_count > 0) or (image_count > 3):
                                success = True
                    except Exception: pass
    except Exception: pass
    
    if hasattr(core, 'db') and core.db:
        try: core.db.close(); del core.db
        except: pass
    
    await asyncio.sleep(0.1)
    if os.path.exists(task_temp_dir):
        try: shutil.rmtree(task_temp_dir)
        except: pass

    return success

async def process_single_manga(session, original_slug, existing_sites, progress, task_id, stats):
    # Eğer zaten bulunduysa hiç uğraşma
    if original_slug in existing_sites:
        progress.advance(task_id)
        return

    # --- AKILLI VARYASYON MOTORU ---
    # Burada türetilen her şey sadece DENEME amaçlıdır.
    # Veritabanına yine original_slug (raw-names.json'daki isim) ile kaydedilir.
    variations = [original_slug] 
    
    # 1. Tireleri kaldır (jujutsukaisen)
    no_dash = original_slug.replace("-", "")
    if no_dash != original_slug:
        variations.append(no_dash)
        
    # 2. Kısaltma / Akrostiş (attack-on-titan -> aot)
    parts = original_slug.split("-")
    if len(parts) > 1:
        acronym = "".join([p[0] for p in parts if p])
        if len(acronym) >= 2: # En az 2 harfli olsun
            variations.append(acronym)
            
    # 3. İlk Kelime (jujutsu-kaisen -> jujutsu)
    if len(parts) > 1 and len(parts[0]) > 3:
        variations.append(parts[0])

    manga_solved = False
    
    try:
        # Önce varyasyonları dön (aot, attackontitan...)
        for current_slug_variant in variations:
            if manga_solved: break
            
            # Sonra her varyasyon için domain kalıplarını dön
            for domain_ptr in DOMAIN_PATTERNS:
                if manga_solved: break

                # Burada varyasyonu url içine gömüyoruz
                base_domain_raw = domain_ptr.format(slug=current_slug_variant).strip().lower()
                
                # RADAR: Kullanıcıya hangi varyasyonu denediğimizi gösterelim
                progress.update(task_id, description=f"[bold blue]{original_slug}[/] [dim yellow]→ {base_domain_raw}[/]")

                # Subdomain Taraması
                tasks = []
                for sub in SUBDOMAINS:
                    prefix = f"{sub}." if sub else ""
                    candidate_url = f"https://{prefix}{base_domain_raw}"
                    tasks.append(check_url_exists(session, candidate_url))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                real_url = None
                for r in results:
                    if isinstance(r, str) and r:
                        real_url = r
                        break

                if real_url:
                    progress.console.print(f"   🔎 [cyan]Hit:[/cyan] [bold]{real_url}[/bold] (Quality Check...)")
                    
                    # İndirme testini de bulunan varyasyonla yapıyoruz
                    # Amaç: Sitenin çalıştığını doğrulamak
                    is_perfect = await verify_download_success(current_slug_variant, real_url)

                    if is_perfect:
                        parsed_domain = real_url.split("//")[1].split("/")[0].replace("www.", "")
                        if parsed_domain.startswith("w") and len(parsed_domain) > 3 and parsed_domain[1].isdigit() and "." in parsed_domain:
                                parsed_domain = parsed_domain.split(".", 1)[1]

                        new_entry = {
                            "name": original_slug.title().replace("-", " "), # İsim orijinal kalır
                            "type": "dynamic",
                            "base_domain": parsed_domain,
                            "test_path": f"/manga/{current_slug_variant}-chapter-1", # Test yolu varyasyona göre olabilir
                            "url_pattern": "{mirror}/manga/" + current_slug_variant + "-chapter-{chapter}" # Pattern varyasyonlu olmalı
                        }
                        
                        # --- KRİTİK NOKTA ---
                        # Bulunan site 'jjk' olsa bile, biz onu 'jujutsu-kaisen' anahtarına kaydediyoruz.
                        existing_sites[original_slug] = new_entry
                        stats["added"].append(original_slug)
                        
                        try:
                            with open(TARGET_DB_PATH, 'w', encoding='utf-8') as f:
                                json.dump(existing_sites, f, indent=2)
                        except: pass
                        
                        progress.console.print(f"   ✅ [bold green]CAPTURED:[/bold green] [white]{original_slug}[/white] [dim](via {current_slug_variant})[/dim]")
                        manga_solved = True
                    else:
                        progress.console.print(f"   🗑️  [dim red]Trash Site:[/dim red] {base_domain_raw}")

    except Exception: pass

    if not manga_solved:
        stats["failed"].append(original_slug)
    
    # İş bitince barı eski haline getir
    progress.update(task_id, description=f"[bold blue]Scanning Library...[/]")
    progress.advance(task_id)

async def main():
    console.rule("[bold red]YOMI AGGREGATOR (SMART VARIANT ENGINE)[/]")
    console.print(f"[yellow]Loadout:[/yellow] Smart permutation engine active.")
    
    if not os.path.exists(RAW_NAMES_PATH): return
    with open(RAW_NAMES_PATH, 'r', encoding='utf-8') as f: raw_names = json.load(f)

    existing_sites = {}
    if os.path.exists(TARGET_DB_PATH):
        try:
            with open(TARGET_DB_PATH, 'r', encoding='utf-8') as f: existing_sites = json.load(f)
        except: pass

    stats = {"added": [], "failed": []}

    # Zaten bulunanları atla (4700'deysen sadece kalanlara bakar)
    pending_mangas = [slug for slug in raw_names if slug not in existing_sites]
    
    console.print(f"[cyan]Database:[/cyan] {len(existing_sites)} found. [yellow]Scanning remaining:[/yellow] {len(pending_mangas)}")

    connector = aiohttp.TCPConnector(limit=GLOBAL_CONNECTION_LIMIT, ttl_dns_cache=600)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"), 
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeRemainingColumn(),
                transient=False
            ) as progress:
                
                main_task = progress.add_task("[bold blue]Scanning Library...", total=len(pending_mangas))
                sem = asyncio.Semaphore(CONCURRENT_MANGAS)

                async def worker(slug):
                    async with sem:
                        try:
                            await process_single_manga(session, slug, existing_sites, progress, main_task, stats)
                        except Exception:
                            progress.advance(main_task)

                tasks = [worker(slug) for slug in pending_mangas]
                await asyncio.gather(*tasks, return_exceptions=True)
        
        finally:
            await asyncio.sleep(2.0)
            await session.close()

    if os.path.exists(TEMP_DIR):
        try: shutil.rmtree(TEMP_DIR)
        except: pass

    console.rule("[bold green]FINAL REPORT[/]")
    table = Table(title=f"Results (New Additions)")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("[green]ADDED NEW[/]", str(len(stats["added"])))
    table.add_row("[red]STILL MISSING[/]", str(len(stats["failed"])))
    console.print(table)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
    finally:
        loop.close()