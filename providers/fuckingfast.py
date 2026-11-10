"""Handler for fuckingfast.co part pages.

Flow (mirrors what the DOWNLOAD button does in a browser):
  1. GET the part page, find the <a hx-post="/f/<id>/go"> button.
  2. POST to that path with the usual htmx headers.
  3. Read the direct URL (https://dl.fuckingfast.co/dl/...) from the response.
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from downloader import ResolvedLink

from .base import ProviderHandler, ResolveError

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 30
DIRECT_RE = re.compile(r"https?://dl\.fuckingfast\.co/dl/[A-Za-z0-9_\-%.~]+")


class FuckingFastHandler(ProviderHandler):
    domains = ("fuckingfast.co",)

    def resolve(self, part_url: str) -> ResolvedLink:
        page_url, _, fragment = part_url.partition("#")
        session = requests.Session()
        session.headers["User-Agent"] = UA

        # 1. page + button
        try:
            page = session.get(page_url, timeout=TIMEOUT)
            page.raise_for_status()
        except requests.RequestException as e:
            raise ResolveError(f"could not load part page: {e}") from e

        go_path = self._find_go_path(page.text, page_url)

        # 2. POST like htmx would
        origin = "{0.scheme}://{0.netloc}".format(urlparse(page_url))
        try:
            resp = session.post(
                urljoin(page_url, go_path),
                headers={
                    "HX-Request": "true",
                    "HX-Current-URL": page_url,
                    "Origin": origin,
                    "Referer": page_url,
                },
                allow_redirects=False,
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise ResolveError(f"download request failed: {e}") from e

        if resp.status_code >= 400:
            raise ResolveError(f"download request returned HTTP {resp.status_code}")

        # 3. extract the direct URL
        direct = self._extract_url(resp, page_url)
        if not direct:
            raise ResolveError(
                "no direct URL in the response "
                f"(status {resp.status_code}, headers {sorted(resp.headers)})"
            )

        # The page URL fragment is often the original filename: use as a hint only.
        hint = unquote(fragment).strip() or None
        return ResolvedLink(
            url=direct,
            filename=hint,
            headers={"Referer": page_url, "User-Agent": UA},
            cookies=session.cookies.get_dict(),
        )

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _find_go_path(html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        btn = soup.find("a", attrs={"hx-post": True})
        if btn:
            return btn["hx-post"]
        # fallback: build /f/<id>/go from the page path
        m = re.search(r"/(?:f/)?([A-Za-z0-9]+)/?$", urlparse(page_url).path)
        if m:
            return f"/f/{m.group(1)}/go"
        raise ResolveError("download button not found on the page")

    @staticmethod
    def _extract_url(resp: requests.Response, base: str) -> str | None:
        # a) redirect-style headers
        for name in ("HX-Redirect", "HX-Location", "Location"):
            val = resp.headers.get(name)
            if not val:
                continue
            if val.lstrip().startswith("{"):          # HX-Location can be JSON
                try:
                    val = json.loads(val).get("path", "")
                except ValueError:
                    pass
            if val:
                return urljoin(base, val)
        # b) JSON body
        try:
            data = resp.json()
            if isinstance(data, dict):
                for key in ("url", "redirect", "link", "download"):
                    if isinstance(data.get(key), str):
                        return urljoin(base, data[key])
        except ValueError:
            pass
        # c) any direct URL in the body
        m = DIRECT_RE.search(resp.text)
        return m.group(0) if m else None