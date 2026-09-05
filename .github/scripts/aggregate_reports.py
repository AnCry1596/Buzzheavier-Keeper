#!/usr/bin/env python3
"""
BuzzHeavier Aggregator for GitHub Actions Parallel Matrix Runs
Merges results across multiple shard JSON outputs into a unified summary report,
generates dead_links.txt, and formats an elegant GitHub Actions Step Summary.
"""

import os
import sys
import json
import glob
import argparse
from typing import Dict, Any, List

# Ensure UTF-8 output across all platforms
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def aggregate_shards(results_dir: str) -> Dict[str, Any]:
    """Scans and merges all shard JSON report files from the results directory."""
    json_files = sorted(glob.glob(os.path.join(results_dir, "**", "*.json"), recursive=True))
    if not json_files:
        json_files = sorted(glob.glob(os.path.join(results_dir, "*.json")))

    if not json_files:
        print(f"[!] No JSON shard results found in: {results_dir}")
        return {}

    print(f"[*] Found {len(json_files)} shard result file(s) in {results_dir}:")
    for jf in json_files:
        print(f"    - {os.path.basename(jf)}")

    all_items = {}
    failed_items_map = {}
    total_unique_links = 0
    total_shards = len(json_files)

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
                total_unique_links = max(total_unique_links, data.get("total_unique_links", 0))
                total_shards = max(total_shards, data.get("total_shards", len(json_files)))
                for item in data.get("items", []):
                    idx = item.get("idx")
                    all_items[idx] = item
                    if not item.get("success", False):
                        failed_items_map[item.get("link", str(idx))] = item
        except Exception as e:
            print(f"[!] Error parsing {jf}: {e}")

    sorted_items = [all_items[k] for k in sorted(all_items.keys())]
    succeeded = sum(1 for item in sorted_items if item.get("success", False))
    failed = len(sorted_items) - succeeded
    success_rate = (succeeded / len(sorted_items) * 100.0) if sorted_items else 0.0

    return {
        "total_unique_links": total_unique_links or len(sorted_items),
        "total_checked": len(sorted_items),
        "total_shards": total_shards,
        "shard_files_count": len(json_files),
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": round(success_rate, 2),
        "items": sorted_items,
        "failed_items": list(failed_items_map.values()),
    }


def write_step_summary(agg: Dict[str, Any], output_path: str):
    """Writes a polished, clean markdown dashboard to GITHUB_STEP_SUMMARY."""
    succeeded = agg["succeeded"]
    failed = agg["failed"]
    total = agg["total_checked"]
    success_rate = agg["success_rate"]
    shards = agg["total_shards"]

    lines = []
    lines.append("## 🐝 BuzzHeavier Keep-Alive — Consolidated CI Report\n")

    # Metrics summary table
    lines.append("| 📊 Total Monitored Links | ✅ Healthy / Active | ❌ Dead / Failed | 📈 Success Rate | ⚡ Parallel Shards |")
    lines.append("|:---:|:---:|:---:|:---:|:---:|")
    lines.append(f"| **{total}** | **{succeeded}** | **{failed}** | **{success_rate:.1f}%** | **{shards} Runners** |\n")

    # Callout alert
    if failed == 0:
        lines.append("> [!TIP]\n> **All monitored files are healthy!** CDN endpoints verified via HTTP Range (`bytes=-1`) keep-alive with near-zero bandwidth consumption.\n")
    else:
        lines.append(f"> [!WARNING]\n> **{failed} link(s) failed or returned HTTP 404 (File Deleted/Expired).** Download the attached `dead-links-report` artifact to prune them from `links.txt`.\n")

    # Failed links table (prominently displayed)
    failed_items = agg.get("failed_items", [])
    if failed_items:
        lines.append("### ⚠️ Dead / Failed Links Requiring Attention\n")
        lines.append("| # | Link | File ID | Error Reason |")
        lines.append("|---|------|---------|--------------|")
        for item in failed_items:
            idx = item.get("idx", "-")
            link = item.get("link", "-")
            fid = item.get("file_id", "-")
            status = item.get("status", "Failed")
            lines.append(f"| {idx} | [{fid}]({link}) | `{fid}` | {status} |")
        lines.append("")

    # Collapsible healthy links
    success_items = [item for item in agg.get("items", []) if item.get("success", False)]
    if success_items:
        lines.append(f"<details>\n<summary><b>📁 View All Active &amp; Verified Links ({len(success_items)})</b></summary>\n")
        lines.append("| # | File Name | Size | Last Byte | Status |")
        lines.append("|---|-----------|------|-----------|--------|")
        for item in success_items:
            idx = item.get("idx", "-")
            name = item.get("name", "-")
            size = item.get("size", "N/A")
            byte_info = item.get("byte", "-")
            status = item.get("status", "✅ OK")
            lines.append(f"| {idx} | {name} | {size} | `{byte_info}` | {status} |")
        lines.append("\n</details>\n")

    content = "\n".join(lines) + "\n"
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Wrote Step Summary to: {output_path}")


def write_dead_links_file(failed_items: List[Dict[str, Any]], output_path: str):
    """Outputs all failed links to a text file for easy cleanup."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# BuzzHeavier Dead/Failed Links Report\n")
        f.write(f"# Generated: {len(failed_items)} failed/dead link(s)\n")
        f.write("# Copy and use this list to prune inactive items from links.txt\n\n")
        for item in failed_items:
            link = item.get("link", "")
            status = item.get("status", "Unknown error")
            f.write(f"{link}  # {status}\n")
    print(f"[+] Wrote {len(failed_items)} dead link(s) to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="BuzzHeavier Shard Report Aggregator")
    parser.add_argument(
        "results_dir",
        nargs="?",
        default=".",
        help="Directory containing shard JSON results (default: current directory)"
    )
    parser.add_argument(
        "--output-failed",
        default="dead_links.txt",
        help="Path to write consolidated dead/failed links file (default: dead_links.txt)"
    )
    parser.add_argument(
        "--soft-fail",
        action="store_true",
        help="Exit with 0 even if dead links were found"
    )

    args = parser.parse_args()

    agg = aggregate_shards(args.results_dir)
    if not agg:
        print("[!] No results to aggregate.")
        sys.exit(0)

    print("\n" + "=" * 60)
    print("           CONSOLIDATED CI RUN REPORT           ")
    print("=" * 60)
    print(f"  Total Links Checked : {agg['total_checked']}")
    print(f"  Parallel Shards     : {agg['total_shards']}")
    print(f"  Active / Succeeded  : {agg['succeeded']}")
    print(f"  Dead / Failed       : {agg['failed']}")
    print(f"  Success Rate        : {agg['success_rate']:.1f}%")
    print("=" * 60 + "\n")

    # Output dead links file
    failed_items = agg.get("failed_items", [])
    if failed_items:
        write_dead_links_file(failed_items, args.output_failed)

    # Write Step Summary if in GitHub Actions
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        write_step_summary(agg, summary_file)

    if failed_items and not args.soft_fail:
        print(f"[!] {len(failed_items)} links failed. Exiting with status 1.")
        sys.exit(1)
    else:
        print("[+] Keep-alive aggregation completed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
