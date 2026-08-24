# Datenmodell — Leseanleitung

Ergänzt [`trading-card-engine.md`](trading-card-engine.md) um die Umsetzung.
Der Code steht in [`db/migrations/`](../../db/migrations).

## Der eine Schnitt, aus dem alles folgt

```
team_order          kaufmännische Klammer
  └─ order_line     WAS wurde bestellt: Person + Design + MENGE + Preis
       └─ card_item EINE physische Karte: Zustand, Artefakt, Bogenplatz
```

`expand_order_line(uuid)` erzeugt aus `quantity` die einzelnen `card_item`-Zeilen.
Drei Karten desselben Spielers sind drei Items, aber **ein** `render_artifact` und
**ein** `card_twin` — Rendering, QA und QR-Token laufen einmal.

Der Produktionsstatus einer Bestellung wird nicht gespeichert, sondern in
`v_team_order_production_status` **abgeleitet**. Gespeichert ist nur der kommandierte
Lebenszyklus (`team_order.lifecycle_state`: RECEIVED, ON_HOLD, CANCELLED, …). Ein separat
gepflegtes Statusfeld läuft garantiert irgendwann auseinander.

## Zwei Kennungen, die man nicht verwechseln darf

| | gehört zu | ändert sich | wird gedruckt |
|---|---|---|---|
| `card_twin.public_token` | der Karten-**Identität** | nie | ja |
| `render_artifact.fingerprint` | dem Karten-**Inhalt** | bei jeder Korrektur | nein |

Der Token wird per Trigger (`card_item_mint_twin`) beim Anlegen des Items vergeben — also
**vor** dem ersten Rendering, sonst ließe er sich nicht einbetten. 22 Zeichen Base58 aus
`gen_random_bytes`, nicht aus IDs abgeleitet und nicht aufzählbar: Der Token steht auf einer
Karte, die verloren gehen kann.

`design_family.token_per_copy` steuert, ob alle Kopien einer Zeile denselben Token tragen
(Standard) oder jede physische Karte einen eigenen bekommt.

## Der Zustandsautomat ist Daten

`card_item_transition` enthält jeden erlaubten Übergang als Zeile — nachlesbar, testbar,
ohne Deployment änderbar. `card_item_guard()` weist alles ab, was nicht in der Tabelle steht.

Der teure Übergang ist `APPROVED → BATCHED`, denn ab dort wird Papier verbraucht. Er verlangt
in derselben Transaktion:

1. ein Artefakt und einen Druck-Batch
2. ein QA-Verdikt `PASS` für **genau diesen** Fingerprint
3. den aus dem PDF zurückgelesenen QR-Token, passend zum Twin (Gate 3d)
4. keinen offenen HARD-Blocker
5. eine nicht widerrufene Einwilligungs-Assertion
6. übereinstimmende Druckspezifikation von Batch und Design — Gold-Folie darf nicht auf den
   Standardbogen

Der Transfer an die Druckerei (`print_batch.transferred_at`) verlangt zusätzlich eine
**frische Revalidierung** der Einwilligungen (Standard: 30 Minuten) und dass jede Karte im
Batch tatsächlich `BATCHED` ist.

## Was sich nicht ändern lässt

| Tabelle | Regel |
|---|---|
| `domain_event`, `partner_payload` | append-only, kein UPDATE, kein DELETE |
| `consent_assertion` | eingefroren; nur `revoked_at` und `last_revalidated_at` änderbar, ein Widerruf ist endgültig |
| `design_version` | nach `published_at` unveränderlich, nur neu versionierbar |
| `blocker.severity` | kommt immer aus `blocker_catalog` — ein SOFT-Blocker für eine fehlende Einwilligung ist nicht anlegbar |

## Aufbewahrung: zwei Uhren

`media_asset.retention_class` und `delete_after` trennen die Fristen. Rohbild kurz,
Freisteller und Druck-PDF mittel, digitale Karte dauerhaft. `v_retention_due` listet, was
fällig ist.

Der Freisteller überlebt das Original bewusst: Wird nur das Rohbild aufbewahrt und alles
Abgeleitete verworfen, ist nach Fristablauf kein Nachdruck mehr möglich.

## Spezifikationen

`specs/slot_schema.v1.json` und `specs/photo_spec.v1.json` sind die Quelle der Wahrheit;
`tools/gen_spec_seed.py` erzeugt daraus `db/seed/0002_specs.generated.sql`. Nach jeder
Änderung an `specs/` das Skript laufen lassen und beide Dateien gemeinsam committen — sonst
laufen Repository und Datenbank auseinander.

Alle vier Templates teilen dasselbe Slot-Schema. Die einzige bewusste Abweichung ist
`TC-TEAM`: Ein Gruppenfoto hat keine Kopf-Anker, also greift dort `fit_mode: COVER` auf
demselben Slot.

## Prüfen

```bash
./db/run.sh --with-test
```

Der Smoke-Test bestätigt 16 Verriegelungen, darunter jede Bedingung des
`APPROVED → BATCHED`-Übergangs und die Unveränderlichkeitsregeln.
