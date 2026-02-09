import json
import os
import re

DB_PATH = os.path.join("yomi", "sites.json")

def smart_db_cleaner():
    if not os.path.exists(DB_PATH):
        print("❌ sites.json bulunamadı!")
        return

    with open(DB_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fixed_count = 0
    
    # Regex açıklaması: 
    # \{chapter -> {chapter ile başlayan yerleri bul
    # [^}]* -> kapatma parantezi (}) görene kadar ne varsa seç
    # \}? -> eğer varsa kapatma parantezini de dahil et
    cleanup_regex = r'\{chapter[^}]*\}?'

    for key, site in data.items():
        old_pattern = site.get("url_pattern", "")
        old_test = site.get("test_path", "")

        # 1. url_pattern düzeltme
        if "{chapter" in old_pattern:
            new_pattern = re.sub(cleanup_regex, "{chapter}", old_pattern)
            if new_pattern != old_pattern:
                site["url_pattern"] = new_pattern
                fixed_count += 1

        # 2. test_path düzeltme (Test path her zaman 1. bölümü hedeflemeli)
        if "{chapter" in old_test:
            # Önce temizle sonra {chapter} yerine "1" koy
            clean_test = re.sub(cleanup_regex, "{chapter}", old_test)
            site["test_path"] = clean_test.replace("{chapter}", "1")
        elif old_test.endswith("{"): # Sonda yarım kalan varsa
            site["test_path"] = old_test.rstrip("{") + "1"

    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ İşlem Tamamlandı!")
    print(f"✨ Toplam {fixed_count} bozuk link yapısı '{' {chapter} '}' olarak standardize edildi.")
    print(f"🚀 Artık 'comic', 'read' veya 'manga' yolları korunarak linkler düzeldi.")

if __name__ == "__main__":
    smart_db_cleaner()