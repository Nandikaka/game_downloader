# Download Automation CLI

A Python command line tool (Windows) that automates batch downloading of multi-part files from a web page. It scrapes a page for a configured header, lists the download parts under it, lets you pick which parts to fetch, asks where to save them, and then downloads them sequentially with progress bars, retries and resume.

## How it is meant to work

1. Ask for the page URL (or take it from `--url`).
2. Load the page and find the `<h3>` whose text contains the configured header text (case-insensitive).
3. Read the `<ul>` that follows. Each `<li>` is a **section** (currently one per hoster).
4. Inside each `<li>`, find the `<div>` with the configured class and collect its `<a>` tags. Each link is a **part** (for example `Resource_Name_part001.rar`).
5. Go straight to the section matching the preferred hoster from the config.
6. Show a checkbox list of that section's parts, all pre-ticked.
7. Ask for the save folder, with the config default pre-filled.
8. Resolve each part link to a direct file URL (provider handler, **not built**).
9. Download each file sequentially, with an overall bar and a per-file bar, then offer to retry any failures.

## Project layout

```
downloader/
├── config.toml        # user settings
├── config.py          # loads and validates config.toml
├── scraper.py         # page parsing: h3 -> ul -> li -> div -> a
├── ui.py              # URL prompt, part checkbox, save-folder prompt, folder naming
├── utils.py           # sanitize() for Windows-safe file and folder names
├── downloader.py      # streaming download, resume, retry, skip-if-complete
├── batch.py           # sequential runner: progress bars, delay, retry-at-end
├── main.py            # CLI entry
├── requirements.txt
└── description.md
```

## Setup and usage

```
pip install -r requirements.txt
python main.py                      # prompts for the page URL
python main.py --url https://...    # skips the URL prompt
python main.py --test-url <direct file URL> [more URLs]   # dev: exercise the downloader only
python main.py --config other.toml  # use a different config file
```

Requires Python 3.9+ (`tomli` is installed automatically on versions before 3.11). Dependencies: `requests`, `beautifulsoup4`, `questionary`, `rich`.

## Configuration (`config.toml`)

| Key                                | Meaning                                                                                                                                       |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `[site] header_text`               | Text the `<h3>` must contain (case-insensitive)                                                                                               |
| `[site] section_div_class`         | Class of the `<div>` inside each `<li>` that holds the part links (one class, or several separated by spaces)                                 |
| `[download] default_dir`           | Default save folder, e.g. `C:/Downloads/MyTool`                                                                                               |
| `[download] subfolder_per_section` | If true, saves into a subfolder named after the resource, derived from the part filenames (`Resource_Name_part001.rar` gives `Resource_Name`) |
| `[providers] preferred`            | Section whose name contains this text is used automatically (case-insensitive)                                                                |
| `[behavior] retries`               | Retries per file after the first attempt (default 3)                                                                                          |
| `[behavior] delay_between_files`   | Seconds to wait after each real download (default 1.0)                                                                                        |
| `[behavior] sequential`            | Read from config but not used yet; downloads are always sequential                                                                            |

The page URL is **not** stored in the config. It is entered at run time.

## What has been built

### Scraper (`scraper.py`)

- Fetches the page with `requests` (the target page was confirmed to be static HTML, so no browser automation is needed).
- Finds the header by "contains" match, takes the following `<ul>`, and builds `Section` and `Part` objects. Relative links are converted to absolute URLs.
- Section name is the `<li>`'s own text with the links div removed, cut to 80 characters, with a "Section N" fallback.
- `find_preferred()` picks the first section whose name contains the preferred text.
- Clear errors for a missing header, a missing list, or no matching sections, including a hint that the page may be JS-rendered.

### Interface (`ui.py`, `main.py`)

- URL prompt with validation (must start with `http://` or `https://`).
- Part checkbox list with everything pre-ticked (space toggles one, `a` toggles all).
- Save-folder prompt with the config default pre-filled and editable.
- Folder naming from the chosen parts' filenames, with Windows-illegal characters removed.
- If no section matches the preferred hoster, it lists the sections found and exits.

### Downloader core (`downloader.py`)

