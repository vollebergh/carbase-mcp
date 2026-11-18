"""HTTP access to www.autoweek.nl: consent cookie, throttling, back-off, size cap and caching."""

from __future__ import annotations

import asyncio
import logging
import time
from email.utils import parsedate_to_datetime

import httpx

from .cache import DiskCache, ttl_for

BASE_URL = "https://www.autoweek.nl"
HOST = "www.autoweek.nl"
CONSENT_HOST = "myprivacy.dpgmedia.nl"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

MIN_INTERVAL = 0.5  # seconds between upstream requests
TIMEOUT = 20.0
MAX_BYTES = 5_000_000  # largest model listing is ~1 MB
BACKOFF_DEFAULT = 300.0  # pause after 429/503 without a usable Retry-After
BACKOFF_MAX = 3600.0
CONSENT_COOKIES = ("authId", "xAuthId")  # the only cookies kept on disk

# httpx logs every URL at INFO, including the consent redirect that carries the authId cookie.
logging.getLogger("httpx").setLevel(logging.WARNING)


class CarbaseError(RuntimeError):
    """Upstream failure that should be reported to the MCP client."""


class NotFoundError(CarbaseError):
    """Autoweek answered 404."""


async def _only_allowed_hosts(request: httpx.Request) -> None:
    """Checked before every request, including each redirect hop (SSRF guard)."""
    if request.url.scheme != "https" or request.url.host not in (HOST, CONSENT_HOST):
        raise CarbaseError(f"Blocked request to {request.url.scheme}://{request.url.host}")


def _retry_after(value: str | None) -> float:
    """Seconds from a Retry-After header (delta or HTTP date), clamped to [1, BACKOFF_MAX]."""
    if value is None:
        return BACKOFF_DEFAULT
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError):
            seconds = BACKOFF_DEFAULT
    return min(max(seconds, 1.0), BACKOFF_MAX)


class CarbaseClient:
    def __init__(self, http: httpx.AsyncClient | None = None, cache: DiskCache | None = None) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "nl,en;q=0.8"},
        )
        self._http.event_hooks = {"request": [_only_allowed_hosts], "response": []}
        self._cache = cache
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._paused_until = 0.0
        for c in cache.load_cookies() if cache else []:
            try:
                if c["name"] in CONSENT_COOKIES and (c["expires"] is None or c["expires"] > time.time()):
                    self._http.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
            except (KeyError, TypeError):
                continue

    async def get(self, path: str, params: dict[str, str] | None = None) -> str:
        """GET a path on www.autoweek.nl and return the body text (cached on disk)."""
        url = str(httpx.URL(path, params=params or {}))
        async with self._lock:  # one request at a time: throttle, pause and cache stay consistent
            if self._cache and (body := self._cache.get(url, ttl_for(url))) is not None:
                return body
            if (wait := self._paused_until - time.monotonic()) > 0:
                raise CarbaseError(f"Autoweek asked to slow down; paused for another {wait:.0f} s")
            body = await self._fetch(url)
            if body is None:
                # Landed on the DPG consent page, which set the authId cookie: retry, keep the cookie.
                body = await self._fetch(url)
                if body is None:
                    raise CarbaseError("Autoweek consent wall could not be passed")
                self._save_cookies()
            if self._cache:
                self._cache.put(url, body)
        return body

    def _save_cookies(self) -> None:
        if self._cache:
            self._cache.save_cookies(
                [
                    {
                        "name": c.name,
                        "value": c.value,
                        "domain": c.domain,
                        "path": c.path,
                        "expires": c.expires,
                    }
                    for c in self._http.cookies.jar
                    if c.name in CONSENT_COOKIES and c.domain.endswith("autoweek.nl") and c.value
                ]
            )

    async def _fetch(self, path: str) -> str | None:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with self._http.stream("GET", path) as resp:
                self._last = time.monotonic()
                if resp.url.host == CONSENT_HOST:
                    return None
                if resp.status_code in (429, 503):
                    pause = _retry_after(resp.headers.get("retry-after"))
                    self._paused_until = time.monotonic() + pause
                    raise CarbaseError(
                        f"Autoweek asked to slow down (HTTP {resp.status_code}); pausing {pause:.0f} s"
                    )
                if resp.status_code == 404:
                    raise NotFoundError(f"Not found on Autoweek: {path}")
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
