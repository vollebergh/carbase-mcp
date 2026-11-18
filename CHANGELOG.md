# Changelog

Alle noemenswaardige wijzigingen. Formaat: [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/), versies volgens [SemVer](https://semver.org/lang/nl/).

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
