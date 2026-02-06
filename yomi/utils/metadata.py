import re

def parse_chapter_metadata(chapter_title: str, series_title: str, url: str) -> dict:
    """
    Bölüm başlığından (String) anlamlı veriler (Sayı, Alt Başlık) çıkarır.
    Örn: "One Piece Chapter 1050: Honor" -> {number: 1050, title: Honor}
    """
    meta_number = ""
    meta_subtitle = ""

    # Regex: "Chapter" veya "No." kelimesinden sonraki sayıyı ve metni ayıklar
    # Grup 1: Sayı (1050 veya 1050.5)
    # Grup 3: Başlık (Honor)
    match = re.search(r'(?:chapter|ch\.?|no\.?)\s*(\d+(\.\d+)?)[\s:-]*(.*)', chapter_title, re.IGNORECASE)

    if match:
        meta_number = match.group(1)
        meta_subtitle = match.group(3).strip()
        # Eğer başlık yoksa otomatik oluştur
        if not meta_subtitle:
            meta_subtitle = f"Chapter {meta_number}"
    else:
        # Sayı bulamazsa olduğu gibi bırak
        meta_subtitle = chapter_title

    return {
        "series": series_title,
        "number": meta_number,
        "title": meta_subtitle,
        "web": url,
        "original_title": chapter_title
    }

def generate_comic_info_xml(metadata: dict) -> str:
    """
    CBZ dosyaları için ComicInfo.xml içeriği üretir.
    """
    # XML uyumluluğu için kaçış karakterleri
    series = str(metadata.get('series', '')).replace("&", "&amp;").replace("<", "&lt;")
    title = str(metadata.get('title', '')).replace("&", "&amp;").replace("<", "&lt;")
    number = str(metadata.get('number', ''))
    web = str(metadata.get('web', ''))

    return f"""<?xml version="1.0"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>{title}</Title>
  <Series>{series}</Series>
  <Number>{number}</Number>
  <Web>{web}</Web>
  <Manga>YesAndRightToLeft</Manga>
</ComicInfo>
"""