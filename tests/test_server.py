import pytest

from carbase_mcp import server


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
