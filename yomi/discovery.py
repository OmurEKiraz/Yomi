import asyncio
import aiohttp
import logging
import json
import os

logger = logging.getLogger("YomiCore")

class MirrorHunter:
    """
    Smart Hunter v2.1 - Robust & Polite
    """
    def __init__(self, debug=False, cache_file="mirrors_cache.json"):
        self.debug = debug
        self.cache_file = cache_file
        self.cache = self._load_cache()
        # Tarayıcı gibi görünmek için Header şart
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self, domain_key, active_url):
        self.cache[domain_key] = active_url
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            if self.debug: logger.error(f"Failed to save cache: {e}")

    async def check_mirror(self, session, url):
        try:
            if self.debug: logger.debug(f"Probing: {url}")
            # FIX: HEAD yerine GET kullanıyoruz. Bazı siteler HEAD'i engeller.
            # allow_redirects=True önemli, bazen w1 -> ana sayfaya yönlendirir.
            async with session.get(url, headers=self.headers, timeout=5, allow_redirects=True) as response:
                if response.status == 200:
                    # URL geçerliyse dön (Yönlendirme olduysa son URL'i al)
                    return str(response.url).rstrip('/')
        except:
            pass
        return None

    async def find_active_mirror(self, base_domain: str, test_path: str = "/") -> str:
        domain_key = base_domain.replace("www.", "")
        
        # FIX: Concurrency Limit (Aynı anda 60 yerine 10 istek)
        connector = aiohttp.TCPConnector(limit=10) 
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # --- ADIM 1: ÖNBELLEK KONTROLÜ ---
            cached_url = self.cache.get(domain_key)
            if cached_url:
                if self.debug: logger.info(f"🧠 Checking cached mirror: {cached_url}")
                # Test path ekleyip kontrol et
                full_test_url = cached_url.rstrip('/') + test_path
                if await self.check_mirror(session, full_test_url):
                    if self.debug: logger.info("⚡ Cache Hit! Skipping scan.")
                    return cached_url
                else:
                    if self.debug: logger.warning("⚠️ Cached mirror dead. Initiating full scan...")

            # --- ADIM 2: TARAMA ---
            print(f"📡 Scanning mirrors for {base_domain}...")
            
            tasks = []
            
            # Standartlar
            protocols = ["https://", "https://www.", "https://w.", "https://ww."]
            for p in protocols:
                full_url = f"{p}{base_domain}{test_path}"
                tasks.append(self.check_mirror(session, full_url))

            # w1 - w60 (Sayıyı artırabiliriz ama 60 genelde yeterli)
            for i in range(1, 61):
                tasks.append(self.check_mirror(session, f"https://w{i}.{base_domain}{test_path}"))
                tasks.append(self.check_mirror(session, f"https://ww{i}.{base_domain}{test_path}"))

            # İstekleri başlat
            for future in asyncio.as_completed(tasks):
                result = await future
                if result:
                    # Bulunan URL, test_path (örn: /manga/solo...) içeriyor olabilir.
                    # Onu temizleyip ana domaini almamız lazım.
                    
                    # Basit yöntem: result zaten yönlendirilmiş son URL. 
                    # Eğer test_path URL'in sonundaysa kesip atalım.
                    
                    # Örneğin result: https://w1.sololeveling-manga.net/manga/solo-leveling-chapter-1
                    # test_path: /manga/solo-leveling-chapter-1
                    
                    # Ancak yönlendirme olduysa URL değişmiş olabilir. 
                    # Garanti yöntem: Netloc (Domain) almak.
                    from urllib.parse import urlparse
                    parsed = urlparse(result)
                    root_url = f"{parsed.scheme}://{parsed.netloc}"
                    
                    self._save_cache(domain_key, root_url)
                    return root_url

        return None