# Changelog

Alle noemenswaardige wijzigingen. Formaat: [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/), versies volgens [SemVer](https://semver.org/lang/nl/).

## [0.1.0] - 2026-11-18

### Toegevoegd
- Eerste versie: tools `list_brands`, `list_models`, `list_filters`, `search`, `get_specs` en `compare_versions`.
- Zoeken via de JSON-variant van Carbase (`?format=json`) met alle filters; specificaties uit de HTML van `/auto/{id}/`.
- DPG-consentcookie, throttling (0,5 s), TTL-cache, groottegrens en host-controle op redirects.
