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
| Renderer, QA-Worker, Cockpit | noch nicht begonnen |

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

## Verzeichnisse

```
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
2. **Artefakte sind content-addressed.** Drei identische Kopien teilen ein Rendering und eine
   QA-Freigabe. Ändert sich ein Input, ändert sich der Fingerprint — und die alte Freigabe
   verfällt automatisch.
3. **Der gedruckte QR-Token ist stabil, der Karteninhalt nicht.**
   `card_twin.public_token` ändert sich nie, `render_artifact.fingerprint` bei jeder Korrektur.
4. **Die Verriegelung liegt in der Datenbank, nicht in der Anwendung.** Wenn in zwei Jahren
   jemand ein Bulk-Update schreibt, hält die Datenbank.

## Offene Entscheidungen vor dem ersten Druck

- **Ein QR-Token je Karteninhalt oder je physischer Kopie**
  (`design_family.token_per_copy`) — wird gedruckt, danach nicht korrigierbar.
- **Resolver-Host** (`system_config.twin.resolver_host`) — das QR-Payload-Budget beträgt
  47 Byte bei ECC Q; ein langer Host erzwingt einen größeren Code oder eine größere Karte.
- **Benennung und Zuschnitt der vier Templates** — bestimmt das Slot-Schema.
- **Mindestlosgröße und Lieferzeit der Druckerei** — setzen sechs Werte in `system_config`.

Alle als `is_placeholder = true` markierten Werte in `system_config` sind fachlich **nicht**
bestätigt und dürfen keine Zusage gegenüber Vereinen begründen.
