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

### Zoekparameters

`search` neemt deze parameters (alle optioneel):

| Parameter | Waarde |
|---|---|
| `brand`, `model` | slugs uit `list_brands` en `list_models`, bijvoorbeeld `toyota` en `rav4`; `model` vraagt een `brand` |
| `filters` | object met filtersleutel → optie of bereik. Opties: een waarde of lijst (`{"fuel_type": ["elektrisch", "waterstof"]}`; een lijst is OF). Bereiken: `{"min": x, "max": y}`, ieder deel optioneel (`{"price": {"max": 45000}}`). Meerdere filters zijn EN |
| `name_contains` | woorden die allemaal in de uitvoeringsnaam moeten staan (`"1.5 tsi life"`); doorzoekt hoogstens 20 pagina's, combineer met merk, model of filters |
| `sort` / `descending` | `make_model` (standaard), `price`, `year` of `power` |
| `page` | 20 modelgeneraties per pagina |

Welke sleutels en waarden er zijn, geeft `list_filters` (met aantallen). De belangrijkste sleutels: `fuel_type`, `body`, `transmission`, `wheeldrive`, `seat_count`, `door_count`, `segment`, `energy_rating`, `plugin_car`, `entrylevel` (instaphoogte: `1-580`, `581-680`, `681-` in mm) en bereiken `price`, `year`, `power_hp`, `elekactieradius`, `batterycapacity`, `min_trunkspace`, `maxweight_trailer_brakes`, `mass`, `length`, `topspeed`, `acceleration`, `consumption_combined`, `co2emission`. Bereiken nemen willekeurige getallen, niet alleen de stappen uit `list_filters`. Een onbekende optiewaarde geeft geen fout maar een leeg resultaat.

Een uitgebreidere handleiding voor taalmodellen staat in [llms.txt](llms.txt).

Voorbeeldvragen aan het model:
- *Welke elektrische SUV's onder € 50.000 hebben een hoge instap en een actieradius van meer dan 400 km?*
- *Vergelijk de Mazda CX-5 165 en 194 pk Luxury uit 2019.*
- *Wat is de instaphoogte van de Toyota RAV4 2.5 Hybrid uit 2016?*

## Installeren

