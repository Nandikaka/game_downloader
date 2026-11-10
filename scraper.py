"""Parses the main page: h3 -> ul -> li (section) -> div.<class> -> a (part)."""
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_NAME_LEN = 80


class ScrapeError(Exception):
    pass


@dataclass
class Part:
    name: str
    url: str


@dataclass
class Section:
    name: str
    parts: list[Part] = field(default_factory=list)


def fetch_html(url: str, timeout: int = 30) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ScrapeError(f"Could not load {url}: {e}") from e
    return resp.text


def _find_header(soup: BeautifulSoup, header_text: str):
    needle = header_text.casefold()
    for h3 in soup.find_all("h3"):
        if needle in h3.get_text(" ", strip=True).casefold():
            return h3
    return None


def _section_name(li, div_selector: str, index: int) -> str:
    """Use the li's own text, ignoring the part-links div."""
    clone = BeautifulSoup(str(li), "html.parser")
    for div in clone.select(div_selector):
        div.decompose()
    text = clone.get_text(" ", strip=True)
    if not text:
        return f"Section {index}"
    first_line = text.splitlines()[0].strip()
    return first_line[:MAX_NAME_LEN].rstrip()


def parse_sections(html: str, header_text: str, div_class: str, base_url: str) -> list[Section]:
    soup = BeautifulSoup(html, "html.parser")

    h3 = _find_header(soup, header_text)
    if h3 is None:
        raise ScrapeError(
            f"No <h3> containing '{header_text}' was found. Check header_text in the "
            "config. If it is correct, the page may be JS-rendered and need Playwright."
        )

    ul = h3.find_next_sibling("ul") or h3.find_next("ul")
    if ul is None:
        raise ScrapeError("Found the header, but no <ul> after it.")

    div_selector = "div." + ".".join(div_class.split())
    sections: list[Section] = []

    for i, li in enumerate(ul.find_all("li", recursive=False), start=1):
        div = li.select_one(div_selector)
        if div is None:
            continue
        parts = [
            Part(
                name=a.get_text(" ", strip=True) or f"part_{n}",
                url=urljoin(base_url, a["href"]),
            )
            for n, a in enumerate(div.find_all("a", href=True), start=1)
        ]
        if parts:
            sections.append(Section(name=_section_name(li, div_selector, i), parts=parts))

    if not sections:
        raise ScrapeError(
            f"The list was found, but no <li> had a div.{div_class} with links. "
            "Check section_div_class in the config."
        )
    return sections


def get_sections(url: str, cfg) -> list[Section]:
    html = fetch_html(url)
    return parse_sections(html, cfg.header_text, cfg.section_div_class, url)


def find_preferred(sections: list[Section], preferred: str) -> Section | None:
    """First section whose name contains the preferred provider (case-insensitive)."""
    needle = preferred.casefold()
    for sec in sections:
        if needle in sec.name.casefold():
            return sec
    return None