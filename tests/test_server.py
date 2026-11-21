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
    async def fake_specs(version_id, sections=None):
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
    responses["/carbase/vw/"] = _state(1, [], [{"slug": "vw", "name": "VW", "models": []}])
    await server.list_models("vw")
    await server.search("vw")
    assert [p for _, p in seen] == [{"format": "json"}, {"format": "json"}]


def _v(i, name="x", price=None):
    return {"id": i, "name": name, "price_new": price}


def _ids(out):
    return [v["id"] for g in out["generations"] for v in g["versions"]]


async def test_name_contains_scans_pages_and_tolerates_empty_names(fake_get):  # CR-02
    responses, seen = fake_get
    responses["/carbase/vw/golf/#1"] = _state(2, [_v(1, "Golf 1.5 TSI"), {"id": 2, "name": None}])
    responses["/carbase/vw/golf/#2"] = _state(2, [_v(3, "Golf 1.5 tsi Life"), {"id": 4}])
    out = await server.search("vw", "golf", name_contains="1.5 TSI")
    assert _ids(out) == [1, 3] and out["returned"] == 2 and out["next_cursor"] is None
    assert out["hint"] is None and len(seen) == 2


async def test_truncation_and_cursor_within_a_page(fake_get):  # B-17
    fake_get[0]["/carbase/"] = _state(1, [_v(i) for i in range(1, 6)])
    first = await server.search(max_versions=2)
    assert _ids(first) == [1, 2] and first["next_cursor"] == "1:2" and "cursor='1:2'" in first["hint"]
    second = await server.search(max_versions=2, cursor=first["next_cursor"])
    assert _ids(second) == [3, 4] and second["next_cursor"] == "1:4"
    last = await server.search(max_versions=2, cursor=second["next_cursor"])
    assert _ids(last) == [5] and last["next_cursor"] is None
    assert last["total_versions"] == 5


async def test_cursor_across_page_boundary_reads_no_earlier_pages(fake_get):  # B-17
    responses, seen = fake_get
    responses["/carbase/#1"] = _state(3, [_v(1), _v(2)])
    responses["/carbase/#2"] = _state(3, [_v(3), _v(4)])
    responses["/carbase/#3"] = _state(3, [_v(5)])
    first = await server.search(max_versions=2)
    assert _ids(first) == [1, 2] and first["next_cursor"] == "2:0"  # page 1 exactly used up
    seen.clear()
    rest = await server.search(max_versions=10, cursor="2:0")
    assert _ids(rest) == [3, 4, 5] and rest["next_cursor"] is None
    assert [p.get("pagina") for _, p in seen] == ["2", "3"]


async def test_pages_per_call_are_bounded(fake_get, monkeypatch):  # B-17
    monkeypatch.setattr(server, "MAX_PAGES", 2)
    fake_get[0]["/carbase/"] = _state(9, [])  # every page empty for this query
    out = await server.search(name_contains="nothing")
    assert out["returned"] == 0 and out["next_cursor"] == "3:0" and "hint" in out


async def test_price_sort_orders_versions_inside_generation(fake_get):  # B-17
    versions = [_v(1, price=30000), _v(2), _v(3, price=20000), _v(4, price=25000)]
    fake_get[0]["/carbase/"] = _state(1, versions)
    assert _ids(await server.search(sort="price")) == [3, 4, 1, 2]
    assert _ids(await server.search(sort="price", descending=True)) == [1, 4, 3, 2]
    assert _ids(await server.search()) == [1, 2, 3, 4]  # other sorts keep Carbase's order


@pytest.mark.parametrize("bad", ["abc", "0:1", "1:-1", "1:2:3", "99999:1", "1:x"])
async def test_invalid_cursor(fake_get, bad):
    with pytest.raises(ValueError, match="cursor"):
        await server.search(cursor=bad)


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
    with pytest.raises(ValueError, match=r"\['nope'\].*PRESTATIES"):  # one unknown among valid ones
        await server.get_specs(7, ["prestaties", "nope"])


