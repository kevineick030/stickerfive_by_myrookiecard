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

**Entschieden: ein QR-Token je physischer Kopie** (`design_family.token_per_copy = true`).
Drei Karten desselben Spielers sind damit drei Items, drei `card_twin` und drei
`render_artifact` — aber alle drei tragen denselben `front_fingerprint`. Sie unterscheiden
sich nur auf der Rückseite. Foto, Freistellung, Komposition und die teuren QA-Gates 3a bis 3c
laufen genau einmal je Vorderseite; je Kopie kommen nur die Rückseite und die QR-Rücklesung
dazu. `create index render_artifact_front` findet die wiederverwendbare Vorderseite.

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
oder jede physische Karte einen eigenen bekommt. Für alle vier Templates steht der Wert auf
`true` — die Entscheidung wird gedruckt und ist danach nicht korrigierbar.

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
`DESIGN-4`: Ein Gruppenfoto hat keine Kopf-Anker, also greift dort `fit_mode: COVER` auf
demselben Slot.

## Prüfen

```bash
./db/run.sh --with-test
```

Der Smoke-Test bestätigt 16 Verriegelungen, darunter jede Bedingung des
`APPROVED → BATCHED`-Übergangs und die Unveränderlichkeitsregeln.

## Die Layout-Engine

`engine/layout.py` ist Schicht B: eine reine Funktion von Slot-Schema, Kartendaten und den
Landmarks aus Schicht A auf das Render-Manifest. Kein Zufall, keine Uhrzeit, kein
Modellaufruf — gleicher Input, gleiches Manifest, gleicher Fingerprint.

Zwei Punkte, die aus der Umsetzung kamen und im Konzept so nicht standen:

**Die Ankerregel braucht Reserve um den Kopf.** Deckt das Bild bei der Anker-Skalierung den
Slot nicht ab, weil zu eng fotografiert wurde, skaliert die Engine hoch — der Kopf wird
dadurch größer als das Zielmaß. Die Augenlinie bleibt exakt auf ihrem Anker, sonst zerfällt
das Set. Bis 15 % Abweichung ist das eine Warnung, darüber ein Gate-1-Fehler. Die daraus
folgenden Ausschnittsregeln (Bildbreite ≥ 2,02 × Kopfhöhe und so weiter) stehen in
`photo_spec` und werden von `tools/photo_requirements.py` aus der Geometrie hergeleitet,
nicht getippt.

**Die Auflösungsregel hängt an der Kopfhöhe, nicht an der Bildgröße.** Ein 4000-px-Foto mit
winzigem Kopf ist unbrauchbar, ein knappes Foto mit formatfüllendem Kopf ist bestens. Aus
Bild-Slot und Ankerregel folgt eine Mindest-Kopfhöhe von 391 px im Quellbild; Gate 1 prüft
die Folge nach der Skalierung erneut (`LOW_EFFECTIVE_DPI`).

## Das Partner-Gateway

`ingest_team_order(partner_code, payload)` nimmt die **normalisierte** Nutzlast auf — in einer
Transaktion, damit eine Bestellung entweder vollständig da ist oder gar nicht. Die Übersetzung
aus dem Fremdformat passiert vorher in `gateway/mapping.py`, gesteuert von einer Mapping-Datei.

Vier Dinge, die dabei bewusst so gebaut sind:

**Unbekannte Vertragsversion bricht ab.** `assert_supported_version` lehnt ab, was nicht in
`partner_contract_version` freigeschaltet ist. Ein stilles Fehlmapping wäre schlimmer als ein
Ausfall — man merkt es erst an der Palette, die von der Druckerei zurückkommt.

**Das Rohdaten-Archiv behält jede Fassung.** `partner_payload` ist append-only, der
Schlüssel enthält den Inhalts-Hash. Identische Wiederlieferung ist ein No-op, geänderter
Inhalt legt eine neue Archivzeile an. Das ist zugleich die Idempotenz und die Beweislage.

**Nach der Annahme wird nichts mehr still geändert.** `accept_team_order` friert die Daten als
Snapshot samt Hash ein. Kommt danach eine Korrektur vom Partner, entsteht ein
`partner_change_request` im Zustand `OPEN` — die Person und die Bestellzeilen bleiben
unverändert, bis jemand im Cockpit entscheidet.