- **Streaming:** 1 MB chunks written to disk, so large files never sit in memory.
- **Filenames:** the server's name wins (`Content-Disposition`). Fallbacks, in order: handler-supplied hint, the page's part name, the last segment of the URL.
- **Probe:** a one-byte ranged request first, to learn the filename and total size.
- **Resume:** writes to `<name>.part` and renames when complete. An existing `.part` is resumed with an HTTP `Range` request. If the server ignores Range, it restarts cleanly.
- **Skip:** a file that already exists with the correct size is skipped. If the size differs, it is treated as incomplete and redownloaded.
- **Retries:** connection errors, timeouts and 408/425/429/5xx are retried with waits of 2s, 4s, 8s. Other HTTP errors (403, 404 and so on) fail immediately.
- **Integrity:** a size check against the server's total after each download.
- **Guards:** a response that is an HTML page instead of a file fails with a clear message. Disk-full and other file system errors are reported as failures.
- **Handler interface:** a `ResolvedLink` (url, optional filename, headers, cookies) is the shape a provider handler is expected to return. The downloader does not care which provider produced it.

### Batch runner (`batch.py`)

- Sequential downloads with an **overall progress bar** (parts done out of total) and a **per-file bar** (size, speed, ETA).
- Configurable delay between real downloads.
- Failed parts are skipped, reported as they happen, and listed in the final summary. After each round, it asks whether to retry just the failed parts, repeating until none fail or you decline.
- Ctrl+C stops cleanly and keeps `.part` files for resume.

### Testing done

- The scraper was tested on sample HTML matching the described structure (header matching, section and part extraction, error cases), and was run once by the user against the real page.
- The downloader was tested against a local HTTP server with 9 scenarios: fresh download with server filename, skip complete file, redownload on size mismatch, dropped connection with retry and resume, resume from a stale `.part`, server ignoring Range, 404 without retry, HTML instead of a file, and a batch with the retry prompt.
- **Not yet verified:** the interactive menus and progress bars in a real Windows terminal, and a real download with `--test-url`.

## What still needs to be built

### 1. Provider handler layer (built for fuckingfast.co; add more handlers as needed)

The part links found by the scraper are pages on a hosting site, not direct file URLs, so the normal flow currently stops after the folder prompt and prints a summary.

- Create a `providers/` package with a handler interface, `resolve(part_url) -> ResolvedLink`, and a registry that maps a domain to a handler.
- Handlers should be limited to sources that serve files without anti-bot or ad gating. Unknown domains should be reported as "no handler" and skipped, not crash.
- Wire the registry into `main.py`: for each chosen part, resolve the link, then pass the results to `run_batch()`.

### 2. Folder naming rework

`subfolder_per_section` currently derives a folder from the part filenames, but the final naming has to account for the server-provided filenames, which are only known after the first request. Decide whether the folder name should come from the page, the part names or the server names.

### 3. Polish

- Logging to a file (failures, retries, skipped files).
- More CLI flags, for example `--out` (skip the folder prompt) and `--yes` (accept defaults).
- Handling of duplicate filenames across sections.
- A friendlier message when the config still has placeholder values.
- Remove or implement the unused `sequential` setting.

### 4. Tests and docs

- Move the throwaway download test script into a proper `tests/` folder (pytest) alongside scraper tests.
- A short README with a worked example config.

### 5. Optional, later

- Parallel downloads (2 to 3 at once), off by default.
- Checksum verification if a source publishes hashes.
- Free-disk-space check before starting.
- Playwright-based scraper, only if a target page turns out to be JS-rendered.
- Packaging as a single `.exe` for Windows (for example with PyInstaller).

## Known limitations

- The scraper assumes the structure `h3` then `ul` then `li` then `div.<class>` then `a`. Different pages will need config changes or edits to `scraper.py`.
- Section names come from raw `<li>` text and can be long or noisy.
- The size check is the only integrity check.

## Browser-based link resolution (Playwright)

`providers/fuckingfast.py` opens each part page in a shared headless Chromium (`providers/browser.py`),
clicks DOWNLOAD (a second time if no link appears), and captures the `https://dl.fuckingfast.co/dl/...`
link by intercepting the browser's request, which is aborted so the browser never downloads the file.
The link, the browser's user agent and the site cookies go to `downloader.py` in a `ResolvedLink`.

- Every part gets a brand-new browser (nothing stored on disk), closed as soon as the link is captured, before the real download starts.
- If headless fails for a part, that part is retried once with a visible window (`fallback_to_headed`, `headed_timeout`) so a Cloudflare box can be ticked by hand; the next part starts headless again.
- Setup: `pip install -r requirements.txt` then `playwright install chromium`.
- Check one link without downloading: `python main.py --resolve-only <part page URL>`.
- `[browser]` config: `headless`, `timeout`, `fallback_to_headed`, `headed_timeout`.
