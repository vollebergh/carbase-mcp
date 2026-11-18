"""FastMCP server exposing the Autoweek Carbase as tools."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import __version__, parse
from .client import CarbaseClient, CarbaseError, NotFoundError

# Carbase filter key (as in the JSON "filters_new") -> URL parameter name, taken from
# Autoweek's search-client bundle. Keys not listed here are internal and not exposed.
FILTER_PARAMS = {
    "fuel_type": "brandstof",
    "body": "carrosserie",
    "transmission": "transmissie",
    "wheeldrive": "aandrijving",
    "seat_count": "aantal-zitplaatsen",
    "door_count": "aantal-deuren",
    "energy_rating": "energielabel",
    "segment": "segment",
    "plugin_car": "plugin",
    "cylinder_count": "cilinders",
    "entrylevel": "instaphoogte",
    "bijtelling_percentage": "bijtelling-percentage",
    "year": "bouwjaar",
    "price": "prijs",
    "power_hp": "vermogen",
    "totaltorque": "max-koppel",
    "topspeed": "topsnelheid",
    "acceleration": "acceleratie",
    "consumption_combined": "verbruik",
    "co2emission": "co2emission",
    "elekactieradius": "actieradius",
    "batterycapacity": "accu-capaciteit",
    "electricBatteryQuickchargepower": "snellaadvermogen",
    "min_trunkspace": "bagageruimte",
    "maxweight_trailer_brakes": "aanhangermassa-geremd",
    "mass": "massa",
    "length": "lengte",
    "cylinder_capacity": "cilinderinhoud",
}
SLUG = re.compile(r"^[a-z0-9]+(?:-+[a-z0-9]+)*-?$")
SORT = {"make_model": "merkmodel", "price": "prijs", "year": "bouwjaar", "power": "vermogen"}
MAX_PAGES = 20

mcp = FastMCP(
    "carbase",
    instructions=(
        "Autoweek Carbase: Dutch catalogue of ~100,000 car versions (uitvoeringen) since the 1970s "
        "with Dutch list prices (euro, incl. VAT/BPM) and full specifications with Dutch labels. "
        "Flow: list_brands/list_models -> search (brand, model and/or filters; see list_filters) "
        "-> get_specs(version_id) or compare_versions(ids). Data comes from Autoweek as-is and "
        "can contain gaps or entry errors."
    ),
)
client = CarbaseClient()


def _slug(value: str, what: str) -> str:
    slug = value.strip().lower().replace(" ", "-")
    if not SLUG.match(slug):
        raise ValueError(f"Invalid {what}: {value!r}")
    return slug


def _path(brand: str | None, model: str | None) -> str:
    if model and not brand:
        raise ValueError("model requires brand")
    parts = [_slug(p, "brand/model") for p in (brand, model) if p]
    return "/carbase/" + "".join(f"{p}/" for p in parts)


def _filter_params(selection: dict[str, Any]) -> dict[str, str]:
    params = {}
    for key, value in selection.items():
        if key not in FILTER_PARAMS:
            raise ValueError(f"Unknown filter {key!r}; call list_filters for valid keys")
        if isinstance(value, dict):  # range
            lo, hi = value.get("min"), value.get("max")
            if not all(v is None or isinstance(v, int | float) for v in (lo, hi)):
                raise ValueError(f"Range filter {key!r} needs numeric min/max")
            text = f"{'' if lo is None else lo}--{'' if hi is None else hi}"
        else:
            values = value if isinstance(value, list) else [value]
            text = "--".join(_slug(str(v), f"{key} value") for v in values)
        params[FILTER_PARAMS[key]] = text
    return params


def _entry(item: dict) -> dict:
    return {"slug": item["slug"], "name": item["name"], "versions": item.get("amount")}


def _parse[T](fn: Callable[..., T], *args: Any) -> T:
    """Run a parser; a changed Autoweek format becomes a clear CarbaseError."""
    try:
        return fn(*args)
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
        raise CarbaseError("Unexpected response format from Autoweek; the site may have changed") from exc


async def _state(path: str, params: dict[str, str] | None = None) -> dict:
    try:
        raw = await client.get(path, {**(params or {}), "format": "json"})
    except NotFoundError:
        raise ValueError(f"Unknown brand or model in {path}; use list_brands / list_models") from None
    return _parse(parse.search_state, raw)


async def _specs(version_id: int, sections: list[str] | None) -> dict:
    data = _parse(parse.specs_page, await client.get(f"/auto/{version_id}/x/"))
    if not data["specs"]:
        raise CarbaseError(f"No specifications found for version {version_id}")
    if sections:
        wanted = {s.lower() for s in sections}
        kept = {k: v for k, v in data["specs"].items() if k.lower() in wanted}
        if not kept:
            raise ValueError(f"No such section(s) {sections}; available: {list(data['specs'])}")
        data["specs"] = kept
    return {"id": version_id, **data}


Brand = Annotated[str, Field(description="Brand slug from list_brands, e.g. 'volkswagen'")]
Model = Annotated[str | None, Field(description="Model slug from list_models, e.g. 'golf'")]
Sections = Annotated[list[str] | None, Field(description="Section names to keep, e.g. ['PRESTATIES']")]


@mcp.tool()
async def list_brands() -> list[dict]:
    """All brands in Carbase: slug, name and number of versions."""
    return [_entry(m) for m in _parse(parse.makes, await _state("/carbase/"))]


@mcp.tool()
async def list_models(brand: Brand) -> list[dict]:
    """All models of a brand: slug, name and number of versions."""
    slug = _slug(brand, "brand")
    makes = _parse(parse.makes, await _state(_path(slug, None)))
    return [_entry(x) for m in makes if m["slug"] == slug for x in m.get("models", [])]


@mcp.tool()
async def list_filters(brand: Brand | None = None, model: Model = None) -> list[dict]:
    """Filters for `search`, with options (value, name, count) or range steps.

    Counts reflect the optional brand/model. Useful keys: fuel_type (benzine, diesel,
    elektrisch, elektro-benzine, ...), body, transmission, wheeldrive, seat_count,
    entrylevel (instaphoogte), segment, price, year, power_hp, elekactieradius (km),
    min_trunkspace (l), maxweight_trailer_brakes (kg).
    """
    return _parse(parse.filters, await _state(_path(brand, model)), FILTER_PARAMS)


@mcp.tool()
async def search(
    brand: Brand | None = None,
    model: Model = None,
    filters: dict[str, Any] | None = None,
    name_contains: str | None = None,
    sort: Literal["make_model", "price", "year", "power"] = "make_model",
    descending: bool = False,
    page: Annotated[int, Field(ge=1)] = 1,
) -> dict:
    """Search Carbase by brand, model and/or filters.

    filters: filter key -> option value(s) or a range, keys and values from list_filters.
      e.g. {"fuel_type": ["elektrisch", "elektro-benzine"], "body": "suv",
            "price": {"max": 40000}, "year": {"min": 2022}}
    name_contains: keep only versions whose name contains all these words ("1.5 tsi");
      scans up to 20 result pages instead of one, so combine it with brand/model or filters.
    page: 20 model generations per page.

    Returns model generations (model, body, years, price range), each with its matching
    versions (id, name, years, fuel, transmission, energy label, list price, bijtelling %).
    Use a version id with get_specs or compare_versions.
    """
    path = _path(brand, model)
    params = _filter_params(filters or {}) | {
        "sorterenop": SORT[sort],
        "sortering": "aflopend" if descending else "oplopend",
    }
    if not name_contains:
        state = await _state(path, params | {"pagina": str(page)})
        return {
            "total_versions": state.get("total_amount"),
            "page": page,
            "pages": state.get("pages"),
            "generations": _parse(parse.generations, state),
        }
    words = name_contains.lower().split()
    found: list[dict] = []
    pages = 0
    for p in range(1, MAX_PAGES + 1):
        state = await _state(path, params | {"pagina": str(p)})
        for gen in _parse(parse.generations, state):
            gen["versions"] = [v for v in gen["versions"] if all(w in v["name"].lower() for w in words)]
            if gen["versions"]:
                found.append(gen)
        pages = state.get("pages") or 0
        if p >= pages:
            break
    return {
        "name_contains": name_contains,
        "matches": sum(len(g["versions"]) for g in found),
        "complete": pages <= MAX_PAGES,
        "generations": found,
    }


@mcp.tool()
async def get_specs(version_id: Annotated[int, Field(gt=0)], sections: Sections = None) -> dict:
    """Full specifications of one version (id from search), grouped per section, Dutch labels.

    Sections: BASISKENMERKEN (prices), MOTORISERING, BRANDSTOFMOTOR or ELEKTROMOTOR/ACCU,
    PRESTATIES, VERBRUIK (WLTP), ONDERSTEL, GEWICHTEN, BAGAGE/LAADRUIMTE, EXTERIEURMATEN,
    INTERIEURMATEN (incl. instaphoogte), VEILIGHEID, COMFORT, INTERIEUR, EXTERIEUR,
    SERVICE & GARANTIE, HISTORISCHE NIEUWPRIJZEN.
    """
    return await _specs(version_id, sections)


@mcp.tool()
async def compare_versions(
    version_ids: Annotated[list[int], Field(min_length=2, max_length=5)],
    sections: Sections = None,
    only_differences: bool = True,
) -> dict:
    """Compare 2-5 versions: per section and field, the values in version_ids order.

    only_differences drops fields that are equal for all versions.
    """
    cars = [await _specs(v, sections) for v in version_ids]
    table: dict[str, dict[str, list[str | None]]] = {}
    for i, car in enumerate(cars):
        for section, fields in car["specs"].items():
            for field, value in fields.items():
                table.setdefault(section, {}).setdefault(field, [None] * len(cars))[i] = value
    if only_differences:
        table = {s: d for s, fs in table.items() if (d := {f: v for f, v in fs.items() if len(set(v)) > 1})}
    return {
        "versions": [{"id": c["id"], "title": c["title"], "subtitle": c["subtitle"]} for c in cars],
        "comparison": table,
    }


def main() -> None:
    # FastMCP has no version argument; without this the server reports the SDK version.
    mcp._mcp_server.version = __version__
    mcp.run()
