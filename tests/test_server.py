import json

import pytest

from carbase_mcp import server
from carbase_mcp.client import NotFoundError


@pytest.mark.parametrize("bad", ["../etc", "a/b", "", "x?y=1", "ä"])
def test_slug_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        server._slug(bad, "brand")


def test_path():
    assert server._path(None, None) == "/carbase/"
    assert server._path("Alfa Romeo", "Giulia") == "/carbase/alfa-romeo/giulia/"
    with pytest.raises(ValueError):
        server._path(None, "golf")


def test_filter_params():
    params = server._filter_params(
        {
            "fuel_type": ["elektrisch", "elektro-benzine"],
            "body": "suv",
            "entrylevel": "681-",
            "price": {"max": 40000},
            "year": {"min": 2020, "max": 2024},
        }
    )
    assert params == {
        "brandstof": "elektrisch--elektro-benzine",
        "carrosserie": "suv",
        "instaphoogte": "681-",
        "prijs": "--40000",
        "bouwjaar": "2020--2024",
    }


@pytest.mark.parametrize("bad", [{"nope": "x"}, {"price": {"max": "40k"}}, {"body": "s&x=1"}])
def test_filter_params_rejects(bad):
    with pytest.raises(ValueError):
        server._filter_params(bad)


async def test_compare_only_differences(monkeypatch):
    async def fake_specs(version_id, sections):
        return {
            "id": version_id,
            "title": f"car {version_id}",
            "subtitle": None,
            "specs": {"A": {"same": "1", "diff": str(version_id)}, "B": {"same": "x"}},
        }

    monkeypatch.setattr(server, "_specs", fake_specs)
    out = await server.compare_versions([1, 2])
    assert out["comparison"] == {"A": {"diff": ["1", "2"]}}
    full = await server.compare_versions([1, 2], only_differences=False)
    assert full["comparison"]["B"] == {"same": ["x", "x"]}


@pytest.mark.live
async def test_live_round_trip():
    result = await server.search("toyota", "rav4", filters={"year": {"min": 2019}})
    version = result["generations"][0]["versions"][0]["id"]
    specs = await server.get_specs(version, ["PRESTATIES"])
    assert specs["specs"]["PRESTATIES"]


def _state(pages, versions, makes=None):
    return {
        "result": [{"name": "Golf", "makes": {"value": "VW"}, "versions": versions}],
        "pages": pages,
        "total_amount": len(versions),
        "filters_new": {"make_models_new": {"values": makes or []}},
    }


@pytest.fixture
def fake_get(monkeypatch):
    """Replace the HTTP client: `responses` maps a path prefix to a body or exception."""
    responses, seen = {}, []

    async def get(path, params=None):
        seen.append((path, dict(params or {})))
        page = (params or {}).get("pagina", "1")
        body = responses.get(f"{path}#{page}", responses.get(path))
        if isinstance(body, Exception):
            raise body
        return body if isinstance(body, str) else json.dumps([body])

    monkeypatch.setattr(server.client, "get", get)
    monkeypatch.setattr(server, "_urls", {})
    return responses, seen


async def test_search_builds_url_params(fake_get):
    responses, seen = fake_get
    responses["/carbase/toyota/rav4/"] = _state(1, [{"id": 1, "name": "RAV4 2.5 Hybrid"}])
    out = await server.search(
        "toyota", "rav4", {"fuel_type": "elektro-benzine"}, sort="price", descending=True
    )
    assert out["generations"][0]["versions"][0]["id"] == 1
    assert seen[0][1] == {
        "brandstof": "elektro-benzine",
        "sorterenop": "prijs",
        "sortering": "aflopend",
        "format": "json",
    }


async def test_default_search_shares_cache_key_with_list_models(fake_get):
    responses, seen = fake_get
    responses["/carbase/vw/"] = _state(2, [], [{"slug": "vw", "name": "VW", "models": []}])
    await server.list_models("vw")
    await server.search("vw")
    await server.search("vw", page=2)
    assert [p for _, p in seen] == [{"format": "json"}, {"format": "json"}, {"pagina": "2", "format": "json"}]


