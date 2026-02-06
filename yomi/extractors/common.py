import logging
import requests
import re
import json
from typing import List, Dict
from bs4 import BeautifulSoup
from .base import BaseExtractor
from urllib.parse import urljoin, unquote

logger = logging.getLogger("YomiCore")

class GenericMangaExtractor(BaseExtractor):
    """
    Universal Extractor v0.5 - Sherlock & Nangca Edition
    """
    def __init__(self, proxy=None):
        super().__init__(proxy)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://google.com"
        })
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})

    @property
    def base_url(self) -> str:
        return "generic"

    def get_soup(self, url):
        logger.debug(f"🌐 GET: {url}")
        # allow_redirects=True çok önemli, w1 -> w22 yönlendirmesi için
        resp = self.session.get(url, timeout=20, allow_redirects=True)
        return BeautifulSoup(resp.content, 'html.parser'), resp.text

    def get_manga_info(self, url: str) -> Dict[str, str]:
        # Bölüm linki geldiyse ana seriyi bul
        if "chapter-" in url.lower() or "/chapter/" in url.lower():
            soup, _ = self.get_soup(url)
            parent_url = self._find_parent_url(soup, url)
            if parent_url: return self.get_manga_info(parent_url)

        soup, _ = self.get_soup(url)
        title = "Unknown Manga"
        selectors = ["div.post-title h1", "h1.entry-title", "div.big-title h1", "h1", "title"]
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag:
                title = tag.get_text(strip=True)
                break
        
        clean_title = title.replace("Manga", "").replace("Read", "").replace("Online", "").strip()
        clean_title = clean_title.strip("-").strip()
        return {"title": clean_title, "url": url}

    def get_chapters(self, manga_url: str) -> List[Dict]:
        if "chapter-" in manga_url.lower():
            soup, _ = self.get_soup(manga_url)
            parent_url = self._find_parent_url(soup, manga_url)
            if parent_url and parent_url != manga_url:
                return self.get_chapters(parent_url)

        soup, _ = self.get_soup(manga_url)
        manga_info = self.get_manga_info(manga_url)
        series_title = manga_info['title'].lower()
        
        chapters = []
        seen_urls = set()

        madara_chapters = soup.select('li.wp-manga-chapter a')
        target_links = madara_chapters if madara_chapters else soup.select("a")

        for link in target_links:
            href = link.get('href')
            text = link.get_text(strip=True)
            if not href: continue
            
            full_url = urljoin(manga_url, href)
            
            # --- FİLTRELER ---
            # Kendi kendine yönlendirme koruması
            if full_url.strip('/') == manga_url.strip('/'): continue
            if full_url in seen_urls: continue
            
            # Tuzak Butonlar ("Enjoy Reading" vb.)
            if any(x in text.lower() for x in ["enjoy reading", "start reading", "read now"]): continue
            
            # Spin-off Koruması (Ragnarok)
            if "ragnarok" in text.lower() and "ragnarok" not in series_title: continue
            
            # Sosyal Medya Linkleri
            if any(x in full_url for x in ["#", "comment", "reply", "login", "facebook", "twitter"]): continue

            is_chapter = False
            if madara_chapters and link in madara_chapters: is_chapter = True
            elif "chapter" in text.lower() and any(c.isdigit() for c in text): is_chapter = True
            elif "/chapter-" in href.lower() or "/ch-" in href.lower(): is_chapter = True

            if is_chapter:
                chapters.append({"title": text, "url": full_url})
                seen_urls.add(full_url)
        
        return list(reversed(chapters))

    def get_pages(self, chapter_url: str) -> List[str]:
        # 1. Direkt Resim Kontrolü
        if chapter_url.endswith(('.webp', '.jpg', '.png')):
             return [chapter_url]

        soup, html_content = self.get_soup(chapter_url)
        images = []
        
        # --- STRATEJİ 1: Attribute Hasatçısı (HTML Tagleri) ---
        img_tags = soup.find_all("img")
        logger.debug(f"   Harvesting attributes from {len(img_tags)} <img> tags...")
        
        for img in img_tags:
            # Tag'in tüm özelliklerini (src, data-src, data-thumb vs) gez
            for attr_name, attr_val in img.attrs.items():
                if isinstance(attr_val, list): attr_val = " ".join(attr_val)
                if not attr_val: continue
                
                val_lower = attr_val.lower().strip()
                # İçinde resim uzantısı geçiyorsa al
                if ".jpg" in val_lower or ".png" in val_lower or ".webp" in val_lower:
                    if "data:" in val_lower or "logo" in val_lower or "icon" in val_lower: continue
                    
                    full_src = urljoin(chapter_url, attr_val.strip())
                    images.append(full_src)
                    break 

        # --- STRATEJİ 2: Sherlock Regex (Nangca & Gizli JSON) ---
        if not images:
            logger.debug("   ⚠️ Attribute scan empty. Deploying SHERLOCK SCAN...")
            
            # Tırnak içindeki "dosya.jpg" formatlı her şeyi yakalar
            regex = r'["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']'
            matches = re.findall(regex, html_content)
            
            logger.debug(f"   🔎 Sherlock found {len(matches)} raw strings. Analyzing...")

            for raw_url in matches:
                # JSON kaçış karakterlerini temizle (\/ -> /)
                clean_url = raw_url.replace(r'\/', '/').replace('\\', '').strip()
                
                # Gereksizleri ele
                if any(x in clean_url.lower() for x in ["logo", "icon", "ads", "banner", "loader", "pixel", "100x", "300x"]): 
                    continue

                # 🔥 NANGCA YAMASI: Nangca linklerini koşulsuz şartsız al
                if "nangca.com" in clean_url:
                    # Protokolü düzelt (//nangca -> https://nangca)
                    if not clean_url.startswith("http"):
                        clean_url = "https:" + clean_url if clean_url.startswith("//") else "https://" + clean_url
                    
                    logger.debug(f"   🎯 Nangca Hit: {clean_url}")
                    images.append(clean_url)
                    continue

                # Diğer normal linkleri tamamla
                final_url = urljoin(chapter_url, clean_url)
                
                # Geçerli bir HTTP linki olduğundan emin ol
                if final_url.startswith("http"):
                    images.append(final_url)

        # 3. Son Temizlik (Tekrarları kaldır)
        unique_images = list(dict.fromkeys(images))
        logger.debug(f"   Final candidates: {len(unique_images)}")
        
        return unique_images

    def _find_parent_url(self, soup, current_url) -> str:
        back_link = soup.select_one("a.btn.back") or soup.select_one("a.all-chapters")
        if back_link: return urljoin(current_url, back_link.get("href"))
        breadcrumbs = soup.select(".breadcrumb a, .rank-math-breadcrumb a")
        if breadcrumbs:
            for link in reversed(breadcrumbs):
                href = link.get("href")
                if href and href != current_url and "home" not in link.get_text().lower():
                    return urljoin(current_url, href)
        return None

    def download_image(self, url, path, referer=None):
        try:
            head = self.session.headers.copy()
            if referer: head["Referer"] = referer
            
            # Timeout artırıldı (Nangca bazen yavaş cevap verir)
            with self.session.get(url, headers=head, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=32768):
                        f.write(chunk)
            return True
        except Exception as e:
            logger.debug(f"Download failed for {url}: {e}")
            return False