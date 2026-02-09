import json
import os
import shutil
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt

console = Console()

# DOSYA YOLLARI
MAIN_DB = os.path.join("yomi", "sites.json")
TEST_DB = os.path.join("yomi", "sites_test.json")
BACKUP_DB = os.path.join("yomi", "sites_backup.json")

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(path, data):
    # Kaydetmeden önce alfabetik sırala (Düzenli olsun)
    sorted_data = dict(sorted(data.items()))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)

def convert_to_dynamic(slug, data):
    """sites_test formatını senin istediğin dynamic sites.json formatına çevirir"""
    return {
        "name": data.get('name', slug.replace('-', ' ').title()),
        "type": "dynamic",
        "base_domain": data.get('base_domain', ''),
        "test_path": f"/manga/{slug}-chapter-1",
        "url_pattern": "{mirror}/manga/" + slug + "-chapter-{chapter}"
    }

def main():
    console.clear()
    console.rule("[bold red]YOMI SMART MERGE TOOL (THE JUDGE - DYNAMIC EDITION)[/]")

    if not os.path.exists(TEST_DB):
        console.print("[red]Hata: sites_test.json bulunamadı![/]")
        return

    main_data = load_json(MAIN_DB)
    test_data = load_json(TEST_DB)

    # 1. YEDEKLEME
    if os.path.exists(MAIN_DB):
        shutil.copy(MAIN_DB, BACKUP_DB)
        console.print(f"[green]✅ Mevcut database yedeklendi:[/green] {BACKUP_DB}")

    new_entries = []
    updates = []
    
    # Analiz
    for slug, data in test_data.items():
        if not data.get('verified', False): continue # Sadece onaylıları al
        
        # Veriyi dynamic formata çevir
        formatted_new_data = convert_to_dynamic(slug, data)
        
        if slug not in main_data:
            new_entries.append((slug, formatted_new_data))
        else:
            # Domain değişmişse veya format güncellenecekse güncelleme listesine al
            if main_data[slug].get('base_domain') != formatted_new_data['base_domain']:
                updates.append((slug, formatted_new_data))

    console.print(f"\n[cyan]Analiz Tamamlandı:[/cyan]")
    console.print(f"✨ Yeni Eklenecek: {len(new_entries)}")
    console.print(f"🔄 Güncellenecek: {len(updates)}")
    console.print("-" * 40)

    # --- EKLEME ---
    for slug, data in new_entries:
        main_data[slug] = data
    
    # --- GÜNCELLEME (ÇAKIŞMA) ---
    if updates:
        console.print(f"\n[yellow]! {len(updates)} adet mevcut manga için yeni kaynak bulundu.[/yellow]")
        if Confirm.ask("Mevcut mangaları yeni linklerle güncelleyeyim mi?"):
            for slug, data in updates:
                main_data[slug] = data
            console.print("[green]✅ Güncellemeler uygulandı.[/green]")

    # --- KAYIT ---
    save_json(MAIN_DB, main_data)
    console.rule("[bold green]İŞLEM BAŞARILI[/]")
    console.print(f"📊 Toplam Site Sayısı: [bold white]{len(main_data)}[/bold white]")
    
    if Confirm.ask("Geçici dosya (sites_test.json) silinsin mi?", default=False):
        os.remove(TEST_DB)
        console.print("🗑️ Temizlendi.")

if __name__ == "__main__":
    main()