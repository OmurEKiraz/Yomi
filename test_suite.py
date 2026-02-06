import os
import sys
import subprocess
import time
import zipfile
import glob
import re

# --- AYARLAR ---
DOWNLOAD_DIR = "downloads"
SCENARIOS = [
    {
        "name": "BLEACH (PDF Test)",
        "target": "bleach",
        "range": "15-16",
        "format": "pdf",
        "expected_folder": "Bleach",
        "keywords": ["15", "16"]
    },
    {
        "name": "SOLO LEVELING (CBZ + Nangca Test)",
        "target": "solo-leveling",
        "range": "110-111",
        "format": "cbz",
        "expected_folder": "Solo Leveling",
        "keywords": ["110", "111"],
        "check_metadata": True
    },
    {
        "name": "ONE PIECE (CBZ + Dynamic Mirror Test)",
        "target": "one-piece",
        "range": "1040-1041",
        "format": "cbz",
        "expected_folder": "One Piece",
        "keywords": ["1040", "1041"],
        "check_metadata": True
    }
]

def print_status(msg, status="INFO"):
    colors = {
        "INFO": "\033[94m",    # Mavi
        "SUCCESS": "\033[92m", # Yeşil
        "ERROR": "\033[91m",   # Kırmızı
        "WARN": "\033[93m",    # Sarı
        "RESET": "\033[0m"
    }
    print(f"{colors.get(status, '')}[{status}] {msg}{colors['RESET']}")

def verify_pdf(path):
    """PDF dosyasının başlığını (Magic Bytes) kontrol eder."""
    try:
        with open(path, 'rb') as f:
            header = f.read(4)
            if header == b'%PDF':
                return True
            return False
    except:
        return False

def inspect_cbz(path):
    """CBZ dosyasını açar ve ComicInfo.xml kontrolü yapar."""
    try:
        with zipfile.ZipFile(path, 'r') as z:
            # 1. Test: Dosya bozuk mu?
            if z.testzip() is not None:
                return False, "Corrupted ZIP"
            
            # 2. Test: ComicInfo.xml var mı?
            if "ComicInfo.xml" in z.namelist():
                with z.open("ComicInfo.xml") as xml:
                    content = xml.read().decode('utf-8')
                    return True, content
            else:
                return False, "Missing ComicInfo.xml"
    except zipfile.BadZipFile:
        return False, "Bad Zip File"
    except Exception as e:
        return False, str(e)

def run_benchmark():
    print_status("🚀 YOMI ULTIMATE BENCHMARK STARTED", "INFO")
    print("=" * 60)

    for scenario in SCENARIOS:
        print(f"\n👉 SCENARIO: {scenario['name']}")
        print(f"   Target: {scenario['target']} | Range: {scenario['range']} | Format: {scenario['format']}")
        
        # 1. İndirme Komutu
        cmd = [
            sys.executable, "-m", "yomi.cli", "download",
            "-u", scenario['target'],
            "-r", scenario['range'],
            "-w", "16",
            "-f", scenario['format'],
            "--debug"
        ]
        
        try:
            # Komutu çalıştır
            result = subprocess.run(cmd, check=False) # check=False hata olsa bile devam etsin
            if result.returncode != 0:
                print_status(f"Command failed for {scenario['target']}", "ERROR")
                continue
        except Exception as e:
            print_status(f"Execution Error: {e}", "ERROR")
            continue

        # 2. Dosya Doğrulama (Forensics)
        target_path = os.path.join(DOWNLOAD_DIR, scenario['expected_folder'])
        if not os.path.exists(target_path):
            print_status(f"Klasör bulunamadı: {target_path}", "ERROR")
            continue

        # Klasördeki dosyaları bul
        found_files = []
        for kw in scenario['keywords']:
            # Regex ile dosya arama (örn: "*Chapter 15*.pdf")
            pattern = f"*{kw}*.{scenario['format']}"
            search_path = os.path.join(target_path, pattern)
            matches = glob.glob(search_path)
            
            if matches:
                found_files.append(matches[0])
            else:
                print_status(f"Dosya EKSİK: Chapter {kw} ({scenario['format']})", "ERROR")

        # 3. İçerik Analizi
        for fpath in found_files:
            filename = os.path.basename(fpath)
            
            # PDF Kontrolü
            if scenario['format'] == 'pdf':
                if verify_pdf(fpath):
                    print_status(f"✅ PDF Valid: {filename}", "SUCCESS")
                else:
                    print_status(f"❌ PDF CORRUPTED: {filename}", "ERROR")

            # CBZ Kontrolü
            elif scenario['format'] == 'cbz':
                is_valid, msg = inspect_cbz(fpath)
                if is_valid:
                    print_status(f"✅ CBZ Valid: {filename}", "SUCCESS")
                    if scenario.get('check_metadata'):
                        # Metadata'yı kısaca göster
                        match = re.search(r'<Title>(.*?)</Title>', msg)
                        title = match.group(1) if match else "Unknown"
                        print(f"      └── 🧠 Metadata Found: Title='{title}'")
                else:
                    if msg == "Missing ComicInfo.xml":
                        print_status(f"⚠️  CBZ OK but NO METADATA: {filename}", "WARN")
                    else:
                        print_status(f"❌ CBZ CORRUPTED: {filename} ({msg})", "ERROR")

        time.sleep(2) # Nefes payı

    print("\n" + "=" * 60)
    print_status("🏁 BENCHMARK COMPLETED", "INFO")

if __name__ == "__main__":
    run_benchmark()