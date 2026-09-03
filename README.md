# BuzzHeavier Keeper & Link Resolver 🐝

A fast, lightweight Python tool and automated GitHub Action to resolve direct download links, extract CDN endpoints, and keep BuzzHeavier files active without consuming excessive bandwidth.

---

## ⚡ Features

- **🚀 Ultra-Fast Resolution:** Uses `curl-cffi` with browser TLS fingerprint impersonation (`chrome124` / `chrome131`) to bypass Cloudflare protection in ~1 second without running heavy headless browsers.
- **🛡️ Bandwidth-Friendly Keep-Alive:** Uses HTTP Range requests (`Range: bytes=-1`) to download only the **last 1 byte** of large files (e.g. 15GB+ files) to ping the CDN and keep links alive with virtually zero bandwidth usage.
- **🔗 Dual Link Extraction:**
  - **Tokenized Link:** `https://buzzheavier.com/<id>/download?t=...` (HMAC-SHA256 signed URL).
  - **Direct CDN Stream URL:** `https://ts.buzzheavier.com/d/<id>?v=...` (High-speed direct stream URL for tools like `curl`, `aria2`, `IDM`).
- **📋 Batch Processing:** Process multiple links from a text file (`links.txt`).
- **🤖 Automated GitHub Action:** Daily scheduled workflow that automatically checks every link in `links.txt` and logs results to GitHub Actions Step Summary.
- **🔍 Byte Inspection:** Verify stream health by downloading and inspecting the first 1 byte (`-b`), last 1 byte (`-l`), or full file (`-d`).

---

## 📦 Installation

Ensure you have Python 3.10+ installed:

```bash
git clone https://github.com/AnCry1596/Buzzheavier-Keeper.git
cd Buzzheavier-Keeper
pip install -r requirements.txt
```

---

## 💻 Usage

### 1. Resolve Single Link or File ID
```bash
python get_download_link.py yebbjo1kfx3b
# or with full URL
python get_download_link.py https://buzzheavier.com/yebbjo1kfx3b
```

### 2. Download Only the Last 1 Byte (`-l`)
Ping the CDN and download just the last 1 byte of the file:
```bash
python get_download_link.py yebbjo1kfx3b -l
```

### 3. Download Only the First 1 Byte (`-b`)
Inspect the first byte (e.g., file header or UTF-8 BOM):
```bash
python get_download_link.py yebbjo1kfx3b -b
```

### 4. Download Both First and Last Byte
```bash
python get_download_link.py yebbjo1kfx3b -b -l
```

### 5. Download Full File (`-d`)
Stream the entire file to disk with a progress display:
```bash
python get_download_link.py yebbjo1kfx3b -d
```

### 6. Batch Keep-Alive (`links.txt`)
Ping the last byte of every link listed in `links.txt`:
```bash
python get_download_link.py links.txt -l
```

### 7. Output as JSON (`--json`)
For integration into automated scripts:
```bash
python get_download_link.py yebbjo1kfx3b --json
```

---

## ⚙️ Automated GitHub Action (Daily Keep-Alive)

The repository includes a GitHub Actions workflow in [`.github/workflows/daily_check.yml`](.github/workflows/daily_check.yml).

### How It Works:
1. Add your file links to `links.txt` (one link per line):
   ```text
   https://buzzheavier.com/1z8c4seiafor
   https://buzzheavier.com/yebbjo1kfx3b
   ```
2. Commit and push your changes to GitHub.
3. The workflow runs **every day at 03:00 UTC** (and on every push to `links.txt`).
4. It downloads the last 1 byte of each link and publishes a clean summary table under the **Actions** tab.

---

## ⚠️ Disclaimers

> [!IMPORTANT]
> **Please read this disclaimer carefully before using this software.**

1. **Educational & Personal Use Only:**
   This project is developed solely for educational, research, and personal file management purposes. It demonstrates HTTP protocol range requests, TLS fingerprinting, and automated workflow integrations.

2. **No Affiliation:**
   This project is an independent open-source tool and is **not** affiliated, associated, authorized, endorsed by, or in any way officially connected with BuzzHeavier (`buzzheavier.com`), its parent company, or any of its subsidiaries.

3. **Fair Use & Bandwidth Consideration:**
   This tool is intentionally designed to minimize server load and bandwidth consumption by utilizing standard HTTP Range requests (`bytes=-1` / 1 byte) rather than repeatedly downloading complete files. Users are advised to respect reasonable request rates and avoid abusive flooding.

4. **Terms of Service & Compliance:**
   Users are solely responsible for ensuring that their use of this software complies with the Terms of Service of the respective hosting platform and all applicable local, national, and international laws.

5. **No Warranty / Limitation of Liability:**
   This software is provided "as is", without warranty of any kind, express or implied. The author(s) and contributor(s) shall not be held liable for any claims, damages, account suspensions, or other liabilities arising from the use or misuse of this codebase.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
