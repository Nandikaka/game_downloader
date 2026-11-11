# GameDownloader

A Python command-line tool for automating batch downloads of multi-part files from web pages.

It scrapes a page for download links, lets you select which parts to download, and downloads them sequentially with progress bars, automatic retries, and download resumption.

## Features

- **Automatic scraping** – Finds download sections and extracts individual file links.
- **Part selection** – Interactive checkbox menu with all parts selected by default.
- **Provider handling** – Resolves supported hosting pages into direct download URLs.
- **Progress tracking** – Overall and per-file progress bars with speed and ETA.
- **Download resumption** – Automatically resumes interrupted downloads.
- **Automatic retries** – Retries temporary network errors and lets you retry failed downloads.
- **Existing file detection** – Skips files that have already been downloaded successfully.
- **Configurable** – Customize scraping, download location, preferred provider, and retry behavior.

## Requirements

- Windows
- Python 3.9 or newer
- pip

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Nandikaka/game_downloader.git
cd game_downloader
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

**PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

**Command Prompt:**

```cmd
.venv\Scripts\activate.bat
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install the Playwright browser

The application uses Chromium to resolve supported hosting links.

```bash
playwright install chromium
```

## Configuration

Before running the application, check `config.toml`.

Available settings:

| Section / Key                    | Description                                            |
| -------------------------------- | ------------------------------------------------------ |
| `site.header_text`               | Text used to identify the download section on the page |
| `site.section_div_class`         | CSS class containing the download links                |
| `download.default_dir`           | Default download destination                           |
| `download.subfolder_per_section` | Whether to create a separate subfolder                 |
| `providers.preferred`            | Preferred hosting provider                             |
| `behavior.retries`               | Number of retries per failed download                  |
| `behavior.delay_between_files`   | Delay between downloads, in seconds                    |
| `browser.headless`               | Run Chromium without a visible window                  |
| `browser.timeout`                | Browser operation timeout                              |
| `browser.fallback_to_headed`     | Allow visible-browser fallback                         |
| `browser.headed_timeout`         | Timeout for visible-browser operations                 |

The page URL is entered when starting the application and is not stored in the configuration.

## Usage

### Start the application

```bash
python main.py
```

You will be prompted for a page URL.

The application will then:

1. Fetch and parse the page.
2. Find the configured download section.
3. Display the available parts.
4. Let you select which parts to download.
5. Ask for the download destination.
6. Resolve supported hosting links.
7. Download the selected files sequentially.

### Start with a URL

Skip the URL prompt by passing the page URL directly:

```bash
python main.py --url "https://example.com/page"
```

### Use a custom configuration

```bash
python main.py --config other.toml
```

### Resolve a link without downloading

Test whether a hosting page can be resolved into a direct download URL:

```bash
python main.py --resolve-only "https://example.com/part-page"
```

### Test direct downloads

Exercise the downloader using direct file URLs:

```bash
python main.py --test-url "https://example.com/file.rar"
```

Multiple URLs can be supplied:

```bash
python main.py --test-url "https://example.com/file1.rar" "https://example.com/file2.rar"
```

## Download behavior

- Files are downloaded in 1 MB chunks.
- Interrupted downloads are saved as `.part` files.
- Existing partial downloads are resumed when supported by the server.
- Completed files are checked against the expected file size.
- Existing files with matching sizes are skipped.
- Temporary network errors are retried automatically.
- Failed downloads are reported and can be retried at the end.
- Pressing `Ctrl+C` stops the process while preserving partial downloads for later resumption.

## Supported providers

Provider support depends on the available link handlers.

Currently implemented:

- **fuckingfast.co** – Uses Playwright and Chromium to resolve download links.

Other hosting services require their own provider handlers.

## Troubleshooting

**Chromium executable not found**

Install the browser:

```bash
playwright install chromium
```

**No matching download section found**

Check `site.header_text` and `site.section_div_class` in `config.toml`. The target page must also match the expected HTML structure.

**No handler available**

The hosting service may not have a supported provider handler.

**Download interrupted**

Run the application again. Existing `.part` files can be resumed when the server supports HTTP Range requests.
