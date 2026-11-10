"""CLI entry. Milestones 1-3: scrape, go straight to the preferred hoster,
pick parts, choose the save folder. (Downloading comes in later milestones.)"""
import argparse
import sys
from pathlib import Path

from config import ConfigError, load_config, DEFAULT_CONFIG_PATH
from scraper import ScrapeError, find_preferred, get_sections
from ui import ask_save_dir, ask_url, choose_parts, resource_folder_name


def main() -> int:
    ap = argparse.ArgumentParser(description="Download automation tool")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    ap.add_argument("--url", help="Page URL (skips the prompt)")
    args = ap.parse_args()

    url = args.url or ask_url()
    if not url:
        print("Cancelled.")
        return 0

    try:
        cfg = load_config(args.config)
        sections = get_sections(url, cfg)
    except (ConfigError, ScrapeError) as e:
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
    print("\n(Downloading is not implemented yet.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())