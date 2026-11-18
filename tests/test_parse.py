import json

import pytest

from carbase_mcp.parse import filters, generations, makes, search_state, specs_page

STATE = [
    {
        "result": [
            {
                "name": "Golf",
                "start": 2024,
                "end": 0,
                "door_count": 5,
                "makes": {"slug": "volkswagen", "value": "Volkswagen"},
                "body": {"slug": "hatchback", "value": "Hatchback"},
                "minimum_price_new": 33955,
                "maximum_price_new": 88870,
                "versions": [
                    {
                        "id": 108843,
                        "name": "Volkswagen Golf 1.5 TSI 116pk",
                        "start": 2024,
                        "end": None,
                        "energylabel": {"value": "C"},
                        "fuel_type": {"value": "Benzine"},
                        "transmission": {"value": "Handgeschakeld"},
                        "price_new": 36870,
                        "bijtelling_percentage": 22,
                    }
                ],
            }
        ],
        "pages": 2,
        "total_amount": 1874,
        "filters_new": {
            "fuel_type": {
                "title": "Brandstof",
                "values": [
                    {"slug": "benzine", "name": "Benzine", "amount": 3},
                    {"slug": "lpg", "name": "LPG", "amount": 0},
                ],
            },
            "price": {"title": "Prijs", "values": [15000, 16000]},
            "suppliers": {"title": "Aanbieders", "values": [{"slug": "overig", "name": "Overig"}]},
            "make_models_new": {
                "values": [
                    {
                        "slug": "volkswagen",
                        "name": "Volkswagen",
                        "amount": 9,
                        "models": [{"slug": "golf", "name": "Golf", "amount": 3}],
                    }
                ]
            },
        },
    }
]

SPEC_HTML = """
<h1>Volkswagen Golf 1.5 TSI 116pk</h1><h2>Navigatie</h2>
<h2>2024-heden | 5-deurs, hatchback | handgeschakeld</h2>
<section class="table-description is-island"><header><h3>PRESTATIES</h3></header>
<table><tr><td>topsnelheid
      </td><td>203 km/h</td></tr><tr><td>acceleratie 0-100 km/h</td><td>9,9 s</td></tr></table>
<section class="nested"><p>x</p></section>
<table><tr><td>na geneste sectie</td><td>ja</td></tr></table></section>
<section class="other"><h3>GEEN SPECS</h3><table><tr><td>a</td><td>b</td></tr></table></section>
<section class="table-description"><h3>GEWICHTEN</h3>
<table><tr><td>gewicht leeg</td><td>1.204 kg</td></tr><tr><td></td><td>leeg label</td></tr></table></section>
"""


def test_search_state_accepts_list_and_rejects_other():
    assert search_state(json.dumps(STATE))["total_amount"] == 1874
    with pytest.raises(ValueError):
        search_state('{"foo": 1}')


def test_generations_flattens_values():
    gen = generations(STATE[0])[0]
    assert gen["model"] == "Volkswagen Golf"
    assert gen["years"] == "2024-heden"
    assert gen["versions"][0] == {
        "id": 108843,
        "name": "Volkswagen Golf 1.5 TSI 116pk",
        "years": "2024-heden",
        "fuel": "Benzine",
        "transmission": "Handgeschakeld",
        "energy_label": "C",
        "price": 36870,
        "bijtelling_pct": 22,
    }


def test_filters_skip_internal_and_empty_options():
    out = {f["key"]: f for f in filters(STATE[0], {"fuel_type", "price"})}
    assert set(out) == {"fuel_type", "price"}
    assert out["fuel_type"]["options"] == [{"value": "benzine", "name": "Benzine", "count": 3}]
    assert out["price"] == {
        "key": "price",
        "title": "Prijs",
        "type": "range",
        "steps": [15000, 16000],
    }


def test_makes():
    assert makes(STATE[0])[0]["models"][0]["slug"] == "golf"


def test_specs_page():
    page = specs_page(SPEC_HTML)
    assert page["title"] == "Volkswagen Golf 1.5 TSI 116pk"
    assert page["subtitle"].startswith("2024-heden")
    assert page["specs"] == {
        "PRESTATIES": {
            "topsnelheid": "203 km/h",
            "acceleratie 0-100 km/h": "9,9 s",
            "na geneste sectie": "ja",
        },
        "GEWICHTEN": {"gewicht leeg": "1.204 kg"},
    }
