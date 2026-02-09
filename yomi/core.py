import os
import logging
import shutil
import json
import asyncio
import aiohttp
import requests
from urllib.parse import unquote
from difflib import SequenceMatcher

# Rich Library (UI)
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table
from rich.prompt import IntPrompt

# Internal Imports
from .database import YomiDB
from .utils.archive import create_cbz_archive, create_pdf_document
from .utils.metadata import parse_chapter_metadata
from .utils.anilist import AniListProvider
from .extractors.common import AsyncGenericMangaExtractor

# Optional Hunter Import
try:
    from .discovery import MirrorHunter
except ImportError:
    MirrorHunter = None

# Logger Configuration
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True)]
)
logger = logging.getLogger("YomiCore")

class YomiCore:
    def __init__(self, output_dir: str = "downloads", workers: int = 8, debug: bool = False, format: str = "folder", proxy: str = None):
        self.output_dir = output_dir
        self.workers = workers 
        self.format = format.lower()
        self.debug = debug
        self.proxy = proxy
        self.console = Console()
        self.anilist = AniListProvider()
        
        if self.debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.ERROR)
        
        os.makedirs(self.output_dir, exist_ok=True)
        self.db = YomiDB(os.path.join(output_dir, "history.db"))
        self.sites_config = self._load_sites_config()

    def _load_sites_config(self) -> dict:
        config = {}
        # ÖNCE YEREL DOSYAYA BAK (Remote'u devre dışı bıraktık ki GitHub karışmasın)
        base_dir = os.path.dirname(__file__)
        local_path = os.path.join(base_dir, "sites.json")
        
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    config.update(json.load(f))
                if self.debug: logger.info(f"Loaded local DB: {len(config)} sites")
            except Exception as e:
                logger.error(f"❌ Critical: Failed to load local database: {e}")
        else:
            logger.error("❌ Critical: sites.json not found in package directory!")
            
        return config

    def _calculate_score(self, query: str, target: str) -> float:
        """
        Gelişmiş Skorlama Algoritması:
        Tireleri, boşlukları ve büyük/küçük harfi yok sayar.
        """
        if not target: return 0
        
        # 1. Normalizasyon (Tireleri boşluk yap, küçük harfe çevir)
        q_norm = query.lower().replace("-", " ").strip()
        t_norm = target.lower().replace("-", " ").strip()
        
        # 2. Tam Kapsama (Substring)
        # Örn: "after ten" -> "after ten millennia..." içindeyse
        if q_norm in t_norm:
            return 95.0  # Neredeyse kesin eşleşme
            
        # 3. Kelime Bazlı Eşleşme (Word Intersection)
        q_words = set(q_norm.split())
        t_words = set(t_norm.split())
        common_words = q_words.intersection(t_words)
        
        word_score = 0
        if len(common_words) > 0:
            # Ortak kelime sayısı / Aranan kelime sayısı
            # Yani "after" ve "ten" yazdıysam ve ikisi de varsa %100 kelime skoru
            word_score = (len(common_words) / len(q_words)) * 80
            
        # 4. Harf Benzerliği (Typos için)
        fuzzy_score = SequenceMatcher(None, q_norm, t_norm).ratio() * 100
        
        return max(word_score, fuzzy_score)

    async def _resolve_target(self, input_str: str, for_download=False):
        if input_str.startswith("http"): return input_str
        
        # Input temizliği
        clean_input = unquote(input_str).strip()
        target_key = None
        
        # 1. Tam Eşleşme Kontrolü
        if clean_input in self.sites_config:
            target_key = clean_input
        else:
            # 2. Akıllı Arama
            matches = []
            for key, data in self.sites_config.items():
                site_name = data.get('name', '').lower()
                
                # Hem Key'e (slug) hem Name'e (başlık) göre skor al
                score_key = self._calculate_score(clean_input, key)
                score_name = self._calculate_score(clean_input, site_name)
                
                # Hangisi yüksekse onu al
                final_score = max(score_key, score_name)
                
                # Eşik değer: %45 (Daha toleranslı)
                if final_score > 45: 
                    matches.append((final_score, key, data['name']))

            matches.sort(key=lambda x: x[0], reverse=True)
            
            if not matches: 
                print(f"❌ '{input_str}' veritabanında bulunamadı.")
                return None
            
            # --- SEÇİM MANTIĞI ---
            # Eğer skor çok yüksekse (>85) sormadan seç
            if matches[0][0] >= 85:
                self.console.print(f"✨ Auto-Match: [bold green]{matches[0][2]}[/] (Confidence: {int(matches[0][0])}%)")
                target_key = matches[0][1]
            else:
                self.console.print(f"\n🔍 Ambiguous input '[bold yellow]{input_str}[/]'. Did you mean one of these?")
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("#", style="cyan", justify="right", width=4)
                table.add_column("Site Name", style="white")
                table.add_column("Match", justify="right", style="green")

                display_count = min(5, len(matches))
                for i in range(display_count):
                    score, key, name = matches[i]
                    table.add_row(str(i + 1), name, f"{int(score)}%")

                self.console.print(table)
                
                choices = [str(i) for i in range(display_count + 1)]
                try:
                    selected = IntPrompt.ask("Select number (0 to cancel)", choices=choices, default=1, show_choices=False)
                except KeyboardInterrupt:
                    return None

                if selected == 0:
                    print("🛑 Selection cancelled.")
                    return None
                
                target_key = matches[selected - 1][1]

        # --- ÇÖZÜMLEME ---
        site_data = self.sites_config[target_key]
        site_type = site_data.get("type", "static")
        
        if site_type == "dynamic" and MirrorHunter:
            print(f"🌍 Auto-Discovery: Resolving '{target_key}'...")
            test_path = site_data.get("test_path", "/")
            safe_test_path = test_path.replace("{chapter}", "1").replace("{chapter", "1")
            
            hunter = MirrorHunter(debug=self.debug)
            active_mirror = await hunter.find_active_mirror(site_data["base_domain"], test_path=safe_test_path)
            
            if active_mirror:
                print(f"✅ TARGET LOCKED: {active_mirror}")
                if "url_pattern" in site_data:
                    full_pattern = site_data["url_pattern"].replace("{mirror}", active_mirror)
                    list_url = full_pattern
                    # Temizlik
                    for junk in ["-chapter-{chapter}", "chapter-{chapter}", "-{chapter}", "{chapter}", "{chapter"]:
                        if junk in list_url:
                            list_url = list_url.replace(junk, "")
                            break
                    if list_url.endswith("-"): list_url = list_url[:-1]
                    return list_url
                return active_mirror
            else:
                print(f"❌ ERROR: Could not resolve mirror for {target_key}")
                return None
        
        elif "url" in site_data:
            return site_data['url']
        return None

    def download_manga(self, target: str, chapter_range: str = None):
        try:
            asyncio.run(self._download_manga_async(target, chapter_range))
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")

    async def _download_manga_async(self, target: str, chapter_range: str):
        url = await self._resolve_target(target)
        if not url: return

        connector = aiohttp.TCPConnector(limit=self.workers)
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            extractor = AsyncGenericMangaExtractor(session)

            print(f"🔍 Analyzing: {url}...")
            try:
                manga_info = await extractor.get_manga_info(url)
            except Exception as e:
                print(f"❌ Failed to fetch info: {e}")
                manga_info = {"title": target.title(), "url": url}

            manga_title = manga_info['title']
            print(f"📘 Target: {manga_title}")
            
            try:
                all_chapters = await extractor.get_chapters(url)
            except Exception as e:
                print(f"❌ Error scanning chapters: {e}")
                all_chapters = []

            if not all_chapters and "/manga/" in url:
                print("⚠️  No chapters found. Trying root domain fallback...")
                root_url = url.split("/manga/")[0]
                all_chapters = await extractor.get_chapters(root_url)

            chapters = self._filter_chapters(all_chapters, chapter_range)
            
            if not chapters:
                print("❌ No chapters found.")
                return

            print(f"🧬 Fetching Metadata for '{manga_title}'...")
            rich_meta = await self.anilist.fetch_metadata(manga_title)
            
            safe_title = "".join([c for c in manga_title if c.isalnum() or c in (' ', '-', '_')]).strip()
            manga_path = os.path.join(self.output_dir, safe_title)
            os.makedirs(manga_path, exist_ok=True)
            
            print(f"🚀 Queued {len(chapters)} chapters...")

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(f"[green]Downloading {manga_title}", total=len(chapters))
                
                for chapter in chapters:
                    if self.db.is_completed(manga_title, chapter['title']):
                        progress.console.print(f"[dim]Skipping {chapter['title']} (Already Downloaded)[/dim]")
                        progress.advance(task)
                        continue

                    await self._download_single_chapter(extractor, chapter, manga_path, manga_title, progress, rich_meta)
                    progress.advance(task)

        self.db.close()

    def _filter_chapters(self, chapters, range_str):
        if not range_str: return chapters
        try:
            if "-" in range_str:
                start_end = range_str.split('-')
                start = float(start_end[0])
                end = float(start_end[1])
            else:
                start = float(range_str)
                end = start
            
            filtered = []
            for chap in chapters:
                import re
                nums = re.findall(r'\d+(?:\.\d+)?', chap['title'])
                if not nums: nums = re.findall(r'\d+(?:\.\d+)?', chap['url'])
                if nums:
                    num = float(nums[-1])
                    if start <= num <= end:
                        filtered.append(chap)
            return filtered
        except:
            return chapters

    async def _download_single_chapter(self, extractor, chapter, parent_path, manga_title, progress, rich_meta=None):
        base_meta = parse_chapter_metadata(chapter['title'], manga_title, chapter['url'])
        full_meta = {**base_meta}
        if rich_meta: full_meta.update(rich_meta)

        clean_title = "".join([c for c in chapter['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        chapter_folder = os.path.join(parent_path, clean_title)
        os.makedirs(chapter_folder, exist_ok=True)

        try:
            pages = await extractor.get_pages(chapter['url'])
            if not pages:
                os.rmdir(chapter_folder)
                return

            tasks = []
            for idx, img_url in enumerate(pages):
                ext = "jpg"
                if ".png" in img_url.lower(): ext = "png"
                elif ".webp" in img_url.lower(): ext = "webp"
                fname = f"{idx+1:03d}.{ext}"
                save_path = os.path.join(chapter_folder, fname)
                tasks.append(extractor.download_image(img_url, save_path))
            
            await asyncio.gather(*tasks)

            loop = asyncio.get_running_loop()
            success = False
            
            if self.format == "pdf":
                pdf_path = os.path.join(parent_path, f"{clean_title}.pdf")
                if await loop.run_in_executor(None, create_pdf_document, chapter_folder, pdf_path):
                    shutil.rmtree(chapter_folder)
                    success = True
            elif self.format == "cbz":
                cbz_path = os.path.join(parent_path, f"{clean_title}.cbz")
                if await loop.run_in_executor(None, create_cbz_archive, chapter_folder, cbz_path, full_meta):
                    shutil.rmtree(chapter_folder)
                    success = True
            else:
                success = True 

            if success:
                self.db.mark_completed(manga_title, chapter['title'])
                author_txt = f" | {full_meta.get('writer')}" if full_meta.get('writer') else ""
                progress.console.print(f"[green]✅ Finished: {clean_title} (Meta: #{full_meta['number']}{author_txt})[/green]")

        except Exception as e:
            progress.console.print(f"[red]Failed {chapter['title']}: {e}[/red]")