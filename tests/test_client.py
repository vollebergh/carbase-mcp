import httpx
import pytest

from carbase_mcp import client as client_mod
from carbase_mcp.client import BASE_URL, CarbaseClient, CarbaseError


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(client_mod, "MIN_INTERVAL", 0)


def make(handler):
    http = httpx.AsyncClient(base_url=BASE_URL, follow_redirects=True, transport=httpx.MockTransport(handler))
    return CarbaseClient(http)


async def test_consent_redirect_then_retry_and_cache():
    calls = []

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
        return httpx.Response(200, text="carbase")

    c = make(handler)
    assert await c.get("/carbase/", {"format": "json"}) == "carbase"
    assert await c.get("/carbase/", {"format": "json"}) == "carbase"  # cached
    assert len(calls) == 3  # carbase -> consent, then carbase with cookie


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


async def test_cache_is_bounded_in_size(monkeypatch):  # S-02
    monkeypatch.setattr(client_mod, "CACHE_CHARS", 25)
    c = make(lambda r: httpx.Response(200, text="x" * 10))
    for i in range(5):
        await c.get(f"/p{i}")
    assert list(c._cache) == ["/p3", "/p4"] and c._cached_chars == 20


async def test_size_cap(monkeypatch):
    monkeypatch.setattr(client_mod, "MAX_BYTES", 10)
    with pytest.raises(CarbaseError, match="too large"):
        await make(lambda r: httpx.Response(200, text="x" * 11)).get("/carbase/")


async def test_404_and_network_errors():
    with pytest.raises(CarbaseError, match="Not found"):
        await make(lambda r: httpx.Response(404)).get("/auto/9/x/")

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(CarbaseError, match="failed"):
        await make(boom).get("/carbase/")