**Ausgehendes läuft über die Outbox.** `outbox_claim` sperrt mit `for update skip locked`,
sodass zwei Worker denselben Vorgang nie doppelt senden; `outbox_settle` schreibt Erfolg oder
exponentielles Backoff. Der `dedupe_key` ist der fachliche Schlüssel des Vorgangs — zweimal
einstellen ist ein No-op.

### Ein Token, den jemand anderes vergibt

`card_twin.token_source` unterscheidet `INTERNAL` von `PARTNER`. Die Formatprüfung gilt nur
für selbst erzeugte Token (22 Zeichen Base58, keine verwechselbaren Zeichen); ein fremder Token
muss lediglich URL-sicher und 12 bis 48 Zeichen lang sein. Ob er noch groß genug gedruckt
werden kann, entscheidet die QR-Rechnung in Gate 1 — ein langer Token verkleinert die Module
und fällt dort auf, nicht erst beim Scannen.

## Der Auflösungsdienst

`resolve_twin(token)` liefert entweder den Karteninhalt oder `{"status":"GONE"}` — und zwar
dieselbe Antwort für **unbekannt, widerrufen und noch nicht gedruckt**. Sonst wäre der Dienst
ein Orakel, mit dem sich prüfen ließe, welche Token existieren.

Veröffentlicht wird beim Druck: der Trigger auf `card_item` setzt `published_at` und
`published_fingerprint`, sobald eine Karte den Zustand `PRINTED` erreicht. Ein Nachdruck mit
korrigiertem Inhalt aktualisiert nur den Fingerprint — der gedruckte Code funktioniert weiter.

Gezählt wird in `twin_scan_daily`: Tagessummen je Karte, ohne IP, ohne Gerät, ohne Uhrzeit.
Für „wie oft wird gescannt" reicht das, und es entsteht kein Bewegungsprofil von Kindern.

Der Dienst selbst (`resolver/`) hat zwei Bremsen mit unterschiedlichem Zweck:

- **Anfragen je Aufrufer** (60 pro Minute) — der eigentliche Schutz vor Überlast.
- **Ein Kurzzeitgedächtnis für falsche Token** — wer denselben falschen Code hundertmal
  abruft, kostet danach keine Datenbankabfrage mehr.

Die zweite Bremse darf **niemals einen echten Scan blockieren**. Genau dieser Fehler steckte in
der ersten Fassung: Eine IP, die zu oft danebengegriffen hatte, bekam anschließend auch mit
einem gültigen Code nichts mehr. Bei 128 Bit Zufall im Token ist Durchprobieren ohnehin
aussichtslos — die Bremse ist eine Kostenfrage, keine Sicherheitsmaßnahme, und wurde
entsprechend umgebaut.

## Das Cockpit

Die Oberfläche (`cockpit/`) liest ausschließlich aus den Sichten und enthält keine Fachlogik —
`v_cockpit_tiles` liefert die Statusleiste in einer Zeile, `v_cockpit_photo_trend` die
Tagesreihe, `v_team_board` das Kachelraster einer Bestellung.

**Der Not-Aus ist die einzige schreibende Aktion.** Er setzt `system_config.ops.transfers_paused`,
und `print_batch_guard()` weist damit jede Übertragung an die Druckerei ab. Die Verriegelung
liegt also in der Datenbank: Auch ein Hintergrunddienst, der die Oberfläche nie sieht, kommt
nicht daran vorbei. Jede Änderung wird als `domain_event` protokolliert, und das Formular trägt
ein Sitzungsmerkmal, damit eine fremde Seite den Schalter nicht auslösen kann.

### Warum genau ein Diagramm

Das Cockpit zeigt eine einzige Kurve: die Ausschussquote der Fotos über vierzehn Tage. Der
naheliegende Entwurf wäre ein gestapelter Balken mit den Qualitätsklassen A, B und C gewesen —
er scheitert daran, dass drei benachbarte Statustöne bei Rot-Grün-Schwäche nicht sicher
trennbar sind, und ein dunkleres Bernstein die Unterscheidbarkeit vollends verliert (geprüft,
nicht geschätzt).

Die Frage des Betreibers lautet ohnehin nicht „wie ist die Verteilung", sondern **„steigt der
Ausschuss?"** — das ist eine Reihe, kein Stapel. Damit entfällt das Farbproblem, und die Kurve
beantwortet die Frage direkter. Alles andere im Cockpit ist Kachel oder Tabelle: Zahlen, die man
vergleicht, gehören in Spalten, nicht in Balken.
