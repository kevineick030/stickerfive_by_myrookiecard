# Trading-Card-Engine

Produktionsstrecke für Teambestellungen im Amateursport: Stammdaten und Fotos kommen per API
vom Partner, vier Templates werden deterministisch bestückt, jede Karte durchläuft eine
automatisierte Prüfkaskade, und hinter dem QR-Code auf der Rückseite liegt eine dauerhaft
verfügbare digitale Karte.

## Stand

| Bereich | Stand |
|---|---|
| Architekturkonzept | [`docs/architecture/trading-card-engine.md`](docs/architecture/trading-card-engine.md) — Rev. 2 |
| Datenmodell | [`db/migrations/`](db/migrations) — lauffähig, Verriegelungen getestet |
| Slot-Schema, `photo_spec` | [`specs/`](specs) — v1, Maße und Schwellwerte sind Platzhalter |
| Layout-Engine (Schicht B) + Gate 1 | [`engine/`](engine) — lauffähig, 23 Tests |
| Freistellung (Schicht A), QA-Worker, Partner-Gateway, Cockpit | noch nicht begonnen |

## Loslegen

```bash
createdb tce
export PGDATABASE=tce
./db/run.sh --with-test
```

`run.sh` generiert den Spec-Seed aus `specs/`, spielt Migrationen und Referenzdaten ein und
lässt auf Wunsch den Smoke-Test laufen. Der Test prüft in einer zurückgerollten Transaktion,
dass sich die 16 Verriegelungen nicht umgehen lassen — unter anderem: keine Karte in den Druck
ohne bestandene QA, ohne passenden QR-Token, mit offenem HARD-Blocker oder auf dem falschen
Druckbogen.

## Layout-Engine ansehen

```bash
python3 tools/render_sample.py        # Musterblatt nach out/sample-sheet.html
python3 tools/photo_requirements.py   # Fotoanforderungen aus der Slot-Geometrie
python3 -m unittest discover -s engine/tests -t .
```

`render_sample.py` baut vier Karten aus dem echten Slot-Schema und lässt jede durch Gate 1
laufen. Die Vorschau wird ausschließlich aus dem Render-Manifest gezeichnet — was dort zu
sehen ist, steht auch im Manifest, und Gate 1 prüft dieselben Zahlen.

Ohne externe Bibliotheken: `engine/fontmetrics.py` liest TrueType-Metriken selbst, damit
Autofit eine Messung ist und fehlende Glyphen (`Đorđević`) vor dem Druck auffallen. Der
QR-Code wird in der Vorschau nur **schematisch** gezeichnet — Version, Modulanzahl und
Modulgröße sind echt gerechnet, der Encoder gehört in die Produktion und kommt dort aus
einer geprüften Bibliothek.

## Verzeichnisse

```
engine/          Layout-Engine, Schriftmetriken, Gate 1, SVG-Vorschau
db/migrations/   Schema, Zustandsautomat, Sichten
db/seed/         Referenzdaten (0002 ist generiert — nicht von Hand ändern)
db/test/         Smoke-Test der Verriegelungen
specs/           Slot-Schema und photo_spec als versionierte Quelle der Wahrheit
tools/           gen_spec_seed.py erzeugt db/seed/0002 aus specs/
docs/            Architekturkonzept
```

## Die vier Regeln, die alles tragen

1. **Menge lebt auf der Zeile, Zustand lebt auf dem Item.** `order_line.quantity` wird in
   `card_item`-Zeilen expandiert. Ein blockierter Spieler blockiert nie die anderen 59.
2. **Artefakte sind content-addressed, und die Vorderseite zählt getrennt.** Jede Kopie hat
   einen eigenen QR-Token, also einen eigenen `fingerprint` — aber denselben
   `front_fingerprint`. Foto, Komposition und die teuren QA-Gates laufen einmal je
   Vorderseite. Ändert sich ein Input, ändert sich der Fingerprint und die alte Freigabe
   verfällt automatisch.
3. **Der gedruckte QR-Token ist stabil, der Karteninhalt nicht.**
   `card_twin.public_token` ändert sich nie, `render_artifact.fingerprint` bei jeder Korrektur.
4. **Die Verriegelung liegt in der Datenbank, nicht in der Anwendung.** Wenn in zwei Jahren
   jemand ein Bulk-Update schreibt, hält die Datenbank.

## Offene Entscheidungen vor dem ersten Druck

- **Resolver-Host** (`system_config.twin.resolver_host`) — das QR-Payload-Budget beträgt
  74 Byte, damit passt jeder realistische Domainname. Ein kurzer Host senkt die QR-Version
  und vergrößert die Module, was das Scannen zerkratzter Karten robuster macht.
- **Benennung und Zuschnitt der vier Templates** — liegen als `DESIGN-1` bis `DESIGN-4`,
  Slot-Geometrie in `specs/slot_schema.v1.json` ist bis zum ersten Andruck vorläufig.
- **Mindestlosgröße und Lieferzeit der Druckerei** — setzen sechs Werte in `system_config`.

Alle als `is_placeholder = true` markierten Werte in `system_config` sind fachlich **nicht**
bestätigt und dürfen keine Zusage gegenüber Vereinen begründen.
