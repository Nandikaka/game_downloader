"""Per-part Playwright sessions for provider handlers.

Every part gets its own brand-new Chromium (process, context, cookies), which is
closed as soon as the link has been captured. Nothing is written to disk.
Playwright is imported lazily so the rest of the tool works without it installed.
"""
from __future__ import annotations

import atexit
import re
from contextlib import contextmanager
from dataclasses import dataclass

from .base import ResolveError


@dataclass
class BrowserSettings:
    headless: bool = True
    timeout: float = 30.0            # seconds: page load, button wait, link wait (headless)
    fallback_to_headed: bool = True  # on failure, retry THAT part once with a visible window
    headed_timeout: float = 120.0    # seconds: more time, since a human may have to tick a box


def full_error(e: Exception, max_lines: int = 12) -> str:
    """Several lines of an exception message, including Playwright's browser log."""
    lines = [ln.rstrip() for ln in str(e).strip().splitlines() if ln.strip()]
    return "\n    ".join(lines[:max_lines])


def short_error(e: Exception) -> str:
    """First line of an exception message (Playwright errors are multi-line)."""
    lines = str(e).strip().splitlines()
    return f"{type(e).__name__}: {lines[0] if lines else ''}".rstrip(": ")


class BrowserSession:
    def __init__(self, headless: bool, timeout: float):
        self.headless = headless
        self.timeout = timeout
        self.user_agent: str | None = None
        self._pw = None
        self._browser = None
        self._ctx = None

    # -- lifecycle -------------------------------------------------------
    def context(self):
        if self._ctx is None:
            self._launch()
        return self._ctx

    def _launch(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ResolveError(
                "Playwright is not installed (pip install playwright, "
                "then: playwright install chromium)"
            ) from e
        try:
            self._pw = sync_playwright().start()
            opts: dict = {}
            ua = self._pw.devices.get("Desktop Chrome", {}).get("user_agent")
            if ua:  # version-matched UA without the "HeadlessChrome" marker
                opts["user_agent"] = ua
                self.user_agent = ua
            self._browser = self._pw.chromium.launch(headless=self.headless)
            self._ctx = self._browser.new_context(
                accept_downloads=False,   # never let Chromium fetch the file itself
                viewport={"width": 1280, "height": 800},
                **opts,
            )
            self._ctx.set_default_timeout(int(self.timeout * 1000))
            if not self.user_agent:
                page = self._ctx.new_page()
                self.user_agent = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
                page.close()
        except Exception as e:
            self.close()
            raise ResolveError(
                "Could not start the browser. Did you run 'playwright install chromium'?\n"
                f"    {full_error(e)}"
            ) from e

    def close(self) -> None:
        """Close everything. Safe to call repeatedly. Also stops Playwright's event loop,
        which would otherwise break questionary's prompts."""
        for target, method in ((self._ctx, "close"), (self._browser, "close"), (self._pw, "stop")):
            if target is not None:
                try:
                    getattr(target, method)()
                except Exception:
                    pass
        self._ctx = self._browser = self._pw = None

    # -- helpers for handlers -------------------------------------------
    @contextmanager
    def capture(self, pattern: "re.Pattern[str]"):
        """Collect (and abort) every browser request whose URL matches `pattern`.

        Works for all pages of the context, including popups. Yields a list of URLs.
        Aborting the request means the browser never downloads the file.
        """
        ctx = self.context()
        hits: list[str] = []

        def handler(route):
            url = route.request.url
            if url not in hits:
                hits.append(url)
            try:
                route.abort()
            except Exception:
                pass

        ctx.route(pattern, handler)
        try:
            yield hits
        finally:
            try:
                ctx.unroute(pattern, handler)
            except Exception:
                pass

    def close_extra_pages(self, keep) -> None:
        """Close ad popups: every tab except `keep`."""
        for p in list(self.context().pages):
            if p is not keep:
                try:
                    p.close()
                except Exception:
                    pass

    def cookies_for(self, domain: str) -> dict:
        try:
            return {c["name"]: c["value"] for c in self.context().cookies()
                    if c["domain"].lstrip(".").endswith(domain)}
        except Exception:
            return {}


# ---- settings + the currently open session (for Ctrl+C cleanup) -------------
_settings = BrowserSettings()
_active: BrowserSession | None = None


def configure(settings: BrowserSettings) -> None:
    global _settings
    _settings = settings


def get_settings() -> BrowserSettings:
    return _settings


@contextmanager
def part_session(headless: bool, timeout: float):
    """A fresh browser for one part; always closed on exit."""
    global _active
    session = BrowserSession(headless, timeout)
    _active = session
    try:
        yield session
    finally:
        session.close()
        if _active is session:
            _active = None


def shutdown() -> None:
    """Close the browser if one is open (Ctrl+C, end of run)."""
    if _active is not None:
        _active.close()


atexit.register(shutdown)