Je hebt [uv](https://docs.astral.sh/uv/) nodig (of pip, zie onder). Er zijn geen API-sleutels nodig. De server praat via stdio (geen poort, geen netwerkdienst).

### Claude Code

```bash
claude mcp add --scope user carbase -- uvx --from git+https://github.com/vollebergh/carbase-mcp@v0.2.0 carbase-mcp
```

`--scope user` maakt hem beschikbaar in al je projecten; zonder de optie geldt hij alleen voor de huidige map. Start daarna een nieuwe sessie: de tools worden bij het starten van een sessie geladen.

```bash
claude mcp list              # staat carbase erbij en is hij verbonden?
claude mcp remove carbase    # verwijderen (bij bijwerken: eerst verwijderen, dan opnieuw toevoegen met de nieuwe tag)
```

Instellingen meegeven (zie [Cache op schijf](#hoe-het-werkt)), bijvoorbeeld de cache uitzetten:

```bash
claude mcp add --scope user carbase -e CARBASE_MCP_CACHE_MB=0 -- uvx --from git+https://github.com/vollebergh/carbase-mcp@v0.2.0 carbase-mcp
```

### Andere MCP-clients

```json
"carbase": {
  "command": "uvx",
  "args": ["--from", "git+https://github.com/vollebergh/carbase-mcp@v0.2.0", "carbase-mcp"],
  "env": { "CARBASE_MCP_CACHE_MB": "100" }
}
```

`env` is optioneel. Herstart de client na het wijzigen van de configuratie.

Pin op een tag, zodat er niet ongemerkt nieuwe code binnenkomt.

### Zonder uvx

Uit een gebouwde wheel (zie *Ontwikkelen*) of een kloon van de repo:

```bash
pip install builds/carbase_mcp-0.2.0-py3-none-any.whl   # of: pip install .
carbase-mcp                                              # start de stdio-server
```

Dan is `"command": "carbase-mcp"` (zonder `args`) genoeg in de clientconfiguratie. `carbase-mcp` kent geen opties; alle instellingen gaan via omgevingsvariabelen.

## Hoe het werkt

- **Zoeken** gebruikt de JSON die de Carbase-pagina's zelf ook laden (`?format=json`). Specificaties komen uit de HTML van `/auto/{id}/`.
- **Consentmuur van DPG Media:** de eerste aanvraag volgt de redirect, die een cookie (`authId`) zet. Er wordt niets aangeklikt. De cookie wordt in de cache op schijf bewaard, zie hieronder.
- **Zuinig met verzoeken:**
  - Hoogstens 2 verzoeken per seconde, en per tool-aanroep hoogstens 20 pagina's.
  - Geeft Autoweek een 429 of 503, dan pauzeert de server zolang Autoweek vraagt (standaard 5 minuten). Tijdens die pauze antwoordt hij alleen uit de cache.
- **Cache op schijf**, gedeeld door alle sessies van dezelfde gebruiker:
  - De consent-cookie (alleen `authId`), zodat niet elke nieuwe sessie de omweg via DPG maakt.
  - Specificaties 30 dagen, merken- en modellijsten 7 dagen, zoekresultaten 1 dag.
  - Begrensd in omvang en leeftijd; instelbaar via omgevingsvariabelen:

    | Variabele | Standaard | Betekenis |
    |---|---|---|
    | `CARBASE_MCP_CACHE_DIR` | `~/.cache/carbase-mcp` | cachemap, alleen voor de eigen gebruiker (0700); een gedeelde of andermans map wordt geweigerd |
    | `CARBASE_MCP_CACHE_MB` | `100` | maximale omvang; `0` zet de cache uit |
    | `CARBASE_MCP_CACHE_DAYS` | `30` | maximale leeftijd van elk item |

- **Alleen-lezen bij Autoweek:** de server doet alleen GET-verzoeken via https naar `www.autoweek.nl`. Dat wordt bij elke redirect gecontroleerd. Hij gebruikt geen sleutels en schrijft alleen in de eigen cachemap.

## Goed om te weten

- **Houd zoekopdrachten smal.** `search` geeft alle uitvoeringen van 20 modelgeneraties per pagina. Een brede vraag als alleen `volkswagen` + `golf` levert ± 1.070 uitvoeringen op (220 kB, ± 55.000 tokens); met een filter of `name_contains` is het enkele kilobytes. Zie [llms.txt](llms.txt).
- De data komt zoals Autoweek hem levert. Er zitten gaten en soms invoerfouten in; een voorbeeld is een instaphoogte van 43 cm bij een Subaru Outback.
- Je zoekvragen gaan naar Autoweek/DPG Media, net als bij gewoon gebruik van de website. Ze staan ook in de cache op schijf (tot 30 dagen); zet `CARBASE_MCP_CACHE_MB=0` als je dat niet wilt.
- Prijzen in de cache kunnen tot een week oud zijn (modellijst) of een dag (zoekresultaten).
- De uitvoer is data van derden. Behandel hem in je eigen agents als onbetrouwbare invoer.
- Werkt de server niet meer, dan heeft Autoweek waarschijnlijk de site veranderd.

## Ontwikkelen

```bash
uv sync                                  # omgeving met afhankelijkheden en dev-tools
uv run carbase-mcp                       # server vanuit de bron starten (wacht op MCP-berichten via stdio)
uv run pytest                            # offline tests
uv run pytest -m live                    # één test tegen www.autoweek.nl
uv run ruff check . && uv run ruff format --check .
uv build --out-dir builds/               # wheel en sdist
```

Een kloon als MCP gebruiken, bijvoorbeeld om aan de code te werken:

```bash
claude mcp add carbase-dev -- uv run --project /pad/naar/carbase-mcp carbase-mcp
```

Versies volgen [SemVer](https://semver.org/lang/nl/); zie [CHANGELOG.md](CHANGELOG.md). Een release is een commit met de nieuwe versie in `pyproject.toml` en een regel in de CHANGELOG, een tag en een build:

```bash
git tag -a vX.Y.Z -m "carbase-mcp X.Y.Z" && git push origin vX.Y.Z
uv build --out-dir builds/
```

Pas daarna de versie in de installatiecommando's hierboven aan.