async def test_compare_sections_may_be_missing_in_some_versions(fake_get):
    fake_get[0]["/auto/1/x/"] = _sections_html({"ELEKTROMOTOR": [("max. vermogen", "150 kW")]})
    fake_get[0]["/auto/2/x/"] = _sections_html({"BRANDSTOFMOTOR": [("max. vermogen", "110 kW")]})
    out = await server.compare_versions([1, 2], ["elektromotor", "brandstofmotor"])
    assert out["comparison"] == {
        "ELEKTROMOTOR": {"max. vermogen": ["150 kW", None]},
        "BRANDSTOFMOTOR": {"max. vermogen": [None, "110 kW"]},
    }
    with pytest.raises(ValueError, match=r"\['accu'\]"):
        await server.compare_versions([1, 2], ["elektromotor", "accu"])


def test_power_is_not_a_sort_order():  # Carbase ignores sorterenop=vermogen
    assert "power" not in server.SORT


async def test_unknown_model_with_empty_200_is_an_error(fake_get):
    responses, _ = fake_get
    makes = [{"slug": "fiat", "name": "Fiat", "models": [{"slug": "500", "name": "500", "amount": 9}]}]
    responses["/carbase/fiat/500e/"] = {
        "result": [],
        "pages": 0,
        "filters_new": {"make_models_new": {"values": makes}},
    }
    responses["/carbase/fiat/"] = _state(1, [_v(1)], makes)
    with pytest.raises(ValueError, match="list_models"):
        await server.search("fiat", "500e")
    with pytest.raises(ValueError, match="list_models"):
        await server.list_filters("fiat", "500e")
    responses["/carbase/fiat/500/"] = {
        "result": [],
        "pages": 0,
        "filters_new": {"make_models_new": {"values": makes}},
    }
    assert (await server.search("fiat", "500", {"fuel_type": "waterstof"}))["generations"] == []


async def test_name_contains_hint_explains_total(fake_get):
    fake_get[0]["/carbase/"] = _state(1, [_v(1, "Golf 1.5 TSI"), _v(2, "Golf 2.0 TDI")])
    out = await server.search(name_contains="tsi")
    assert out["returned"] == 1 and out["next_cursor"] is None and "before name_contains" in out["hint"]


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


def _spec_html(rows):
    cells = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    head = '<h1>car</h1><section class="table-description"><h3>INTERIEURMATEN</h3>'
    return f"{head}<table>{cells}</table></section>"


async def test_get_fields_across_versions(fake_get):  # B-10
    responses, seen = fake_get
    responses["/auto/1/x/"] = _spec_html([("instaphoogte voor", "715 mm"), ("Hoofdruimte  voor", "1.000 mm")])
    responses["/auto/2/x/"] = _spec_html([("hoofdruimte voor", "950 mm")])  # no step-in height
    out = await server.get_fields([1, 2], ["Instaphoogte voor", "hoofdruimte voor"])
    assert [r["values"] for r in out["versions"]] == [
        {"Instaphoogte voor": "715 mm", "hoofdruimte voor": "1.000 mm"},
        {"Instaphoogte voor": None, "hoofdruimte voor": "950 mm"},
    ]
    assert out["unknown_fields"] is None and len(seen) == 2


async def test_get_fields_suggests_labels(fake_get):  # B-10
    fake_get[0]["/auto/1/x/"] = _spec_html([("instaphoogte voor", "715 mm")])
    out = await server.get_fields([1], ["instap hoogte"])
    assert out["unknown_fields"] == {"instap hoogte": ["instaphoogte voor"]}
    assert out["versions"][0]["values"] == {"instap hoogte": None}


def _sections_html(sections):
    body = "".join(
        f'<section class="table-description"><h3>{name}</h3><table>'
        + "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
        + "</table></section>"
        for name, rows in sections.items()
    )
    return f"<h1>car</h1>{body}"


