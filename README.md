# 🐇 Yomi - Speed Organized Manga Downloader

> **The Universal, Hybrid-Engine Manga Downloader.** > *Bypasses protection. Auto-resumes. Converts to PDF/CBZ.*

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**Yomi** is a CLI tool designed for speed and resilience. It uses a **Hybrid Engine** (curl_cffi + requests) to bypass Cloudflare and scraping protections, ensuring you get high-quality images every time.


## ✨ Features

* **🚀 Hybrid Engine:** Smartly switches between `curl_cffi` (to scrape) and `requests` (to download) to defeat "0-byte" ghost files.
* **🧠 Auto-Resume:** Tracks your history in a local SQLite DB. Crashed? Restart and it continues exactly where it left off.
* **📚 Universal Support:** Optimized for Manganato, Manganelo, and 1000+ WordPress-based sites (Asura, Reaper, Flame, W5).
* **📦 Smart Conversion:** Auto-converts chapters to **PDF** or **CBZ** formats.
* **🔍 Built-in Search:** Search for manga directly from your terminal.
* **🎯 Range Selection:** Download specific chapters (e.g., `-r "1-10"`) or fill gaps (`-r "50-60"`).
* **🛡️ Proxy Support:** Built-in tunneling for bypassing region blocks.



## 🛠️ Installation

# 1. Clone the repo
git clone [https://github.com/YOUR_USERNAME/Yomi.git](https://github.com/YOUR_USERNAME/Yomi.git)
cd Yomi

# 2. Create virtual env
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
📖 Usage
1. 🔍 Search for Manga
Find the exact URL for your series using the massive Manganato database.
python -m yomi.cli search "solo leveling"

2. ⬇️ Download
The classic command. Downloads images into folders by default.
python -m yomi.cli download -u "URL_HERE"


3. 📦 Download as PDF or CBZ
Auto-convert chapters into single files.
python -m yomi.cli download -u "URL_HERE" -f pdf
python -m yomi.cli download -u "URL_HERE" -f cbz


4. 🎯 Download Specific Chapters
Only want chapters 10 through 20?
python -m yomi.cli download -u "URL_HERE" -r "10-20"


5. ⚡ Turbo Mode (Workers)
Increase threads for faster downloads (Default: 8).
python -m yomi.cli download -u "URL_HERE" -w 16


6. 🛡️ Use a Proxy
Bypass IP bans or geoblocks.
python -m yomi.cli download -u "URL_HERE" -p "[http://user:pass@1.2.3.4:8080](http://user:pass@1.2.3.4:8080)"


🧩 Supported Sites
Yomi works on Generic Mode for almost any WordPress-based manga site. Verified specific support for:

✅ Manganato / Manganelo (Search & DL)

✅ Asura Scans

✅ Flame Comics

✅ Reaper Scans

✅ W5 / W3 Mirrors (Rent-a-Girlfriend, etc.)

Check supported sites list:
python -m yomi.cli available


🤝 Contributing
Pull requests are welcome!

Fork the Project

Create your Feature Branch (git checkout -b feature/AmazingFeature)

Commit your Changes (git commit -m 'Add some AmazingFeature')

Push to the Branch (git push origin feature/AmazingFeature)

Open a Pull Request