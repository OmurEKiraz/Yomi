import requests
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

class MirrorHunter:
    def __init__(self, debug=False):
        self.debug = debug
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        }

    def check_mirror(self, url):
        """
        URL'ye gider ve SON DURAK (Final Destination) adresini döner.
        """
        try:
            # allow_redirects=True kritik!
            resp = requests.get(url, headers=self.headers, timeout=5, stream=True, allow_redirects=True)
            
            if resp.status_code == 200:
                # Zombi kontrolü
                try:
                    chunk = next(resp.iter_content(1024), b"")
                    if len(chunk) > 500:
                        # 🔥 BURASI ÇOK ÖNEMLİ:
                        # resp.url, yönlendirmelerden sonraki son adrestir.
                        # w1'e girdin, w22'ye attıysa, resp.url w22 olur.
                        return resp.url 
                except:
                    pass
            return None
        except:
            return None

    def find_active_mirror(self, base_domain, test_path="/", max_w=60):
        print(f"🔍 Hunter Active: Probing deep links for {base_domain}...")
        
        candidates = []
        for i in range(1, max_w + 1):
            prefixes = [f"w{i}", f"ww{i}", f"w{i:02d}"]
            for p in prefixes:
                full_url = f"https://{p}.{base_domain}{test_path}"
                candidates.append(full_url)

        with ThreadPoolExecutor(max_workers=30) as executor:
            # Future -> Original URL eşleşmesine gerek yok, sonucu direkt alacağız
            futures = [executor.submit(self.check_mirror, url) for url in candidates]
            
            for future in futures:
                final_url = future.result()
                if final_url:
                    # Final URL'den temiz domaini (netloc) çekip alalım
                    # Örn: https://w22.sololeveling-manga.net/manga/chapter-1 -> w22.sololeveling-manga.net
                    parsed = urlparse(final_url)
                    clean_mirror = f"{parsed.scheme}://{parsed.netloc}"
                    
                    if self.debug: print(f"✅ FOUND & RESOLVED MIRROR: {clean_mirror}")
                    return clean_mirror
        
        print("❌ No active mirror found!")
        return None