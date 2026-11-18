import httpx
import pytest

from carbase_mcp import client as client_mod
from carbase_mcp.cache import DiskCache
from carbase_mcp.client import BASE_URL, CarbaseClient, CarbaseError


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(client_mod, "MIN_INTERVAL", 0)


def make(handler, cache=None):
    http = httpx.AsyncClient(base_url=BASE_URL, follow_redirects=True, transport=httpx.MockTransport(handler))
    return CarbaseClient(http, cache)


def consent_handler(calls):
    def handler(request):
        calls.append(str(request.url))
        if request.url.host == "www.autoweek.nl" and "authId" not in request.headers.get("cookie", ""):
            return httpx.Response(
                302,
                headers={
                    "location": "https://myprivacy.dpgmedia.nl/consent",
                    "set-cookie": "authId=abc; Domain=.autoweek.nl; Path=/",
                },
            )
        if request.url.host == "myprivacy.dpgmedia.nl":
            return httpx.Response(200, text="consent page")
        return httpx.Response(
            200, text="carbase", headers={"set-cookie": "ak_bmsc=bot; Domain=.autoweek.nl; Path=/"}
        )

    return handler


async def test_consent_redirect_then_retry_and_cache(tmp_path):
    calls = []
    c = make(consent_handler(calls), DiskCache(tmp_path))
    assert await c.get("/carbase/", {"format": "json"}) == "carbase"
    assert await c.get("/carbase/", {"format": "json"}) == "carbase"  # cached
    assert len(calls) == 3  # carbase -> consent, then carbase with cookie


async def test_consent_cookie_is_reused_by_next_process(tmp_path):
    calls = []
    await make(consent_handler(calls), DiskCache(tmp_path)).get("/a")
    assert (tmp_path / "cookies.json").stat().st_mode & 0o777 == 0o600
    assert [c["name"] for c in DiskCache(tmp_path).load_cookies()] == ["authId"]  # not ak_bmsc
    calls.clear()
    await make(consent_handler(calls), DiskCache(tmp_path)).get("/b")  # new client, same cache dir
    assert calls == ["https://www.autoweek.nl/b"]  # no consent detour


async def test_foreign_redirect_is_refused():
    def handler(request):
        if request.url.host == "www.autoweek.nl":
            return httpx.Response(302, headers={"location": "https://evil.example/"})
        return httpx.Response(200, text="x")

    with pytest.raises(CarbaseError, match=r"Blocked request to https://evil\.example"):
        await make(handler).get("/auto/1/x/")


async def test_redirect_hops_are_checked_before_the_request():  # S-01
    requested = []

    def handler(request):
        requested.append(request.url.host)
        if request.url.host == "www.autoweek.nl":
            # internal host halfway a redirect chain that would end on autoweek again
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        return httpx.Response(302, headers={"location": "https://www.autoweek.nl/ok"})

    with pytest.raises(CarbaseError, match="Blocked"):
        await make(handler).get("/carbase/")
    assert requested == ["www.autoweek.nl"]


async def test_429_pauses_requests_but_cache_still_serves(tmp_path, monkeypatch):  # 4
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/cached":
            return httpx.Response(200, text="ok")
        return httpx.Response(429, headers={"retry-after": "120"})

    c = make(handler, DiskCache(tmp_path))
    await c.get("/cached")
    with pytest.raises(CarbaseError, match="pausing 120 s"):
        await c.get("/x")
    with pytest.raises(CarbaseError, match="paused for another"):
        await c.get("/y")
    assert await c.get("/cached") == "ok"
    assert calls == ["/cached", "/x"]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("30", 30),
        ("0", 1),
        ("999999", 3600),
        ("onzin", 300),
        (None, 300),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 1),
    ],
)
def test_retry_after(header, expected):
    assert client_mod._retry_after(header) == expected


async def test_expired_consent_cookie_is_not_reused(tmp_path):
    DiskCache(tmp_path).save_cookies(
        [{"name": "authId", "value": "old", "domain": ".autoweek.nl", "path": "/", "expires": 1}]
    )
    calls = []
    await make(consent_handler(calls), DiskCache(tmp_path)).get("/a")
    assert len(calls) == 3  # consent detour again
