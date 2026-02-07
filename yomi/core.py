import os
import logging
import shutil
import json
import asyncio
import aiohttp
from urllib.parse import unquote
from difflib import SequenceMatcher

# Rich Kütüphanesi (Görsellik)
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table
from rich.prompt import IntPrompt

# Import Async Extractor & Utils
from .extractors.common import AsyncGenericMangaExtractor
from .database import YomiDB
from .utils.archive import create_cbz_archive, create_pdf_document
from .utils.metadata import parse_chapter_metadata
from .utils.anilist import AniListProvider

# Import Hunter (Opsiyonel)
try:
    from .discovery import MirrorHunter
except ImportError:
    MirrorHunter = None

# Logger Ayarları
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
        
        # AniList Sağlayıcısını Başlat
        self.anilist = AniListProvider()
        
        if self.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("[bold red]DEBUG MODE ON: Async Engine Active[/]")
        else:
            logger.setLevel(logging.ERROR)
        
        os.makedirs(self.output_dir, exist_ok=True)
        self.db = YomiDB(os.path.join(output_dir, "history.db"))
        self.sites_config = self._load_sites_config()

    def _load_sites_config(self):
        config_path = os.path.join(os.path.dirname(__file__), "sites.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    async def _resolve_target(self, input_str: str):
        """
        Hedefi analiz eder:
        1. Direkt URL mi?
        2. Tam eşleşme mi?
        3. Benzerlik var mı? (Fuzzy Search)
        """
        # 1. Direkt URL kontrolü
        if input_str.startswith("http"): return input_str
        
        clean_input = unquote(input_str).strip().lower()
        
        # 2. Tam Eşleşme (%100)
        if clean_input in self.sites_config:
            return await self._finalize_target(clean_input)

        # 3. Bulanık Arama (Fuzzy Search)
        matches = []
        for key, data in self.sites_config.items():
            site_name = data.get('name', '').lower()
            
            # Hem 'key' (one-piece) hem 'name' (One Piece) ile benzerliğe bak
            ratio_key = SequenceMatcher(None, clean_input, key).ratio()
            ratio_name = SequenceMatcher(None, clean_input, site_name).ratio()
            score = max(ratio_key, ratio_name) * 100 
            
            if score > 40: # %40 altını hiç gösterme
                matches.append((score, key, data['name']))

        # Skorlara göre sırala
        matches.sort(key=lambda x: x[0], reverse=True)
        
        if not matches:
            print(f"⚠️ No matches found for '{input_str}'. Trying as direct link...")
            return input_str

        top_score, top_key, top_name = matches[0]

        # SENARYO A: Çok yüksek benzerlik (%80 üstü) -> OTOMATİK
        if top_score >= 80:
            self.console.print(f"✨ Auto-Match: [bold green]{top_name}[/] (Confidence: {int(top_score)}%)")
            return await self._finalize_target(top_key)
        
        # SENARYO B: Arada kaldıysa -> KULLANICIYA SOR
        else:
            self.console.print(f"\n🔍 [yellow]Ambiguous input '{input_str}'. Did you mean one of these?[/]")
            
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("Site Name", style="cyan")
            table.add_column("Confidence", justify="right")
            
            options = matches[:5] # İlk 5 sonucu göster
            for idx, (score, key, name) in enumerate(options, 1):
                color = "green" if score > 60 else "yellow"
                table.add_row(str(idx), name, f"[{color}]{int(score)}%[/]")
            
            self.console.print(table)
            
            selected_idx = IntPrompt.ask("Select number (0 to cancel)", choices=[str(i) for i in range(len(options) + 1)], default=1)
            
            if selected_idx == 0:
                print("❌ Selection cancelled.")
                return None
            
            selected_key = options[selected_idx - 1][1]
            return await self._finalize_target(selected_key)

    async def _finalize_target(self, target_key):
        """Anahtar (key) bulunduktan sonra URL'i çözer (MirrorHunter varsa çalıştırır)"""
        site_data = self.sites_config[target_key]
        site_type = site_data.get("type", "static")
        
        if site_type == "dynamic" and MirrorHunter:
            print(f"🌍 Auto-Discovery: Resolving '{target_key}'...")
            test_path = site_data.get("test_path", "/")
            hunter = MirrorHunter(debug=self.debug)
            active_mirror = await hunter.find_active_mirror(site_data["base_domain"], test_path=test_path)
            
            if active_mirror:
                print(f"✅ TARGET LOCKED: {active_mirror}")
                if "url_pattern" in site_data:
                    return site_data["url_pattern"].replace("{mirror}", active_mirror)
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
                return

            manga_title = manga_info['title']
            
            # --- ANILIST METADATA ÇEKİMİ ---
            print(f"🧬 Fetching AniList Metadata for '{manga_title}'...")
            rich_meta = await self.anilist.fetch_metadata(manga_title)
            
            safe_title = "".join([c for c in manga_title if c.isalnum() or c in (' ', '-', '_')]).strip()
            manga_path = os.path.join(self.output_dir, safe_title)
            os.makedirs(manga_path, exist_ok=True)
            
            print(f"📘 Target: {manga_title}")
            
            all_chapters = await extractor.get_chapters(url)
            chapters = self._filter_chapters(all_chapters, chapter_range)
            
            if not chapters:
                print("❌ No chapters found.")
                return

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
            start_end = range_str.split('-')
            start = float(start_end[0])
            end = float(start_end[1]) if len(start_end) > 1 else start
            
            filtered = []
            for chap in chapters:
                import re
                match = re.search(r'(\d+(\.\d+)?)', chap['title'])
                if match:
                    num = float(match.group(1))
                    if start <= num <= end:
                        filtered.append(chap)
            return filtered
        except:
            return chapters

    async def _download_single_chapter(self, extractor, chapter, parent_path, manga_title, progress, rich_meta=None):
        # 1. Bölüm bazlı temel meta (Sayı, başlık)
        base_meta = parse_chapter_metadata(chapter['title'], manga_title, chapter['url'])
        
        # 2. AniList verisiyle birleştir (Yazar, Tür, Özet)
        full_meta = {**base_meta}
        if rich_meta:
            full_meta.update(rich_meta)

        clean_title = "".join([c for c in chapter['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        chapter_folder = os.path.join(parent_path, clean_title)
        os.makedirs(chapter_folder, exist_ok=True)

        try:
            pages = await extractor.get_pages(chapter['url'])
            if not pages:
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
                # Zenginleştirilmiş Metadata ile CBZ oluştur
                if await loop.run_in_executor(None, create_cbz_archive, chapter_folder, cbz_path, full_meta):
                    shutil.rmtree(chapter_folder)
                    success = True
            else:
                success = True 

            if success:
                self.db.mark_completed(manga_title, chapter['title'])
                # Ekrana basarken Yazarı da göster (Hava atma noktası)
                author_txt = f" | {full_meta.get('writer')}" if full_meta.get('writer') else ""
                progress.console.print(f"[green]✅ Finished: {clean_title} (Meta: #{full_meta['number']}{author_txt})[/green]")

        except Exception as e:
            progress.console.print(f"[red]Failed {chapter['title']}: {e}[/red]")
            if self.debug: logger.exception("Traceback")