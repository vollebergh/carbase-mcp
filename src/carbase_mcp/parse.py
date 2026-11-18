"""Turn Carbase responses into compact dicts (no I/O)."""

from __future__ import annotations

import json
from collections.abc import Collection
from html.parser import HTMLParser
from typing import Any


def search_state(raw: str) -> dict[str, Any]:
    """The single state object returned by a Carbase URL with ?format=json."""
    data = json.loads(raw)
    state = data[0] if isinstance(data, list) and data else data
    if not isinstance(state, dict) or "result" not in state:
        raise ValueError("unexpected Carbase JSON")
    return state


def makes(state: dict) -> list[dict]:
    """Brand list (with nested models for the selected brand) from filters_new."""
    return state["filters_new"]["make_models_new"]["values"]


def filters(state: dict, keys: Collection[str]) -> list[dict]:
    """Search filters in `keys` with their options and counts for the current selection."""
    out = []
    for key, spec in state["filters_new"].items():
        if key not in keys:
            continue
        values = spec.get("values") or []
        item: dict[str, Any] = {"key": key, "title": spec.get("title")}
        if values and isinstance(values[0], dict):
            item["type"] = "options"
            item["options"] = [
                {"value": str(v["slug"]), "name": v["name"], "count": v.get("amount")}
                for v in values
                if v.get("amount")
            ]
        else:
            item["type"] = "range"
            item["steps"] = values
        out.append(item)
    return out


def _years(start: int | None, end: int | None) -> str | None:
    return f"{start}-{end or 'heden'}" if start else None


def _value(field: Any) -> Any:
    return field.get("value") if isinstance(field, dict) else field


def generations(state: dict) -> list[dict]:
    """Search results: one entry per model generation/body, each with its versions."""
    return [
        {
            "model": f"{_value(r.get('makes'))} {r.get('name')}",
            "body": _value(r.get("body")),
            "doors": r.get("door_count"),
            "years": _years(r.get("start"), r.get("end")),
            "price_from": r.get("minimum_price_new"),
            "price_to": r.get("maximum_price_new"),
            "versions": [
                {
                    "id": v["id"],
                    "name": v.get("name") or "",
                    "years": _years(v.get("start"), v.get("end")),
                    "fuel": _value(v.get("fuel_type")),
                    "transmission": _value(v.get("transmission")),
                    "energy_label": _value(v.get("energylabel")),
                    "price": v.get("price_new"),
                    "bijtelling_pct": v.get("bijtelling_percentage"),
                }
                for v in r.get("versions", [])
            ],
        }
        for r in state["result"]
    ]


class _SpecParser(HTMLParser):
    """Collects h1, the '|' subtitle and every section.table-description of a version page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.subtitle: str | None = None
        self.specs: dict[str, dict[str, str]] = {}
        self._depth = 0  # nesting depth inside a spec section, 0 = outside
        self._tag: str | None = None  # h1/h2/h3/td whose text is being collected
        self._buf: list[str] = []
        self._section: str | None = None
        self._cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._depth:
            self._depth += tag == "section"
        elif tag == "section" and "table-description" in (dict(attrs).get("class") or "").split():
            self._depth, self._section = 1, None
        if tag in ("h1", "h2", "h3", "td"):
            self._tag, self._buf = tag, []
        elif tag == "tr":
            self._cells = []

    def handle_endtag(self, tag: str) -> None:
        if tag == self._tag:
            text = " ".join("".join(self._buf).split())
            self._tag = None
            if tag == "td":
                self._cells.append(text)
            elif tag == "h3" and self._depth:
                self._section = text
            elif tag == "h1" and self.title is None:
                self.title = text
            elif tag == "h2" and self.subtitle is None and "|" in text:
                self.subtitle = text
        elif tag == "tr" and self._depth and self._section and len(self._cells) >= 2:
            if self._cells[0]:
                self.specs.setdefault(self._section, {})[self._cells[0]] = self._cells[1]
        elif tag == "section" and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._tag:
            self._buf.append(data)


def specs_page(html: str) -> dict:
    parser = _SpecParser()
    parser.feed(html)
    parser.close()
    return {"title": parser.title, "subtitle": parser.subtitle, "specs": parser.specs}
