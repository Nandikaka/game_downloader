"""Streaming downloader: server filenames, resume, retry, skip-if-complete."""
import errno
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from utils import sanitize

CHUNK = 1024 * 1024
TIMEOUT = (15, 60)  # connect, read
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class ResolvedLink:
    """What a provider handler hands to the downloader."""
    url: str
    filename: str | None = None            # optional hint; the server's name wins
    headers: dict = field(default_factory=dict)
    cookies: dict = field(default_factory=dict)


@dataclass
class DownloadResult:
    name: str
    status: str                             # "ok" | "skipped" | "failed"
    path: Path | None = None
    bytes_written: int = 0
    error: str = ""


class ProgressSink:
    """No-op progress reporter. Subclass to display progress."""
    def file_start(self, name: str, total: int | None, offset: int) -> None: ...
    def advance(self, n: int) -> None: ...
    def status(self, msg: str) -> None: ...


class DownloadError(Exception):
    def __init__(self, msg: str, retryable: bool = False):
        super().__init__(msg)
        self.retryable = retryable


@dataclass
class _Probe:
    total: int | None
    server_name: str | None
    content_type: str


# ---------- helpers ----------

def _make_session(link: ResolvedLink) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.headers.update(link.headers)
    s.cookies.update(link.cookies)
    return s


def _check_status(r: requests.Response) -> None:
    if r.status_code in (200, 206):
        return
    raise DownloadError(f"HTTP {r.status_code}", retryable=r.status_code in RETRYABLE_STATUS)


def _total_from(r: requests.Response) -> int | None:
    if r.status_code == 206:
        m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range", ""))
        return int(m.group(1)) if m else None
    cl = r.headers.get("Content-Length")
    return int(cl) if cl and cl.isdigit() else None


def _name_from_disposition(cd: str) -> str | None:
    m = re.search(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", cd, re.I)
    if m:
        try:
            return unquote(m.group(2).strip(), encoding=m.group(1) or "utf-8")
        except LookupError:
            return unquote(m.group(2).strip())
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I) or re.search(r"filename\s*=\s*([^;]+)", cd, re.I)
    return m.group(1).strip() if m else None


def _choose_name(server_name: str | None, hint: str | None, fallback: str, url: str) -> str:
    """Server's name first, then the handler hint, the page's part name, the URL's last segment."""
    url_name = unquote(Path(urlparse(url).path).name)
    for cand in (server_name, hint, fallback, url_name):
        if cand and sanitize(cand, 200) != "download":
            return sanitize(cand, 200)
    return "download"


def _probe(session: requests.Session, url: str) -> _Probe:
    """Ask for the first byte only, to learn the filename and total size."""
    try:
        r = session.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DownloadError(f"Connection problem ({type(e).__name__})", retryable=True)
    try:
        _check_status(r)
        name = _name_from_disposition(r.headers.get("Content-Disposition", ""))
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype.lower() and not (name or "").lower().endswith((".html", ".htm")):
            raise DownloadError("Server returned a web page instead of a file "
                                "(the link may have expired or need extra steps)")
        return _Probe(_total_from(r), name, ctype)
    finally:
        r.close()


def _with_retries(fn, retries: int, backoff: float, sink: ProgressSink):
    attempt = 0
    while True:
        try:
            return fn()
        except DownloadError as e:
            if not e.retryable or attempt >= retries:
                raise
            attempt += 1
            wait = backoff * 2 ** (attempt - 1)
            sink.status(f"{e}. Retry {attempt}/{retries} in {wait:g}s")
            time.sleep(wait)


def _download_once(session, url: str, part: Path, total: int | None, sink: ProgressSink, name: str) -> int:
    offset = part.stat().st_size if part.exists() else 0
    if total is not None and offset > total:
        part.unlink()
        offset = 0
    if total is not None and total > 0 and offset == total:
        return offset  # .part is already complete

    headers = {"Range": f"bytes={offset}-"} if offset else {}
    try:
        r = session.get(url, headers=headers, stream=True, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DownloadError(f"Connection problem ({type(e).__name__})", retryable=True)

    try:
        if r.status_code == 416:
            part.unlink(missing_ok=True)
            raise DownloadError("Resume rejected by server, restarting", retryable=True)
        _check_status(r)

        if offset and r.status_code == 206:
            mode = "ab"
        else:
            mode, offset = "wb", 0  # fresh start, or server ignored Range

        expected = total if total is not None else _total_from(r)
        if expected is None and r.headers.get("Content-Length", "").isdigit():
            expected = offset + int(r.headers["Content-Length"])
        sink.file_start(name, expected, offset)

        written = offset
        with open(part, mode) as f:
            for chunk in r.iter_content(CHUNK):
                if chunk:
                    f.write(chunk)
                    written += len(chunk)
                    sink.advance(len(chunk))
    except requests.RequestException as e:
        raise DownloadError(f"Connection interrupted ({type(e).__name__})", retryable=True)
    finally:
        r.close()

    if expected is not None and written != expected:
        raise DownloadError(f"Incomplete download ({written} of {expected} bytes)", retryable=True)
    return written


# ---------- public API ----------

def download_file(link: ResolvedLink, dest_dir, fallback_name: str, retries: int = 3,
                  sink: ProgressSink | None = None, backoff: float = 2.0) -> DownloadResult:
    sink = sink or ProgressSink()
    dest_dir = Path(dest_dir)
    name = sanitize(fallback_name, 200)
    session = _make_session(link)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        probe = _with_retries(lambda: _probe(session, link.url), retries, backoff, sink)
        name = _choose_name(probe.server_name, link.filename, fallback_name, link.url)
        final = dest_dir / name
        part = final.with_name(final.name + ".part")

        # Complete file already there? Skip. Different size? Treat as incomplete: redownload.
        if final.exists() and probe.total is not None and final.stat().st_size == probe.total:
            return DownloadResult(name, "skipped", final, final.stat().st_size)

        written = _with_retries(
            lambda: _download_once(session, link.url, part, probe.total, sink, name),
            retries, backoff, sink)
        os.replace(part, final)
        return DownloadResult(name, "ok", final, written)
    except DownloadError as e:
        return DownloadResult(name, "failed", error=str(e))
    except OSError as e:
        msg = "Disk is full" if e.errno == errno.ENOSPC else f"File system error: {e}"
        return DownloadResult(name, "failed", error=msg)
    finally:
        session.close()