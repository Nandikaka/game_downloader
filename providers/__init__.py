"""Provider registry: maps a domain to a handler."""
from __future__ import annotations

from urllib.parse import urlparse

from downloader import ResolvedLink

from .base import NoHandlerError, ProviderHandler, ResolveError
from .fuckingfast import FuckingFastHandler

_HANDLERS: list[ProviderHandler] = [FuckingFastHandler()]
_BY_DOMAIN: dict[str, ProviderHandler] = {
    d: h for h in _HANDLERS for d in h.domains
}


def get_handler(url: str) -> ProviderHandler | None:
    host = (urlparse(url).hostname or "").lower()
    # exact match, or subdomain of a registered domain
    for domain, handler in _BY_DOMAIN.items():
        if host == domain or host.endswith("." + domain):
            return handler
    return None


def resolve_part(part_url: str) -> ResolvedLink:
    """Resolve one part link. Raises ResolveError / NoHandlerError."""
    handler = get_handler(part_url)
    if handler is None:
        host = urlparse(part_url).hostname or part_url
        raise NoHandlerError(f"no handler for {host}")
    return handler.resolve(part_url)


__all__ = ["resolve_part", "get_handler", "ResolveError", "NoHandlerError"]