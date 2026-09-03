#!/usr/bin/env python3
"""
BuzzHeavier Download Link Resolver (curl-cffi edition)
Fast, lightweight link resolver and downloader for BuzzHeavier files using TLS fingerprint impersonation.
"""

import sys
import os
import re
import json
import argparse
import io
from typing import Dict, Any, Optional

# Ensure UTF-8 output across all platforms (especially Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from curl_cffi import requests
except ImportError:
    print("[!] Error: 'curl_cffi' is required for fast TLS impersonation.")
    print("    Install it using: pip install curl_cffi")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


def parse_file_id(input_val: str) -> str:
    """Extract file ID from raw ID or full BuzzHeavier URL."""
    input_val = input_val.strip()
    match = re.search(r'(?:https?://(?:buzzheavier\.com|bzzhr\.to)/)?([a-zA-Z0-9]{8,16})', input_val)
    if match:
        return match.group(1)
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', input_val)
    if cleaned:
        return cleaned
    raise ValueError(f"Could not extract a valid file ID from: {input_val}")


def resolve_buzzheavier_link(file_id: str, impersonate: str = "chrome124", timeout: int = 15) -> Dict[str, Any]:
    """
    Resolves BuzzHeavier download link and direct CDN stream URL using curl_cffi.
    """
    page_url = f"https://buzzheavier.com/{file_id}"
    result = {
        "file_id": file_id,
        "page_url": page_url,
        "file_name": None,
        "file_size": None,
        "token_link": None,
        "token": None,
        "direct_cdn_url": None,
    }

    # 1. Fetch the file landing page with automatic fallback if Cloudflare challenge is encountered
    candidate_impersonates = [impersonate]
    for alt in ["chrome131", "chrome124", "safari17_0"]:
        if alt not in candidate_impersonates:
            candidate_impersonates.append(alt)

    resp = None
    for imp in candidate_impersonates:
        session = requests.Session(impersonate=imp)
        try:
            r = session.get(page_url, timeout=timeout)
            if r.status_code == 404:
                raise RuntimeError(f"File not found (404). File ID '{file_id}' may be invalid or deleted.")
            if r.status_code == 200 and "Just a moment..." not in r.text:
                resp = r
                break
        except RuntimeError:
            raise
        except Exception:
            continue

    if not resp:
        raise RuntimeError("Cloudflare challenge encountered. Please retry or verify the link.")

    # 2. Parse title and download button
    html = resp.text
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            t = soup.title.string.strip()
            if t not in ("Buzzheavier", "Just a moment..."):
                result["file_name"] = t
        btn = soup.find("a", attrs={"hx-get": re.compile(r"download")})
        if btn:
            hx_get = btn.get("hx-get")
            btn_text = btn.get_text()
        else:
            hx_get = None
            btn_text = ""
    else:
        # Fallback regex parsing if bs4 is missing
        title_m = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
        if title_m:
            result["file_name"] = title_m.group(1).strip()
        btn_m = re.search(r'<a[^>]*hx-get=["\']([^"\']*download[^"\']*)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
        if btn_m:
            hx_get = btn_m.group(1)
            btn_text = btn_m.group(2)
        else:
            hx_get = None
            btn_text = ""

    if not hx_get:
        raise RuntimeError("Could not find download link on page. File might be protected or removed.")

    # Size extraction from button text
    size_m = re.search(r'([0-9.]+\s*(?:B|KB|MB|GB|TB))', btn_text, re.IGNORECASE)
    if size_m:
        result["file_size"] = size_m.group(1).strip()

    # Build tokenized link
    token_link = f"https://buzzheavier.com{hx_get}" if hx_get.startswith("/") else hx_get
    result["token_link"] = token_link

    token_m = re.search(r'[?&]t=([^&]+)', hx_get)
    if token_m:
        result["token"] = token_m.group(1)

    # 3. Simulate HTMX request to fetch direct CDN link from HX-Redirect
    htmx_headers = {
        "HX-Request": "true",
        "Referer": page_url,
        "HX-Current-URL": page_url,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    r_htmx = session.get(token_link, headers=htmx_headers, allow_redirects=False, timeout=timeout)
    direct_cdn = r_htmx.headers.get("hx-redirect") or r_htmx.headers.get("location")
    if direct_cdn:
        result["direct_cdn_url"] = direct_cdn

    # Also verify file name from Content-Disposition if not found yet
    if direct_cdn and not result["file_name"]:
        try:
            head_resp = session.head(direct_cdn, timeout=timeout)
            cd = head_resp.headers.get("content-disposition", "")
            cd_m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
            if cd_m:
                result["file_name"] = cd_m.group(1).strip()
        except Exception:
            pass

    return result


def download_first_byte(url: str, impersonate: str = "chrome124") -> bytes:
    """Downloads and returns the first 1 byte from the direct CDN URL."""
    session = requests.Session(impersonate=impersonate)
    # BuzzHeavier supports HTTP Range requests (HTTP 206 Partial Content)
    resp = session.get(url, headers={"Range": "bytes=0-0"})
    if resp.status_code in (200, 206) and resp.content:
        return resp.content[:1]

    # Fallback: stream and grab the first byte
    r = session.get(url, stream=True)
    r.raise_for_status()
    for chunk in r.iter_content(chunk_size=1):
        if chunk:
            return chunk[:1]
    return b""


def download_last_byte(url: str, impersonate: str = "chrome124") -> bytes:
    """Downloads and returns the last 1 byte from the direct CDN URL."""
    session = requests.Session(impersonate=impersonate)
    # HTTP Range suffix request: bytes=-1 requests the last 1 byte
    resp = session.get(url, headers={"Range": "bytes=-1"})
    if resp.status_code in (200, 206) and resp.content:
        return resp.content[-1:]

    # Fallback: query Content-Length and request exact last byte offset
    head = session.head(url)
    total_size = int(head.headers.get("content-length", 0))
    if total_size > 0:
        resp = session.get(url, headers={"Range": f"bytes={total_size - 1}-{total_size - 1}"})
        if resp.status_code in (200, 206) and resp.content:
            return resp.content[-1:]
    return b""


def download_file(url: str, output_path: Optional[str] = None, impersonate: str = "chrome124"):
    """Downloads the file from the direct CDN URL with progress display."""
    session = requests.Session(impersonate=impersonate)
    print(f"[*] Starting download from CDN...")
    r = session.get(url, stream=True)
    r.raise_for_status()
    if not output_path:
        cd = r.headers.get("content-disposition", "")
        cd_m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
        if cd_m:
            output_path = cd_m.group(1).strip()
        else:
            output_path = "downloaded_file"

    total_size = int(r.headers.get("content-length", 0))
    downloaded = 0
    first_byte_logged = False
    print(f"[*] Saving to: {output_path}")
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                if not first_byte_logged:
                    first_b = chunk[:1]
                    val = first_b[0]
                    char_repr = repr(chr(val)) if 32 <= val <= 126 else repr(first_b)
                    print(f"[*] First 1 byte received: {first_b} (Hex: 0x{val:02x}, Dec: {val}, Repr: {char_repr})")
                    first_byte_logged = True
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    print(f"\r    Progress: {downloaded}/{total_size} bytes ({percent:.1f}%)", end="", flush=True)
                else:
                    print(f"\r    Downloaded: {downloaded} bytes", end="", flush=True)
    print("\n[+] Download complete!")


def process_batch(file_path: str, args):
    """Processes a list of links/IDs from a file."""
    if not os.path.exists(file_path):
        print(f"[!] File not found: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    if not lines:
        print(f"[!] No valid links found in {file_path}")
        return

    print("=" * 55)
    print(f"  BATCH PROCESSING: {len(lines)} LINK(S)")
    print("=" * 55)
    succeeded = 0
    failed = 0

    report_rows = []
    for idx, line in enumerate(lines, 1):
        print(f"\n[{idx}/{len(lines)}] Target: {line}")
        try:
            file_id = parse_file_id(line)
            data = resolve_buzzheavier_link(file_id, impersonate=args.impersonate)
            file_name = data.get('file_name') or line
            file_size = data.get('file_size') or "N/A"
            print(f"    File     : {file_name} ({file_size})")

            byte_info = "-"
            if args.last_byte:
                b = download_last_byte(data["direct_cdn_url"], impersonate=args.impersonate)
                if b:
                    val = b[0]
                    char_repr = repr(chr(val)) if 32 <= val <= 126 else repr(b)
                    byte_info = f"0x{val:02x} ({char_repr})"
                    print(f"    Last Byte: {b} (Hex: 0x{val:02x}, Repr: {char_repr}) -> SUCCESS")
                else:
                    raise RuntimeError("Failed to fetch last byte from CDN")

            if args.first_byte:
                b = download_first_byte(data["direct_cdn_url"], impersonate=args.impersonate)
                if b:
                    val = b[0]
                    char_repr = repr(chr(val)) if 32 <= val <= 126 else repr(b)
                    byte_info = f"0x{val:02x} ({char_repr})"
                    print(f"    First Byte: {b} (Hex: 0x{val:02x}, Repr: {char_repr}) -> SUCCESS")

            if args.download:
                download_file(data["direct_cdn_url"], output_path=args.output, impersonate=args.impersonate)

            succeeded += 1
            report_rows.append({
                "idx": idx, "name": file_name, "size": file_size, "byte": byte_info, "status": "✅ OK"
            })
        except Exception as e:
            failed += 1
            print(f"    [FAIL] Error: {e}")
            report_rows.append({
                "idx": idx, "name": line, "size": "N/A", "byte": "-", "status": f"❌ {e}"
            })

    print("\n" + "=" * 55)
    print(f"  BATCH SUMMARY: {succeeded}/{len(lines)} succeeded, {failed} failed.")
    print("=" * 55)

    # Write summary to GitHub Actions if running in CI
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as sf:
                sf.write("### 🐝 BuzzHeavier Daily Keep-Alive Report\n\n")
                sf.write("| # | File Name | Size | Last Byte | Status |\n")
                sf.write("|---|-----------|------|-----------|--------|\n")
                for r in report_rows:
                    sf.write(f"| {r['idx']} | {r['name']} | {r['size']} | `{r['byte']}` | {r['status']} |\n")
                sf.write(f"\n**Total:** {succeeded}/{len(lines)} succeeded, {failed} failed.\n")
        except Exception:
            pass

    if failed > 0:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="BuzzHeavier Download Link Resolver using curl-cffi (fast & lightweight)."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="BuzzHeavier file URL, file ID, or links file (e.g. yebbjo1kfx3b or links.txt)"
    )
    parser.add_argument(
        "-f", "--file",
        help="Path to text file containing links or IDs (one per line)"
    )
    parser.add_argument(
        "-b", "--first-byte",
        action="store_true",
        help="Download and print the first 1 byte from the file"
    )
    parser.add_argument(
        "-l", "--last-byte",
        action="store_true",
        help="Download and print the last 1 byte from the file"
    )
    parser.add_argument(
        "-d", "--download",
        action="store_true",
        help="Directly download the file after resolving the link"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output filename when downloading"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )
    parser.add_argument(
        "--impersonate",
        default="chrome124",
        help="Browser TLS fingerprint to impersonate (default: chrome124)"
    )

    args = parser.parse_args()

    # Check if batch mode via --file or positional file path
    batch_file = args.file
    if not batch_file and args.input and os.path.isfile(args.input):
        batch_file = args.input

    if batch_file:
        process_batch(batch_file, args)
        return

    target_input = args.input
    if not target_input:
        target_input = input("Enter BuzzHeavier file link or file ID: ").strip()

    if not target_input:
        print("[!] Error: No input provided.")
        sys.exit(1)

    try:
        file_id = parse_file_id(target_input)
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)

    if not args.json:
        print(f"[*] Target File ID: {file_id}")
        print(f"[*] Resolving via curl-cffi (impersonating {args.impersonate})...")

    try:
        data = resolve_buzzheavier_link(file_id, impersonate=args.impersonate)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"[!] Failed to resolve link: {e}")
        sys.exit(1)

    # If first-byte requested, fetch it
    first_byte_data = None
    if args.first_byte and data.get("direct_cdn_url"):
        b = download_first_byte(data["direct_cdn_url"], impersonate=args.impersonate)
        if b:
            val = b[0]
            char_repr = repr(chr(val)) if 32 <= val <= 126 else repr(b)
            first_byte_data = {
                "raw": str(b),
                "hex": f"0x{val:02x}",
                "decimal": val,
                "binary": bin(val),
                "repr": char_repr
            }
            data["first_byte"] = first_byte_data

    # If last-byte requested, fetch it
    last_byte_data = None
    if args.last_byte and data.get("direct_cdn_url"):
        b = download_last_byte(data["direct_cdn_url"], impersonate=args.impersonate)
        if b:
            val = b[0]
            char_repr = repr(chr(val)) if 32 <= val <= 126 else repr(b)
            last_byte_data = {
                "raw": str(b),
                "hex": f"0x{val:02x}",
                "decimal": val,
                "binary": bin(val),
                "repr": char_repr
            }
            data["last_byte"] = last_byte_data

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("\n" + "=" * 55)
        print("          BUZZHEAVIER DOWNLOAD DETAILS           ")
        print("=" * 55)
        if data["file_name"]:
            print(f"  File Name   : {data['file_name']}")
        if data["file_size"]:
            print(f"  File Size   : {data['file_size']}")
        print(f"  File Page   : {data['page_url']}")
        print(f"  Token (t=)  : {data['token']}")
        print("-" * 55)
        print("  Tokenized Link (t=):")
        print(f"  {data['token_link']}")
        print("-" * 55)
        if data["direct_cdn_url"]:
            print("  Direct CDN Stream URL (Ready for download):")
            print(f"  {data['direct_cdn_url']}")
        print("=" * 55)

    if args.first_byte and first_byte_data:
        print("\n" + "=" * 55)
        print("            FIRST 1 BYTE DOWNLOADED              ")
        print("=" * 55)
        print(f"  Raw Byte : {first_byte_data['raw']}")
        print(f"  Hex      : {first_byte_data['hex']}")
        print(f"  Decimal  : {first_byte_data['decimal']}")
        print(f"  Binary   : {first_byte_data['binary']}")
        print(f"  Repr     : {first_byte_data['repr']}")
        print("=" * 55)

    if args.last_byte and last_byte_data:
        print("\n" + "=" * 55)
        print("             LAST 1 BYTE DOWNLOADED              ")
        print("=" * 55)
        print(f"  Raw Byte : {last_byte_data['raw']}")
        print(f"  Hex      : {last_byte_data['hex']}")
        print(f"  Decimal  : {last_byte_data['decimal']}")
        print(f"  Binary   : {last_byte_data['binary']}")
        print(f"  Repr     : {last_byte_data['repr']}")
        print("=" * 55)

    if args.download and data["direct_cdn_url"]:
        download_file(data["direct_cdn_url"], output_path=args.output, impersonate=args.impersonate)


if __name__ == "__main__":
    main()
