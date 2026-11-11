"""Handler for fuckingfast.co part pages (Playwright).

Every part is resolved in its own brand-new browser, closed right after the link is
captured. If a headless attempt fails, that one part is retried with a visible window
(so a Cloudflare box can be ticked by hand); the next part starts headless again.

Flow:
  1. Open the part page and wait for the DOWNLOAD button.
  2. Click it. Wait a few seconds for a https://dl.fuckingfast.co/dl/... link.
  3. If none appeared (ad popup, overlay, button swapped), click a second time.
  4. The link is taken from whichever appears first: an intercepted browser request
     (aborted, so the file is never downloaded by the browser) or a link in the page.
The returned link is reusable, so the real download is done by downloader.py.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from downloader import ResolvedLink

from .base import ProviderHandler, ResolveError
from .browser import BrowserSession, get_settings, part_session, short_error

DIRECT_RE = re.compile(r"https?://dl\.fuckingfast\.co/dl/[A-Za-z0-9_\-%.~]+")
DIRECT_REQUEST_RE = re.compile(r"^https?://dl\.fuckingfast\.co/dl/")
COOKIE_DOMAIN = "fuckingfast.co"
FIRST_CLICK_WAIT = 6.0   # seconds to wait for a link before the second click
POLL_MS = 250


class FuckingFastHandler(ProviderHandler):
    domains = ("fuckingfast.co",)

    def resolve(self, part_url: str) -> ResolvedLink:
        cfg = get_settings()
        try:
            return self._resolve_in_fresh_browser(part_url, cfg.headless, cfg.timeout)
        except ResolveError as first:
            if not (cfg.headless and cfg.fallback_to_headed):
                raise
            try:
                return self._resolve_in_fresh_browser(part_url, False, cfg.headed_timeout)
            except ResolveError as second:
                raise ResolveError(f"{first} | headed retry: {second}") from second

    # -- one attempt, in its own browser ---------------------------------
    def _resolve_in_fresh_browser(self, part_url: str, headless: bool, timeout: float) -> ResolvedLink:
        page_url, _, fragment = part_url.partition("#")
        with part_session(headless, timeout) as session:
            page = None
            try:
                page = session.context().new_page()
                with session.capture(DIRECT_REQUEST_RE) as hits:
                    direct = self._click_for_url(session, page, page_url, hits)
                cookies = session.cookies_for(COOKIE_DOMAIN)
                user_agent = session.user_agent or ""
            except ResolveError:
                raise
            except Exception as e:  # Playwright timeouts, closed page, ...
                raise ResolveError(f"browser error: {short_error(e)}") from e
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
        # browser is closed here, before the real download starts

        hint = unquote(fragment).strip() or None  # page fragment is often the filename
        return ResolvedLink(
            url=direct,
            filename=hint,
            headers={"Referer": page_url, "User-Agent": user_agent},
            cookies=cookies,
        )

    def _click_for_url(self, session: BrowserSession, page, page_url: str, hits: list) -> str:
        timeout_ms = int(session.timeout * 1000)
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as e:
            raise ResolveError(f"could not load part page: {short_error(e)}") from e

        # click 1
        self._click(self._find_button(page, timeout_ms))
        url = self._wait_for_url(session, page, hits, FIRST_CLICK_WAIT)
        if url:
            return url

        # click 2: an ad may have navigated the tab away, so get back to the page first
        if urlparse(page.url).hostname != urlparse(page_url).hostname:
            try:
                page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass
        button = self._find_button(page, 3000, required=False)
        if button is not None:
            self._click(button)
        url = self._wait_for_url(session, page, hits, session.timeout)
        if url:
            return url
        raise ResolveError("no download link appeared after two clicks")

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _find_button(page, timeout_ms: int, required: bool = True):
        candidates = (
            (page.locator("a[hx-post]").first, timeout_ms),
            (page.get_by_role("link", name=re.compile("download", re.I)).first, 2000),
            (page.get_by_role("button", name=re.compile("download", re.I)).first, 2000),
        )
        for loc, wait in candidates:
            try:
                loc.wait_for(state="visible", timeout=wait)
                return loc
            except Exception:
                continue
        if required:
            raise ResolveError("download button not found on the page")
        return None

    @staticmethod
    def _click(loc) -> None:
        try:
            loc.click(timeout=5000)
        except Exception:
            try:  # an overlay may be in the way: fire the click event on the element itself
                loc.dispatch_event("click")
            except Exception:
                pass

    @staticmethod
    def _wait_for_url(session: BrowserSession, page, hits: list, seconds: float) -> str | None:
        waited = 0.0
        while waited < seconds:
            if hits:
                return hits[0]
            session.close_extra_pages(page)
            try:
                m = DIRECT_RE.search(page.content())
                if m:
                    return m.group(0)
            except Exception:
                pass  # page is mid-navigation
            page.wait_for_timeout(POLL_MS)  # also lets route handlers run
            waited += POLL_MS / 1000
        return hits[0] if hits else None