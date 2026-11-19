"""Return types of the tools. FastMCP turns these into each tool's outputSchema.

Fields that do not always apply are always present and ``None`` when not applicable: FastMCP
serialises a missing optional key as ``null``, and MCP clients validate that against the schema.
"""

from typing import TypedDict


class Entry(TypedDict):
    slug: str
    name: str
    versions: int | None  # number of versions in Carbase


class FilterOption(TypedDict):
    value: str
    name: str
    count: int | None


class SearchFilter(TypedDict):
    key: str
    title: str | None
    type: str  # "options" or "range"
    options: list[FilterOption] | None  # for type "options"
    steps: list[float] | None  # for type "range"


class Version(TypedDict):
    id: int
    name: str
    years: str | None
    fuel: str | None
    transmission: str | None
    energy_label: str | None
    price: int | None  # list price in euro
    bijtelling_pct: int | None


class Generation(TypedDict):
    model: str
    body: str | None
    doors: int | None
    years: str | None
    price_from: int | None
    price_to: int | None
    versions: list[Version]


class SearchResult(TypedDict):
    total_versions: int | None
    returned: int
    next_cursor: str | None
    generations: list[Generation]
    hint: str | None  # set when there are more results


class Specs(TypedDict):
    id: int
    title: str | None
    subtitle: str | None
    specs: dict[str, dict[str, str]]


class VersionTitle(TypedDict):
    id: int
    title: str | None
    subtitle: str | None


class Comparison(TypedDict):
    versions: list[VersionTitle]
    comparison: dict[str, dict[str, list[str | None]]]


class FieldRow(TypedDict):
    id: int
    title: str | None
    subtitle: str | None
    values: dict[str, str | None]


class Fields(TypedDict):
    versions: list[FieldRow]
    unknown_fields: dict[str, list[str]] | None  # labels found in none of the versions
