import re
from urllib.parse import unquote

def parse_chapter_metadata(chapter_title: str, series_title: str, url: str) -> dict:
    """
    Hem BAŞLIKTAN hem de URL'den bölüm numarası avlayan akıllı fonksiyon.
    """
    meta_number = ""
    meta_subtitle = ""
    
    # 1. TEMİZLİK: Başlık ve URL'i analize hazırla
    clean_title = chapter_title.strip()
    clean_url = unquote(url).strip().lower() # URL'deki %20'leri temizle
    
    # --- YÖNTEM A: Başlıktan Dene (Klasik) ---
    # Regex: Chapter/Ch/No kelimesinden sonraki sayıyı yakalar
    match_title = re.search(r'(?:chapter|ch\.?|no\.?|episode)\s*(\d+(\.\d+)?)', clean_title, re.IGNORECASE)
    
    if match_title:
        meta_number = match_title.group(1)
        # Alt başlığı ayıkla (Chapter 5: The End -> The End)
        meta_subtitle = re.sub(r'(?:chapter|ch\.?|no\.?|episode)\s*(\d+(\.\d+)?)[\s:-]*', '', clean_title, flags=re.IGNORECASE).strip()
    
    # --- YÖNTEM B: Başlık Çuvalladıysa URL'e Bak (Senin istediğin özellik) ---
    if not meta_number:
        # Link genelde şöyledir: .../bleach-chapter-5 veya .../chapter-5-raw
        # URL'in sonundaki veya ortasındaki "chapter-5" yapısını arıyoruz
        match_url = re.search(r'(?:chapter|ch|c)[-_]?(\d+(\.\d+)?)', clean_url)
        
        if match_url:
            print(f"⚠️ Title confusing ('{clean_title}'). Extracted #{match_url.group(1)} from URL instead.")
            meta_number = match_url.group(1)
            meta_subtitle = f"Chapter {meta_number}" # Başlık yoksa uydur

    # Hâlâ numara yoksa (Örn: "Oneshot")
    if not meta_number:
        # Son çare: Başlıktaki İLK sayıyı al (Tehlikeli ama bazen işe yarar)
        match_fallback = re.search(r'(\d+(\.\d+)?)', clean_title)
        if match_fallback:
             meta_number = match_fallback.group(1)
        else:
             meta_number = "0" # Hiçbir şey yoksa 0 ver

    if not meta_subtitle:
        meta_subtitle = clean_title

    return {
        "series": series_title,
        "number": meta_number,
        "title": meta_subtitle,
        "web": url,
        "original_title": chapter_title
    }

# generate_comic_info_xml FONKSİYONU AYNI KALACAK (Ona dokunmana gerek yok)
def generate_comic_info_xml(metadata: dict) -> str:
    # ... (eski kodun aynısı) ...
    def clean(val):
        return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    series = clean(metadata.get('series', ''))
    title = clean(metadata.get('title', ''))
    number = clean(metadata.get('number', ''))
    web = clean(metadata.get('web', ''))
    
    writer = clean(metadata.get('writer', ''))
    artist = clean(metadata.get('artist', ''))
    genres = clean(metadata.get('genres', ''))
    summary = clean(metadata.get('summary', ''))
    year = clean(metadata.get('year', ''))

    return f"""<?xml version="1.0"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>{title}</Title>
  <Series>{series}</Series>
  <Number>{number}</Number>
  <Writer>{writer}</Writer>
  <Penciller>{artist}</Penciller>
  <Genre>{genres}</Genre>
  <Summary>{summary}</Summary>
  <Year>{year}</Year>
  <Web>{web}</Web>
  <Manga>YesAndRightToLeft</Manga>
</ComicInfo>
"""