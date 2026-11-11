"""CLI entry: scrape -> preferred hoster -> pick parts -> choose folder -> resolve + download.
Each part link is resolved by its provider handler right before it is downloaded.
Dev option: --test-url downloads direct file URLs to exercise the downloader."""
import argparse
import sys
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

import requests

from batch import BatchItem, run_batch
from config import ConfigError, load_config, DEFAULT_CONFIG_PATH
from downloader import ResolvedLink
from providers import (BrowserSettings, ResolveError, configure_browser, resolve_part,
                       shutdown_browser)
from scraper import ScrapeError, find_preferred, get_sections
from ui import ask_save_dir, ask_url, choose_parts, resource_folder_name


def resolve_only(part_url: str) -> int:
    """Dev: resolve one part page, print the direct link, and test it with requests."""
    try:
        link = resolve_part(part_url)
    except ResolveError as e:
        print(f"Resolve failed: {e}", file=sys.stderr)
        return 1
    finally:
        shutdown_browser()
    print(f"Direct link: {link.url}")
    print(f"Cookies: {sorted(link.cookies) or 'none'}")
    try:
        r = requests.get(link.url, headers={**link.headers, "Range": "bytes=0-0"},
                         cookies=link.cookies, stream=True, timeout=30)
        print(f"requests test: HTTP {r.status_code}")
        for h in ("Content-Type", "Content-Range", "Content-Length", "Content-Disposition"):
            print(f"  {h}: {r.headers.get(h)}")
        r.close()
        return 0 if r.status_code in (200, 206) else 1
    except requests.RequestException as e:
        print(f"requests test failed: {e}", file=sys.stderr)
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Download automation tool")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    ap.add_argument("--url", help="Page URL (skips the prompt)")
    ap.add_argument("--test-url", nargs="+", metavar="FILE_URL",
                    help="Dev: download direct file URL(s), skipping the scraper")
    ap.add_argument("--resolve-only", metavar="PART_URL",
                    help="Dev: resolve one part page URL with the browser and print the direct link")
    args = ap.parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    configure_browser(BrowserSettings(headless=cfg.headless, timeout=cfg.browser_timeout,
                                      fallback_to_headed=cfg.fallback_to_headed,
                                      headed_timeout=cfg.headed_timeout))

    if args.resolve_only:
        return resolve_only(args.resolve_only)

    if args.test_url:
        save_dir = ask_save_dir(cfg.default_dir)
        if save_dir is None:
            print("Cancelled.")
            return 0
        items = [BatchItem(Path(urlparse(u).path).name or "file", ResolvedLink(url=u))
                 for u in args.test_url]
        summary = run_batch(items, save_dir, cfg.retries, cfg.delay)
        return 1 if summary.failed else 0

    url = args.url or ask_url()
    if not url:
        print("Cancelled.")
        return 0

    try:
        sections = get_sections(url, cfg)
    except ScrapeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    section = find_preferred(sections, cfg.preferred_provider)
    if section is None:
        print(f"Error: no section matches preferred provider '{cfg.preferred_provider}'.", file=sys.stderr)
        print("Sections found on the page:", file=sys.stderr)
        for sec in sections:
            print(f"  - {sec.name}", file=sys.stderr)
        return 1

    print(f"Using: {section.name}  ({len(section.parts)} parts)\n")

    chosen = choose_parts(section.parts)
    if chosen is None:
        print("Cancelled.")
        return 0
    if not chosen:
        print("No parts selected. Nothing to do.")
        return 0

    save_dir = ask_save_dir(cfg.default_dir)
    if save_dir is None:
        print("Cancelled.")
        return 0
    if cfg.subfolder_per_section:
        save_dir = save_dir / resource_folder_name([p.name for p in chosen])

    print(f"\n{len(chosen)} part(s) selected. Files will be saved to:\n  {save_dir}")
    for p in chosen:
        print(f"  - {p.name}")
    print()

    items = [BatchItem(p.name, resolve=partial(resolve_part, p.url)) for p in chosen]
    try:
        summary = run_batch(items, save_dir, cfg.retries, cfg.delay)
    finally:
        shutdown_browser()  # safety net: closes a browser left open by Ctrl+C
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())