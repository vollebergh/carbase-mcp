"""HTTP access to www.autoweek.nl: consent cookie, throttling, size cap and a small TTL cache."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict

import httpx

BASE_URL = "https://www.autoweek.nl"
HOST = "www.autoweek.nl"
CONSENT_HOST = "myprivacy.dpgmedia.nl"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

MIN_INTERVAL = 0.5  # seconds between upstream requests
TIMEOUT = 20.0
MAX_BYTES = 5_000_000  # largest model listing is ~1 MB
CACHE_TTL = 3600.0
CACHE_SIZE = 256

# httpx logs every URL at INFO, including the consent redirect that carries the authId cookie.
logging.getLogger("httpx").setLevel(logging.WARNING)


class CarbaseError(RuntimeError):
    """Upstream failure that should be reported to the MCP client."""


class CarbaseClient:
    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "nl,en;q=0.8"},
        )
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

    async def get(self, path: str, params: dict[str, str] | None = None) -> str:
        """GET a path on www.autoweek.nl and return the body text (cached)."""
        url = str(httpx.URL(path, params=params or {}))
        async with self._lock:  # one request at a time: throttle and cache stay consistent
            hit = self._cache.pop(url, None)  # re-inserted below as most recently used
            if hit is None or time.monotonic() - hit[0] >= CACHE_TTL:
                # The first visit lands on the DPG consent page, which sets the authId
                # cookie; the retry then gets the real page.
                body = await self._fetch(url)
                if body is None:
                    body = await self._fetch(url)
                if body is None:
                    raise CarbaseError("Autoweek consent wall could not be passed")
                hit = (time.monotonic(), body)
            self._cache[url] = hit
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return hit[1]

    async def _fetch(self, path: str) -> str | None:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with self._http.stream("GET", path) as resp:
                self._last = time.monotonic()
                host = resp.url.host
                if host == CONSENT_HOST:
                    return None
                if host != HOST:
                    raise CarbaseError(f"Unexpected redirect to {host}")
                if resp.status_code == 404:
                    raise CarbaseError(f"Not found on Autoweek: {path}")
                resp.raise_for_status()
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise CarbaseError("Response too large")
                    chunks.append(chunk)
                return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise CarbaseError(f"Request to Autoweek failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._http.aclose()
