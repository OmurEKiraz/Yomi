import os
import logging
import shutil
import json
import asyncio
import aiohttp
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.logging import RichHandler

# Import Async Extractor & Utils
from .extractors.common import AsyncGenericMangaExtractor
from .database import YomiDB
from .utils.archive import create_cbz_archive, create_pdf_document
from .utils.metadata import parse_chapter_metadata

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
        self.workers = workers # Eşzamanlı istek limiti (Semaphore)
        self.format = format.lower()
        self.debug = debug
        self.proxy = proxy
        
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
        Hedef URL'yi çözer. Dinamik aynaları (Mirror) bulur.
        """
        if input_str.startswith("http"): return input_str
        
        if input_str in self.sites_config:
            site_data = self.sites_config[input_str]
            site_type = site_data.get("type", "static")
            
            if site_type == "dynamic" and MirrorHunter:
                print(f"🌍 Auto-Discovery: Resolving '{input_str}'...")
                test_path = site_data.get("test_path", "/")
                
                # Async Hunter Başlat
                hunter = MirrorHunter(debug=self.debug)
                # Önce önbelleğe bakar, yoksa tarar
                active_mirror = await hunter.find_active_mirror(site_data["base_domain"], test_path=test_path)
                
                if active_mirror:
                    print(f"✅ TARGET LOCKED: {active_mirror}")
                    if "url_pattern" in site_data:
                        return site_data["url_pattern"].replace("{mirror}", active_mirror)
                    return active_mirror
                else:
                    print(f"❌ ERROR: Could not resolve mirror for {input_str}")
                    return None
                    
            elif "url" in site_data:
                return site_data['url']
        return input_str

    def download_manga(self, target: str, chapter_range: str = None):
        """
        Ana giriş noktası. Async döngüsünü (Event Loop) başlatır.
        """
        try:
            asyncio.run(self._download_manga_async(target, chapter_range))
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")

    async def _download_manga_async(self, target: str, chapter_range: str):
        # 1. Hedefi Çöz (Async olarak bekle)
        url = await self._resolve_target(target)
        if not url: return

        # 2. Bağlantı Havuzunu Kur
        connector = aiohttp.TCPConnector(limit=self.workers)
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            extractor = AsyncGenericMangaExtractor(session)

            print(f"🔍 Analyzing: {url}...")
            manga_info = await extractor.get_manga_info(url)
            manga_title = manga_info['title']
            
            # Klasör adını temizle
            safe_title = "".join([c for c in manga_title if c.isalnum() or c in (' ', '-', '_')]).strip()
            manga_path = os.path.join(self.output_dir, safe_title)
            os.makedirs(manga_path, exist_ok=True)
            
            print(f"📘 Target: {manga_title}")
            
            # Bölümleri Çek
            all_chapters = await extractor.get_chapters(url)
            chapters = self._filter_chapters(all_chapters, chapter_range)
            
            if not chapters:
                print("❌ No chapters found.")
                return

            print(f"🚀 Queued {len(chapters)} chapters...")

            # İndirme Döngüsü
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(f"[green]Downloading {manga_title}", total=len(chapters))
                
                for chapter in chapters:
                    # DB Kontrolü (Senkron ama hızlı olduğu için sorun yok)
                    if self.db.is_completed(manga_title, chapter['title']):
                        progress.console.print(f"[dim]Skipping {chapter['title']} (Already Downloaded)[/dim]")
                        progress.advance(task)
                        continue

                    # Tek Bölümü İndir (Async)
                    await self._download_single_chapter(extractor, chapter, manga_path, manga_title, progress)
                    progress.advance(task)

        self.db.close()

    def _filter_chapters(self, chapters, range_str):
        if not range_str: return chapters
        try:
            start, end = map(float, range_str.split('-'))
            filtered = []
            for chap in chapters:
                import re
                match = re.search(r'(\d+(\.\d+)?)', chap['title'])
                if match and start <= float(match.group(1)) <= end:
                    filtered.append(chap)
            return filtered
        except:
            return chapters

    async def _download_single_chapter(self, extractor, chapter, parent_path, manga_title, progress):
        # Metadata Analizi
        meta = parse_chapter_metadata(chapter['title'], manga_title, chapter['url'])
        clean_title = "".join([c for c in chapter['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        chapter_folder = os.path.join(parent_path, clean_title)
        os.makedirs(chapter_folder, exist_ok=True)

        try:
            # Sayfaları Bul (Async)
            pages = await extractor.get_pages(chapter['url'])
            if not pages:
                if self.debug: logger.warning(f"⚠️  No pages found for {chapter['title']}")
                return

            # Resimleri İndir (Hepsi aynı anda!)
            tasks = []
            for idx, img_url in enumerate(pages):
                ext = "jpg"
                if ".png" in img_url.lower(): ext = "png"
                elif ".webp" in img_url.lower(): ext = "webp"
                
                fname = f"{idx+1:03d}.{ext}"
                save_path = os.path.join(chapter_folder, fname)
                # İndirme görevini listeye ekle
                tasks.append(extractor.download_image(img_url, save_path))
            
            # Tüm resimleri paralel indir
            await asyncio.gather(*tasks)

            # Arşivleme (CPU İşlemi - Ana döngüyü bloklamaması için Thread'e atıyoruz)
            loop = asyncio.get_running_loop()
            success = False
            
            if self.format == "pdf":
                pdf_path = os.path.join(parent_path, f"{clean_title}.pdf")
                if await loop.run_in_executor(None, create_pdf_document, chapter_folder, pdf_path):
                    shutil.rmtree(chapter_folder)
                    success = True
            
            elif self.format == "cbz":
                cbz_path = os.path.join(parent_path, f"{clean_title}.cbz")
                if await loop.run_in_executor(None, create_cbz_archive, chapter_folder, cbz_path, meta):
                    shutil.rmtree(chapter_folder)
                    success = True
            else:
                success = True # Klasör modu

            if success:
                self.db.mark_completed(manga_title, chapter['title'])
                progress.console.print(f"[green]✅ Finished: {clean_title} (Meta: #{meta['number']})[/green]")

        except Exception as e:
            progress.console.print(f"[red]Failed {chapter['title']}: {e}[/red]")
            if self.debug: logger.exception("Traceback")