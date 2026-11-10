"""Handler interface and shared errors for provider handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod

# ResolvedLink already exists in downloader.py (url, filename, headers, cookies).
from downloader import ResolvedLink


class ResolveError(Exception):
    """A part link could not be turned into a direct file URL."""


class NoHandlerError(ResolveError):
    """No registered handler for this domain."""


class ProviderHandler(ABC):
    #: domains this handler serves, e.g. ("fuckingfast.co",)
    domains: tuple[str, ...] = ()

    @abstractmethod
    def resolve(self, part_url: str) -> ResolvedLink:
        """Return a direct download link for a part page URL.

        Must raise ResolveError (never crash) on any failure.
        """