async def test_get_fields_label_in_several_sections(fake_get):
    fake_get[0]["/auto/1/x/"] = _sections_html(
        {
            "BRANDSTOFMOTOR": [("max. vermogen", "607 kW")],
            "ELEKTROMOTOR": [("max. vermogen", "330 kW"), ("bidirectioneel laden: V2L", "nee")],
        }
    )
    out = await server.get_fields(
        [1],
        ["max. vermogen", "elektromotor: Max. vermogen", "bidirectioneel laden: V2L", "accu: max. vermogen"],
    )
    assert out["versions"][0]["values"] == {
        "max. vermogen": "BRANDSTOFMOTOR: 607 kW; ELEKTROMOTOR: 330 kW",
        "elektromotor: Max. vermogen": "330 kW",
        "bidirectioneel laden: V2L": "nee",
        "accu: max. vermogen": None,
    }
    assert out["unknown_fields"] == {"accu: max. vermogen": ["max. vermogen"]}


async def test_get_fields_keeps_going_past_a_bad_id(fake_get):
    fake_get[0]["/auto/1/x/"] = _spec_html([("instaphoogte voor", "715 mm")])
    fake_get[0]["/auto/2/x/"] = "<h1>nothing</h1>"
    out = await server.get_fields([1, 2], ["instaphoogte voor"])
    good, bad = out["versions"]
    assert good["values"] == {"instaphoogte voor": "715 mm"} and good["error"] is None
    assert bad["values"] == {"instaphoogte voor": None} and "version 2" in bad["error"]
    with pytest.raises(server.CarbaseError, match="version 2"):
        await server.get_fields([2], ["instaphoogte voor"])


async def _call(name, args):
    """Through a real MCP client session: server-side and client-side outputSchema validation."""
    from mcp.shared.memory import create_connected_server_and_client_session

    async with create_connected_server_and_client_session(server.mcp._mcp_server) as client:
        result = await client.call_tool(name, args)
    assert not result.isError, result.content[0].text
    return result.structuredContent


async def test_optional_output_fields_may_be_absent(fake_get):  # regression 0.5.1/0.5.2
    responses, _ = fake_get
    responses["/carbase/"] = _state(1, [_v(1)])  # everything fits: no next_cursor, so no hint
    responses["/auto/1/x/"] = _spec_html([("instaphoogte voor", "715 mm")])
    assert (await _call("search", {}))["hint"] is None
    fields = await _call("get_fields", {"version_ids": [1], "fields": ["instaphoogte voor"]})
    assert fields["unknown_fields"] is None
    responses["/carbase/"]["filters_new"] |= {
        "fuel_type": {"title": "Brandstof", "values": [{"slug": "diesel", "name": "Diesel", "amount": 2}]},
        "price": {"title": "Prijs", "values": [15000, 16000]},
    }
    filters = {f["key"]: f for f in (await _call("list_filters", {}))["result"]}
    assert filters["fuel_type"]["steps"] is None and filters["price"]["options"] is None


async def test_every_tool_passes_client_side_output_validation(fake_get):
    responses, _ = fake_get
    makes = [
        {"slug": "vw", "name": "VW", "amount": 3, "models": [{"slug": "golf", "name": "Golf", "amount": 3}]}
    ]
    responses["/carbase/"] = _state(1, [_v(1)], makes)
    responses["/carbase/vw/"] = _state(1, [_v(1)], makes)
    responses["/auto/1/x/"] = _spec_html([("instaphoogte voor", "715 mm")])
    responses["/auto/2/x/"] = _spec_html([("instaphoogte voor", "700 mm")])
    assert (await _call("list_brands", {}))["result"][0]["slug"] == "vw"
    assert (await _call("list_models", {"brand": "vw"}))["result"][0]["slug"] == "golf"
    assert (await _call("get_specs", {"version_id": 1}))["specs"]["INTERIEURMATEN"]
    assert (await _call("compare_versions", {"version_ids": [1, 2]}))["comparison"]
