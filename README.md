# carbase-mcp

MCP-server die de [Autoweek Carbase](https://www.autoweek.nl/carbase/) doorzoekbaar maakt voor een taalmodel. De Carbase is een Nederlandse catalogus van ± 100.000 auto-uitvoeringen vanaf de jaren zeventig, met nieuwprijzen en volledige specificaties.

> **Onofficieel.** Dit project is niet verbonden aan Autoweek of DPG Media. De data is van DPG Media en volgens hun [voorwaarden](https://www.autoweek.nl/copyright/) alleen bedoeld voor persoonlijk, niet-commercieel gebruik. Gebruik deze server alleen daarvoor, met mate, en respecteer de voorwaarden van Autoweek.

## Wat kan het

| Tool | Doet |
|---|---|
| `list_brands` | alle merken (slug, naam, aantal uitvoeringen) |
| `list_models(brand)` | alle modellen van een merk |
| `list_filters(brand?, model?)` | beschikbare zoekfilters met opties en aantallen, of bereikstappen |
| `search(brand?, model?, filters?, name_contains?, sort, descending, page)` | modelgeneraties met hun uitvoeringen: id, naam, bouwjaren, brandstof, transmissie, energielabel, nieuwprijs, bijtelling |
| `get_specs(version_id, sections?)` | alle specificaties van één uitvoering (± 190 velden in 16 secties: prijzen, motor, prestaties, WLTP-verbruik, gewichten, maten, instaphoogte, bagageruimte, veiligheid, uitrusting, garantie, historische prijzen) |
| `compare_versions(version_ids, sections?, only_differences)` | 2–5 uitvoeringen naast elkaar, standaard alleen de verschillen |

De filters zijn die van de Carbase zelf, onder andere:
- brandstof, carrosserie, transmissie, aandrijving, zitplaatsen
- instaphoogte, segment, energielabel
- prijs, bouwjaar, vermogen, actieradius, bagageruimte, trekgewicht en verbruik

Voorbeeldvragen aan het model:
- *Welke elektrische SUV's onder € 50.000 hebben een hoge instap en een actieradius van meer dan 400 km?*
- *Vergelijk de Mazda CX-5 165 en 194 pk Luxury uit 2019.*
- *Wat is de instaphoogte van de Toyota RAV4 2.5 Hybrid uit 2016?*

## Installeren

Je hebt [uv](https://docs.astral.sh/uv/) nodig. Er zijn geen API-sleutels nodig.

```bash
claude mcp add --scope user carbase -- uvx --from git+https://github.com/vollebergh/carbase-mcp@v0.1.4 carbase-mcp
```

Of in de configuratie van een andere MCP-client:

```json
"carbase": {
  "command": "uvx",
  "args": ["--from", "git+https://github.com/vollebergh/carbase-mcp@v0.1.4", "carbase-mcp"]
}
```

Pin op een tag, zodat er niet ongemerkt nieuwe code binnenkomt.

## Hoe het werkt

- **Zoeken** gebruikt de JSON die de Carbase-pagina's zelf ook laden (`?format=json`). Specificaties komen uit de HTML van `/auto/{id}/`.
- **Consentmuur van DPG Media:** de eerste aanvraag volgt de redirect, die een sessiecookie zet. Er wordt niets aangeklikt of opgeslagen.
- **Zuinig met verzoeken:** hoogstens 2 verzoeken per seconde en een cache in het geheugen (1 uur). Per tool-aanroep gaan er hoogstens 20 pagina's naar Autoweek.
- **Alleen-lezen:** de server doet alleen GET-verzoeken via https naar `www.autoweek.nl`. Dat wordt bij elke redirect gecontroleerd. Hij gebruikt geen sleutels en schrijft niets naar schijf.

## Goed om te weten

- De data komt zoals Autoweek hem levert. Er zitten gaten en soms invoerfouten in; een voorbeeld is een instaphoogte van 43 cm bij een Subaru Outback.
- Je zoekvragen gaan naar Autoweek/DPG Media, net als bij gewoon gebruik van de website.
- De uitvoer is data van derden. Behandel hem in je eigen agents als onbetrouwbare invoer.
- Werkt de server niet meer, dan heeft Autoweek waarschijnlijk de site veranderd.

## Ontwikkelen

```bash
uv sync
uv run pytest                # offline tests
uv run pytest -m live        # één test tegen www.autoweek.nl
uv run ruff check . && uv run ruff format --check .
uv build --out-dir builds/   # wheel en sdist
```

Versies volgen [SemVer](https://semver.org/lang/nl/); zie [CHANGELOG.md](CHANGELOG.md).
