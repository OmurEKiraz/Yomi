# 🐇 Yomi: The Intelligent Manga Archiver

> **"403 Forbidden? Not on my watch."**
>
> *Auto-Discovery. Anti-Protection. Smart Metadata.*

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Stable_v0.2.0-orange?style=for-the-badge)

**Yomi** is not just a downloader; it is a full-stack **Manga Archival Solution**. It is designed to hunt down active mirror sites, bypass "Access Denied" image protections (like Nangca/CDN), and package your manga into professional, metadata-tagged formats ready for media servers like **Kavita**, **Komga**, or **CDisplayEx**.


## ✨ Why Yomi?

### 🌍 1. The Hunter Engine (Auto-Discovery)
Sites like *One Piece* or *Bleach* change domains constantly (w57 -> w58). Yomi's **Hunter Engine** automatically probes potential mirrors, finds the active one, and locks onto the target. You never have to update links manually.

### 🕵️‍♂️ The Sherlock Engine (Deep Scan)
Images hidden behind `403 Forbidden` or deeply nested inside HTML/JavaScript (Nangca CDNs)? **Sherlock** parses the raw HTML, regex-matches the protected assets, and extracts them with surgical precision.

### 📚 The Librarian (Smart Metadata)
Yomi doesn't just give you a file.
* **PDF:** Clean, header-checked documents.
* **CBZ:** Embeds `ComicInfo.xml` automatically. Your reader will know the *Series Name*, *Chapter Number*, and *Title* (e.g., "Chapter 1050: Honor") instantly.

### ⚡ Turbo Mode
Built with a multi-threaded core that acts like a DDoS attack (in a good way). Downloads entire volumes in seconds.


## 🛠️ Installation

# 1. Clone the repository
git clone [https://github.com/OmurEKiraz/yomi.git](https://github.com/OmurEKiraz/yomi.git)
cd yomi

# 2. Create a virtual environment (Recommended)
##### python -m venv venv
##### Windows: .\venv\Scripts\activate
##### Linux/Mac: source venv/bin/activate

# 3. Install requirements
##### pip install -r requirements.txt


# 📖 Command Cheat Sheet
Yomi is controlled via the CLI. Here is everything you need to know.
#### ⬇️ Basic Download
Download chapters as images inside folders. 
##### python -m yomi.cli download -u "[https://site.com/manga/series-name](https://site.com/manga/series-name)"

#### 📦 Archival Mode (PDF / CBZ)Recommended. 
Downloads and converts chapters into single files
.CBZ: Includes metadata (Best for Komga/Kavita)
.PDF: Best for phone/tablet reading.
##### python -m yomi.cli download -u "URL_HERE" -f cbz
#### or
##### python -m yomi.cli download -u "URL_HERE" -f pdf
# 🎯 Range Selection
Download specific chapters, ranges, or fill missing gaps.
#### Download only chapters 10 through 20
##### python -m yomi.cli download -u "URL_HERE" -r "10-20"
#⚡ Turbo Mode (Speed)
Increase the worker threads. Default is 4.Warning: Setting this too high (e.g., 32+) might cause temporary IP bans on some sites.
# 16 Parallel Downloads
##### python -m yomi.cli download -u "URL_HERE" -w 16
# 🛡️ Proxy Support
Bypass region blocks or IP bans.
##### python -m yomi.cli download -u "URL_HERE" -p "[http://user:pass@1.2.3.4:8080](http://user:pass@1.2.3.4:8080)"
