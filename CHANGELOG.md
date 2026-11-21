# Changelog

Alle noemenswaardige wijzigingen. Formaat: [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/), versies volgens [SemVer](https://semver.org/lang/nl/).

## [0.6.1] - 2026-11-21

### Opgelost
- Een onbekend merk dat Carbase met een lege pagina beantwoordt in plaats van een 404 (bijvoorbeeld `trabant`), gaf een lege lijst; `list_models`, `search` en `list_filters` geven nu `Unknown brand ...`.
- `get_fields`: bij een veld in meer secties vallen `n.b.`-waarden weg als een andere sectie een echte waarde heeft (`actieradius` gaf `VERBRUIK (NEDC): n.b.; VERBRUIK (WLTP): 534 km`).
- README: de 500e is een generatie van model `500` (Fiat en Abarth), geen eigen model; de tekst noemde hem ten onrechte een Abarth-model.

## [0.6.0] - 2026-11-21

### Gewijzigd
- `search`: `sort="power"` vervalt. Carbase kent alleen sorteren op merk/model, bouwjaar en prijs en negeerde `vermogen` stilzwijgend, zodat de volgorde niets met vermogen te maken had. Voor de sterkste auto's: filter `power_hp` en lees het vermogen met `get_fields`.
- `get_fields`: een veld dat in meer secties voorkomt (`max. vermogen` in `BRANDSTOFMOTOR` en `ELEKTROMOTOR`) gaf de waarde van de laatste sectie; nu staan alle waarden met hun sectie in het antwoord. Een sectie ervoor kiest er één: `"ELEKTROMOTOR: max. vermogen"`.
- `get_fields`: een onleesbaar versie-id laat niet langer de hele aanroep falen; die uitvoering krijgt een `error` (nieuw veld, anders `null`) en lege waarden. Alleen als geen enkele uitvoering te lezen is, volgt een fout.

### Opgelost
- `get_specs` negeerde een onbekende sectienaam als er ook een geldige bij stond; nu geeft elke onbekende naam een fout met de beschikbare secties. `compare_versions` accepteert een sectie die in een deel van de uitvoeringen ontbreekt, maar niet een die in geen enkele voorkomt.
- Een onbekend model dat Carbase met een lege pagina beantwoordt in plaats van een 404 (bijvoorbeeld `fiat`/`500e`), geeft nu `Unknown model ...` in `search` en `list_filters` in plaats van een leeg resultaat.
- `search` met `name_contains`: de `hint` legt uit dat `total_versions` vóór `name_contains` telt en dat een volgende pagina weinig treffers kan hebben.

### Documentatie
- README en tool-beschrijvingen: `plugin_car="plug-in"` omvat ook volledig elektrische auto's; bereikfilters gelden per uitvoering en `power_hp` is bij hybrides het gecombineerde vermogen; `ELEKTROMOTOR` bevat accu en laden (geen sectie `ACCU`); werkwijze voor "de sterkste auto's".

## [0.5.2] - 2026-11-19

### Opgelost
- De reparatie van 0.5.1 was onvolledig: een ontbrekend optioneel veld kwam als `null` in de uitvoer, terwijl het schema geen `null` toeliet, waardoor MCP-clients de uitvoer van `search` en `get_fields` weigerden ("Output validation error"). `hint`, `unknown_fields`, `options` en `steps` staan nu altijd in de uitvoer en zijn `null` als ze niet van toepassing zijn; het schema staat dat toe.
- Tests roepen alle zeven tools nu aan via een echte MCP-clientsessie, met de uitvoercontrole aan server- en clientkant.

## [0.5.1] - 2026-11-19

### Opgelost
- Sinds 0.4.0 faalden tools als een optioneel veld ontbrak: `search` zonder `hint` (alle resultaten passen), `get_fields` zonder `unknown_fields` en `list_filters` (een filter heeft `options` óf `steps`). Oorzaak: `from __future__ import annotations` in `models.py`, waardoor `TypedDict` `NotRequired` niet zag en elk veld verplicht maakte. Regressietests gaan nu door de uitvoercontrole van FastMCP.

## [0.5.0] - 2026-11-19

### Toegevoegd
- Optionele HTTP-modus voor clients die alleen externe MCP-servers kennen, zoals ChatGPT: `carbase-mcp --http [--port 8000] [--public-host HOST]`. Luistert alleen op 127.0.0.1; toegang via een geheim pad (`/<token>/mcp`, token uit `CARBASE_MCP_HTTP_TOKEN` of per start willekeurig); Host- en Origin-controle; hoogstens 32 sessies en 64 kB per verzoek; geen toegangslog. Stdio blijft de standaard.
- Licentie MIT-0 (`LICENSE`) en pakketgegevens (licentie, repository, changelog, trefwoorden, classifiers).

### Gewijzigd
- README: `llms.txt` opgenomen in het hoofdstuk "Voor taalmodellen"; installatie voor meerdere clients (Claude Code, Claude Desktop/Cursor, VS Code, opencode, ChatGPT); licentiesectie.

## [0.4.0] - 2026-11-19

### Toegevoegd
- Tool `get_fields(version_ids, fields)`: een paar velden (hoogstens 10) van 1–20 uitvoeringen in één antwoord, met suggesties voor onbekende veldnamen (B-10).
- Elke tool heeft een `outputSchema` via `TypedDict`-retourtypes in `models.py`; clients krijgen dezelfde data ook als `structuredContent` (B-12).
- CI (GitHub Actions, actions vastgepind op commit-SHA, alleen leesrechten): ruff, tests op Python 3.12 en 3.14, pip-audit en gitleaks. Dependabot voor uv en GitHub Actions met 7 dagen afkoelperiode (B-13).

### Gewijzigd
- `CLAUDE.md` en `.obsidian/` staan niet meer in de repository, ook niet in de geschiedenis; alle commits en tags zijn herschreven (B-19). Commit-hashes van eerdere versies zijn daardoor veranderd.

## [0.3.0] - 2026-11-18

Kleinere zoekantwoorden (B-17).

### Gewijzigd (niet terugwaarts compatibel)
- `search` geeft hoogstens `max_versions` uitvoeringen (1–500, standaard 100) en een `next_cursor` om met dezelfde argumenten verder te gaan (`cursor`). Een brede zoekopdracht als `volkswagen` + `golf` gaat van ± 220 kB (± 55.000 tokens) naar ± 21 kB.
- Vervallen: de parameter `page` en de velden `page`, `pages`, `name_contains`, `matches` en `complete` in het antwoord. Nieuw: `returned`, `next_cursor` en bij meer resultaten `hint`.
- `name_contains` werkt met dezelfde afkapping en cursor; een aanroep leest nog steeds hoogstens 20 Carbase-pagina's en geeft dan een `next_cursor`.
- Met `sort="price"` worden ook de uitvoeringen binnen een generatie op prijs gesorteerd (zonder prijs achteraan).
- Serverinstructie: smal zoeken, verder bladeren, lege resultaten bij onbekende filterwaarden, data als data behandelen, alleen persoonlijk gebruik.

## [0.2.0] - 2026-11-18

Minder belasting voor autoweek.nl.

### Toegevoegd
- Cache op schijf, gedeeld door alle sessies van een gebruiker. De consent-cookie (`authId`, met vervaldatum) wordt bewaard. Specificaties blijven 30 dagen, merken- en modellijsten 7 dagen en zoekresultaten 1 dag. Instelbaar via `CARBASE_MCP_CACHE_DIR`, `CARBASE_MCP_CACHE_MB` (standaard 100, `0` = uit) en `CARBASE_MCP_CACHE_DAYS` (standaard 30).
- Terugschakelen bij HTTP 429/503 volgens `Retry-After` (1 s–1 uur, standaard 5 min). Tijdens de pauze gaan er geen verzoeken naar Autoweek; de cache blijft antwoorden.

### Gewijzigd
- `search` laat de standaardsortering en pagina 1 weg uit de URL, zodat `list_models`, `list_filters` en `search(brand)` hetzelfde antwoord delen.
- De cache in het geheugen is vervangen door de schijfcache.

### Beveiliging
- De cache gebruikt alleen een eigen, privé map: geen symlink, van deze gebruiker, niet schrijfbaar voor anderen. Tijdelijke bestanden worden geopend met `O_NOFOLLOW` (S-09).

## [0.1.4] - 2026-11-18

### Gewijzigd
- `get_specs` en `compare_versions` gebruiken de echte URL van een uitvoering als die in een eerdere zoekopdracht voorbijkwam (hoogstens 20.000 onthouden). Dat scheelt per uitvoering een redirect en een verzoek naar Autoweek. Onbekende id's gaan nog via `/auto/{id}/x/`.
- URL's uit het antwoord van Autoweek worden alleen overgenomen als ze precies `/auto/{id}/{slug}/` zijn, met hetzelfde id.

## [0.1.3] - 2026-11-18

Ronde S van de security review.

### Beveiliging
- Elke uitgaande request, ook elke redirect-stap, mag alleen via https naar `www.autoweek.nl` of `myprivacy.dpgmedia.nl` (S-01, CWE-918).
- De cache is ook begrensd op omvang (50 M tekens) (S-02, CWE-770).

## [0.1.2] - 2026-11-18

Ronde A van de codebase review (CR-01 t/m CR-05, CR-09, CR-10).

### Gewijzigd
- Een gewijzigd antwoordformaat van Autoweek geeft een duidelijke `CarbaseError` in plaats van een kale `KeyError` (CR-01).
- Onbekend merk of model: melding met verwijzing naar `list_brands` / `list_models` (CR-04).
- `get_specs`/`compare_versions` met een onbekende sectienaam: fout met de beschikbare secties (CR-05).
- `search` met `name_contains` meldt `complete` als het maximum van 20 pagina's is bereikt (CR-03).
- Serverinstructie: data vanaf de jaren zeventig (CR-10).

### Opgelost
- `name_contains` struikelde over een uitvoering zonder naam (CR-02).

### Tests
- Offline tests voor `search` (URL-parameters, paginering), `list_models` en de foutvertaling (CR-09); 27 tests.

## [0.1.1] - 2026-11-18

### Gewijzigd
- Code verkleind: korte parametertypes, uitleg in de docstrings; filtertabel naar de serverlaag.
- Cache-opzoeking binnen de lock; verlopen en gebruikte items schuiven correct op in de LRU.

### Beveiliging
- httpx-logging op WARNING: de consent-redirect met de `authId` kwam anders in de logs.

## [0.1.0] - 2026-11-18

### Toegevoegd
- Eerste versie: tools `list_brands`, `list_models`, `list_filters`, `search`, `get_specs` en `compare_versions`.
- Zoeken via de JSON-variant van Carbase (`?format=json`) met alle filters; specificaties uit de HTML van `/auto/{id}/`.
- DPG-consentcookie, throttling (0,5 s), TTL-cache, groottegrens en host-controle op redirects.
