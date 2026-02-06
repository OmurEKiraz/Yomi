import os
import logging
import shutil
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.logging import RichHandler

from .extractors.common import GenericMangaExtractor
from .database import YomiDB

# 🔥 YENİ MODÜLLERDEN İMPORT
from .utils.archive import create_cbz_archive, create_pdf_document
from .utils.metadata import parse_chapter_metadata

try:
    from .discovery import MirrorHunter
except ImportError:
    MirrorHunter = None

logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True)]
)
logger = logging.getLogger("YomiCore")

class YomiCore:
    def __init__(self, output_dir: str = "downloads", workers: int = 4, debug: bool = False, format: str = "folder", proxy: str = None):
        self.output_dir = output_dir
        self.workers = workers
        self.format = format.lower()
        self.debug = debug
        
        if self.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("[bold red]DEBUG MODE ON[/]")
        else:
            logger.setLevel(logging.ERROR)
        
        os.makedirs(self.output_dir, exist_ok=True)
        self.extractor = GenericMangaExtractor(proxy=proxy)
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

    def _resolve_target(self, input_str: str):
        if input_str.startswith("http"): return input_str
        if input_str in self.sites_config:
            site_data = self.sites_config[input_str]
            site_type = site_data.get("type", "static")
            
            if site_type == "dynamic" and MirrorHunter:
                print(f"🌍 Auto-Discovery: Searching active mirror for '{input_str}'...")
                test_path = site_data.get("test_path", "/")
                hunter = MirrorHunter(debug=self.debug)
                active_mirror = hunter.find_active_mirror(site_data["base_domain"], test_path=test_path)
                if active_mirror:
                    print(f"✅ TARGET LOCKED: {active_mirror}")
                    if "url_pattern" in site_data:
                        return site_data["url_pattern"].replace("{mirror}", active_mirror)
                    return active_mirror
            elif "url" in site_data:
                return site_data['url']
        return input_str

    def download_manga(self, target: str, chapter_range: str = None):
        try:
            url = self._resolve_target(target)
            if not url: return

            print(f"🔍 Analyzing: {url}...")
            manga_info = self.extractor.get_manga_info(url)
            manga_title = manga_info['title']
            
            safe_title = "".join([c for c in manga_title if c.isalnum() or c in (' ', '-', '_')]).strip()
            manga_path = os.path.join(self.output_dir, safe_title)
            os.makedirs(manga_path, exist_ok=True)
            
            print(f"📘 Target: {manga_title}")
            all_chapters = self.extractor.get_chapters(url)
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

                    self._download_single_chapter(chapter, manga_path, manga_title, progress)
                    progress.advance(task)

        except Exception as e:
            print(f"❌ Critical Error: {e}")
            if self.debug: logger.exception("Traceback:")
        finally:
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

    def _download_single_chapter(self, chapter, parent_path, manga_title, progress):
        # 🔥 MODÜLER GÜÇ: Metadata analizi artık tek satır!
        meta = parse_chapter_metadata(chapter['title'], manga_title, chapter['url'])
        
        clean_title = "".join([c for c in chapter['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        chapter_folder = os.path.join(parent_path, clean_title)
        os.makedirs(chapter_folder, exist_ok=True)

        try:
            pages = self.extractor.get_pages(chapter['url'])
            if not pages:
                if self.debug: logger.warning(f"⚠️  No pages found for {chapter['title']}")
                return

            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = []
                for idx, img_url in enumerate(pages):
                    ext = "jpg"
                    if ".png" in img_url.lower(): ext = "png"
                    elif ".webp" in img_url.lower(): ext = "webp"
                    
                    fname = f"{idx+1:03d}.{ext}"
                    save_path = os.path.join(chapter_folder, fname)
                    futures.append(executor.submit(self.extractor.download_image, img_url, save_path, chapter['url']))

                for f in as_completed(futures): f.result()

            # 🔥 MODÜLER GÜÇ: Arşivleme işlemleri utils'ten çağrılıyor
            success = False
            if self.format == "pdf":
                pdf_path = os.path.join(parent_path, f"{clean_title}.pdf")
                if create_pdf_document(chapter_folder, pdf_path):
                    shutil.rmtree(chapter_folder)
                    success = True
            
            elif self.format == "cbz":
                cbz_path = os.path.join(parent_path, f"{clean_title}.cbz")
                # Metadata'yı buraya paslıyoruz
                if create_cbz_archive(chapter_folder, cbz_path, metadata=meta):
                    shutil.rmtree(chapter_folder)
                    success = True
            else:
                success = True

            if success:
                self.db.mark_completed(manga_title, chapter['title'])
                progress.console.print(f"[green]✅ Finished: {clean_title} (Meta: #{meta['number']})[/green]")

        except Exception as e:
            progress.console.print(f"[red]Failed {chapter['title']}: {e}[/red]")