async def test_name_contains_scans_pages_and_tolerates_empty_names(fake_get):  # CR-02, CR-03
    responses, seen = fake_get
    responses["/carbase/vw/golf/#1"] = _state(2, [{"id": 1, "name": "Golf 1.5 TSI"}, {"id": 2, "name": None}])
    responses["/carbase/vw/golf/#2"] = _state(2, [{"id": 3, "name": "Golf 1.5 tsi Life"}, {"id": 4}])
    out = await server.search("vw", "golf", name_contains="1.5 TSI")
    assert [v["id"] for g in out["generations"] for v in g["versions"]] == [1, 3]
    assert out["matches"] == 2 and out["complete"] is True
    assert len(seen) == 2


async def test_name_contains_reports_incomplete(fake_get, monkeypatch):  # CR-03
    monkeypatch.setattr(server, "MAX_PAGES", 1)
    fake_get[0]["/carbase/"] = _state(5, [{"id": 1, "name": "x"}])
    assert (await server.search(name_contains="x"))["complete"] is False


async def test_format_change_is_a_clear_error(fake_get):  # CR-01
    fake_get[0]["/carbase/"] = {"result": [], "pages": 1}  # no filters_new
    with pytest.raises(server.CarbaseError, match="format"):
        await server.list_brands()
    fake_get[0]["/carbase/"] = {"result": [{"versions": [{"name": "no id"}]}]}
    with pytest.raises(server.CarbaseError, match="format"):
        await server.search()


async def test_unknown_brand_is_a_helpful_error(fake_get):  # CR-04
    fake_get[0]["/carbase/nope/"] = NotFoundError("404")
    with pytest.raises(ValueError, match="list_brands"):
        await server.list_models("nope")


async def test_list_models(fake_get):
    makes = [{"slug": "vw", "name": "VW", "models": [{"slug": "golf", "name": "Golf", "amount": 3}]}]
    fake_get[0]["/carbase/vw/"] = _state(1, [], makes)
    assert await server.list_models("vw") == [{"slug": "golf", "name": "Golf", "versions": 3}]


async def test_unknown_section_lists_available(fake_get):  # CR-05
    fake_get[0]["/auto/7/x/"] = (
        '<section class="table-description"><h3>PRESTATIES</h3>'
        "<table><tr><td>a</td><td>b</td></tr></table></section>"
    )
    with pytest.raises(ValueError, match="PRESTATIES"):
        await server.get_specs(7, ["Interieur maten"])
    assert (await server.get_specs(7, ["prestaties"]))["specs"] == {"PRESTATIES": {"a": "b"}}


SPEC = '<section class="table-description"><h3>A</h3><table><tr><td>a</td><td>b</td></tr></table></section>'


async def test_get_specs_uses_url_from_search(fake_get):
    responses, seen = fake_get
    responses["/carbase/"] = _state(1, [{"id": 9, "name": "x", "url": "/auto/9/real-slug/"}])
    responses["/auto/9/real-slug/"] = SPEC
    responses["/auto/10/x/"] = SPEC
    await server.search()
    await server.get_specs(9)
    await server.get_specs(10)  # never seen in a search: slug-less fallback
    assert [p for p, _ in seen[1:]] == ["/auto/9/real-slug/", "/auto/10/x/"]


async def test_remembered_urls_are_bounded(fake_get, monkeypatch):
    monkeypatch.setattr(server, "MAX_URLS", 2)
    versions = [{"id": i, "name": "x", "url": f"/auto/{i}/s/"} for i in range(1, 5)]
    fake_get[0]["/carbase/"] = _state(1, versions)
    await server.search()
    assert server._urls == {3: "/auto/3/s/", 4: "/auto/4/s/"}
