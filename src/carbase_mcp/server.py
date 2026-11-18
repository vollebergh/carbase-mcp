"""FastMCP server exposing the Autoweek Carbase as tools."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import __version__
from .client import CarbaseClient, CarbaseError
from .parse import FILTER_PARAMS, filters, generations, makes, search_state, specs_page

SLUG = re.compile(r"^[a-z0-9]+(?:-+[a-z0-9]+)*-?$")
SORT = {"make_model": "merkmodel", "price": "prijs", "year": "bouwjaar", "power": "vermogen"}
MAX_PAGES = 20

mcp = FastMCP(
    "carbase",
    instructions=(
        "Autoweek Carbase: Dutch catalogue of ~100,000 car versions (uitvoeringen) since the 1990s "
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


async def _state(path: str, params: dict[str, str] | None = None) -> dict:
    raw = await client.get(path, {**(params or {}), "format": "json"})
    try:
        return search_state(raw)
    except (ValueError, KeyError, IndexError) as exc:
        raise CarbaseError(f"Unexpected response from Autoweek for {path}") from exc


async def _specs(version_id: int, sections: list[str] | None) -> dict:
    data = specs_page(await client.get(f"/auto/{version_id}/x/"))
    if not data["specs"]:
        raise CarbaseError(f"No specifications found for version {version_id}")
    if sections:
        wanted = {s.lower() for s in sections}
        data["specs"] = {k: v for k, v in data["specs"].items() if k.lower() in wanted}
    return {"id": version_id, **data}


@mcp.tool()
async def list_brands() -> list[dict]:
    """All brands in Carbase: slug, name and number of versions."""
    return [{"slug": m["slug"], "name": m["name"], "versions": m.get("amount")}
            for m in makes(await _state("/carbase/"))]


@mcp.tool()
async def list_models(brand: Annotated[str, Field(description="Brand slug, e.g. 'volkswagen'")]) -> list[dict]:
    """All models of a brand: slug, name and number of versions."""
    slug = _slug(brand, "brand")
    for m in makes(await _state(_path(slug, None))):
        if m["slug"] == slug:
            return [{"slug": x["slug"], "name": x["name"], "versions": x.get("amount")}
                    for x in m.get("models", [])]
    raise ValueError(f"Unknown brand {brand!r}; call list_brands for valid slugs")


@mcp.tool()
async def list_filters(
    brand: Annotated[str | None, Field(description="Optional brand slug to scope the counts")] = None,
    model: Annotated[str | None, Field(description="Optional model slug (needs brand)")] = None,
) -> list[dict]:
    """Search filters for `search`: key, title and either options (value, name, count) or range steps.

    Examples: fuel_type (benzine, diesel, elektrisch, elektro-benzine, ...), body, transmission,
    wheeldrive, seat_count, entrylevel (instaphoogte), segment, price, year, power_hp,
    elekactieradius (km), min_trunkspace (l), maxweight_trailer_brakes (kg).
    """
    return filters(await _state(_path(brand, model)))


@mcp.tool()
async def search(
    brand: Annotated[str | None, Field(description="Brand slug, e.g. 'toyota'")] = None,
    model: Annotated[str | None, Field(description="Model slug from list_models, e.g. 'rav4' (needs brand)")] = None,
    filters: Annotated[dict[str, Any] | None, Field(description=(
        "Filter key -> option value(s) or range. Options: a value or list of values from "
        "list_filters, e.g. {'fuel_type': ['elektrisch'], 'body': 'suv'}. Ranges: "
        "{'min': x, 'max': y}, e.g. {'price': {'max': 40000}, 'year': {'min': 2022}}."))] = None,
    name_contains: Annotated[str | None, Field(description="Only versions whose name contains all these words, e.g. '1.5 tsi'. Scans all result pages.")] = None,
    sort: Literal["make_model", "price", "year", "power"] = "make_model",
    descending: bool = False,
    page: Annotated[int, Field(ge=1, description="Result page (20 model generations per page); ignored with name_contains")] = 1,
) -> dict:
    """Search Carbase. Returns model generations (model, body, years, price range) each with
    its matching versions (id, name, years, fuel, transmission, energy label, list price,
    bijtelling %). Use a version id with get_specs or compare_versions.
    """
    path = _path(brand, model)
    params = _filter_params(filters or {}) | {
        "sorterenop": SORT[sort], "sortering": "aflopend" if descending else "oplopend"}
    if not name_contains:
        state = await _state(path, params | {"pagina": str(page)})
        return {"total_versions": state.get("total_amount"), "page": page,
                "pages": state.get("pages"), "generations": generations(state)}
    words = name_contains.lower().split()
    found: list[dict] = []
    for p in range(1, MAX_PAGES + 1):
        state = await _state(path, params | {"pagina": str(p)})
        for gen in generations(state):
            gen["versions"] = [v for v in gen["versions"]
                               if all(w in (v["name"] or "").lower() for w in words)]
            if gen["versions"]:
                found.append(gen)
        if p >= (state.get("pages") or 0):
            break
    return {"name_contains": name_contains, "matches": sum(len(g["versions"]) for g in found),
            "generations": found}


@mcp.tool()
async def get_specs(
    version_id: Annotated[int, Field(gt=0, description="Version id from search")],
    sections: Annotated[list[str] | None, Field(description="Optional section names to keep, e.g. ['PRESTATIES', 'INTERIEURMATEN']")] = None,
) -> dict:
    """Full specifications of one version, grouped per section (Dutch labels).

    Sections: BASISKENMERKEN (prices), MOTORISERING, BRANDSTOFMOTOR or ELEKTROMOTOR/ACCU,
    PRESTATIES, VERBRUIK (WLTP), ONDERSTEL, GEWICHTEN, BAGAGE/LAADRUIMTE, EXTERIEURMATEN,
    INTERIEURMATEN (incl. instaphoogte), VEILIGHEID, COMFORT, INTERIEUR, EXTERIEUR,
    SERVICE & GARANTIE, HISTORISCHE NIEUWPRIJZEN.
    """
    return await _specs(version_id, sections)


@mcp.tool()
async def compare_versions(
    version_ids: Annotated[list[int], Field(min_length=2, max_length=5, description="2-5 version ids")],
    sections: Annotated[list[str] | None, Field(description="Optional section names to compare")] = None,
    only_differences: Annotated[bool, Field(description="Drop fields that are equal for all versions")] = True,
) -> dict:
    """Compare 2-5 versions side by side: per section and field, the values in version_ids order."""
    cars = [await _specs(v, sections) for v in version_ids]
    table: dict[str, dict[str, list[str | None]]] = {}
    for i, car in enumerate(cars):
        for section, fields in car["specs"].items():
            for field, value in fields.items():
                table.setdefault(section, {}).setdefault(field, [None] * len(cars))[i] = value
    if only_differences:
        table = {s: d for s, fs in table.items()
                 if (d := {f: v for f, v in fs.items() if len(set(v)) > 1})}
    return {"versions": [{"id": c["id"], "title": c["title"], "subtitle": c["subtitle"]} for c in cars],
            "comparison": table}


def main() -> None:
    mcp._mcp_server.version = __version__
    mcp.run()
