# Trading-Card-Engine — Architekturkonzept

Status: Entwurf zur Abstimmung · Stand: 2026-08-24
Kontext: Fusion B2C-Kartenshop (Etsy) × Marktführer Amateursport-Sammelalben ("Sticker-König")

---

## 0. Ausgangslage und Annahmen

Vollautomatisierte Verarbeitung von Teambestellungen (20–60 Spieler je Auftrag). Stammdaten,
DSGVO-Einwilligungen und Fotos kommen per API aus der Applikation des Partners. Die physische
Produktion übernimmt eine Großdruckerei.

Annahmen, die vor Umsetzungsbeginn zu bestätigen sind:

| # | Annahme |
|---|---|
| A1 | Sticker-König stellt eine HTTP-API bereit; wir konsumieren per Pull und/oder Webhook. |
| A2 | Ein erheblicher Teil der abgebildeten Personen sind Minderjährige → Einwilligung durch Erziehungsberechtigte. |
| A3 | Die Druckerei nimmt druckfertige PDF/X-Dateien plus maschinenlesbares Manifest entgegen (SFTP/S3/API). |
| A4 | Das bestehende Etsy-Backend bleibt zunächst unverändert in Betrieb. |
| A5 | Zielvolumen: 1.000–5.000 Karten/Tag im Peak, ausgeprägte Saisonspitzen. |

Hinweis: Das bestehende Etsy-Backend liegt nicht in diesem Repository. Alle Aussagen über den
Altbestand beruhen auf der Beschreibung, nicht auf einer Code-Analyse.

---

## 1. Architektur-Entscheidung: Neuer Standalone-Dienst

### 1.1 Es ist eine andere Domäne, nicht dasselbe in größer

**(a) Anderer Aggregate Root.** Im B2C-Shop ist die *Bestellung* die atomare Einheit; der Zustand
lebt auf der Bestellung. Im Teamgeschäft ist die *Karte* die Produktionseinheit und die
*Teambestellung* nur die kaufmännische Klammer. Teil-Auslieferung, Einzel-Nachdruck und gemischte
Designs verlangen einen Zustandsautomaten je Karte. Einen Item-Zustandsautomaten nachträglich in ein
System einzuziehen, dessen Queries, Webhooks und Statusfelder alle von „Bestellung hat einen Status"
ausgehen, ist der klassische Grund, warum solche Systeme verrotten.

**(b) Andere Rechtsperson im Datenmodell.** Etsy: Käufer = betroffene Person. Team: Besteller
(Verein/Trainer) ≠ betroffene Person (Spieler bzw. Erziehungsberechtigte). Einwilligungen,
Auskunfts- und Löschansprüche hängen am Spieler, nicht am Besteller. Das ist keine zusätzliche
Spalte, sondern ein anderes Schema — und der Teil mit dem Haftungsrisiko.

**(c) Anderes Lastprofil.** Etsy: konstanter Tropf, 1–3 Artikel, Sekunden pro Bestellung.
Team: Burst von 60 Renderings plus 60 Vision-Prüfungen in einem Schub, CPU/GPU-lastig, Minuten.
Im gemeinsamen Worker-Pool blockiert ein Teamauftrag den laufenden Shop. Man kann das mit
Prioritätsqueues entschärfen — dann hat man die Trennung aber ohnehin gebaut, nur schlechter.

**(d) Andere Fehlerkosten und Deploy-Kadenz.** Ein Etsy-Fehler kostet eine Erstattung. Ein
Team-Fehler betrifft 60 Personen, einen Verein, eine Deadline und einen bereits gebuchten
Druckbogen. Das neue System braucht andere Gates, anderes Monitoring und andere Deploy-Vorsicht.
Zudem darf der umsatztragende Altbestand während der Fusion nicht destabilisiert werden.

### 1.2 Was wir bewusst *nicht* bauen

Kein Microservice-Zoo. Empfehlung: **ein eigenständiger Dienst (Standalone Bounded Context),
intern modular geschnitten, mit getrennten Worker-Pools.**

- 1 API-Service (Ingest, Admin-API, Webhooks)
- 1 Datenbank (PostgreSQL) als Source of Truth, inklusive transaktionaler Job-Queue
- N Worker-Pools nach Ressourcenklasse: `assets` (Freistellung), `render` (PDF/PNG),
  `qa` (OCR/Vision), `transfer` (Druckerei), `notify`
- Object Storage (S3-kompatibel, EU-Region) für Assets und Artefakte

Warum *eine* Datenbank statt Datenbank-pro-Service: Die zentrale Invariante — „keine Karte in den
Druck ohne gültige Einwilligung und bestandene QA" — will man in einer Transaktion und in
DB-Constraints erzwingen, nicht über Eventual Consistency. Das ist der wasserdichte Teil.

### 1.3 Migrationspfad (Strangler Fig)

Nicht zwei Backends für immer, sondern:

1. **Phase 1** — Die Engine übernimmt B2B-Teamaufträge. Das Etsy-Backend bleibt unberührt.
2. **Phase 2** — Die Engine exponiert Render-, QA- und Print-Pipeline als interne API. Das
   Etsy-Backend wird deren Client; eine Etsy-Bestellung ist dann eine Teambestellung mit einer Zeile.
3. **Phase 3** — Das Legacy-Backend schrumpft auf Marktplatz-Anbindung (Etsy-Sync, Payouts).
   Produktionslogik existiert nur noch an einer Stelle.

### 1.4 Anti-Corruption Layer zum Partner

Das Fremdschema wird niemals ins Kerndomänenmodell durchgereicht. Ein `partner-gateway`-Modul leistet:

- Übersetzung Fremdschema → eigenes Schema, versioniert (`payload_version`)
- Idempotenz über `(partner_id, external_ref, payload_version)` — Webhook-Retries erzeugen keine Duplikate
- Rohdaten-Archiv: jede eingehende Payload roh plus Hash (Beweislage, Replay bei Mapping-Fehlern)
- Reconciliation: nächtlicher Soll-Ist-Abgleich mit dem Partner. Webhooks gehen verloren, immer.
- Contract Tests gegen eine Partner-Sandbox in der CI. Schemaänderungen brechen im CI, nicht in Produktion.

### 1.5 Zwei nicht verhandelbare Bauprinzipien

**Immutable Snapshot bei Auftragsannahme.** Mit der Annahme werden die Daten eingefroren
(`order_snapshot` inklusive Hash). Der Partner darf Spielerdaten danach ändern — was wir gedruckt
haben, bleibt dokumentiert. Ohne diesen Snapshot ist nach einer Reklamation nicht rekonstruierbar,
was tatsächlich passiert ist.

**Content-Addressed Artefakte.** Jedes Rendering ist eine reine Funktion:

```
fingerprint = hash(snapshot_row + design_version + asset_version + engine_version)
```

Daraus folgt: deterministisch, deduplizierbar (drei identische Karten = ein Rendering),
gefahrlos wiederholbar, und die QA-Freigabe klebt am Hash statt am Zeitpunkt. Ändert sich irgendein
Input, ändert sich der Hash und die alte Freigabe verfällt automatisch.

---

## 2. Automatisierte Qualitätskontrolle

### 2.1 Zwei Vorbemerkungen

**Zur 100-%-Automatisierung.** Das Ziel sollte lauten: 100 % automatisierter Happy Path plus eine
deterministische Quarantäne-Spur. Ein System ohne menschliche Bahn hat nicht 100 % Automatisierung —
es liefert 100 % der Fehler aus. Die Steuerungsgröße ist die **Auto-Pass-Rate** (Ziel > 99 %), nicht
die Abwesenheit einer Review-Queue. Bei 3.000 Karten/Tag entspricht das rund 30 Sichtprüfungen —
wenige Minuten Arbeit gegenüber einem Nachdruck von 60 Karten.

**Der Prüfer darf nicht der Renderer sein.** Eine QA, die dieselbe Bibliothek und denselben Code wie
der Renderer verwendet, erbt dessen Fehler. Die QA arbeitet ausschließlich auf dem **fertigen PDF,
rasterisiert zu Pixeln**, und vergleicht gegen den **Datenbank-Snapshot** — zwei unabhängige Pfade.

### 2.2 Die Gate-Kaskade

Billig und deterministisch zuerst, teuer und probabilistisch zuletzt.

#### Gate 0 — Eingangsvalidierung (vor dem Rendering)

- Pflichtfelder, Zeichensatz, Namenslänge gegen Layoutgrenzen
- Einwilligung vorhanden, gültig, richtige Textversion, bei Minderjährigen mit Nachweis der
  Erziehungsberechtigten → **Hard Gate**
- Foto: Mindestauflösung für 300 dpi im Endformat, Seitenverhältnis, Farbraum
- Genau ein Gesicht erkannt, Kopf innerhalb der Sicherheitszone
- **Die Zuordnung Foto → Spieler stammt ausschließlich aus der Partner-ID, niemals aus dem
  Dateinamen.** Dateinamen-Matching ist die häufigste Ursache vertauschter Karten.

#### Gate 1 — Render-Manifest (deterministisch, im Renderer)

Der Renderer erzeugt neben dem PDF ein Manifest: welcher String in welche Box, welcher Asset-Hash in
welchen Slot, Schriftgrößen, berechnete Textbreiten. Sofort prüfbar:

- Textüberlauf bzw. automatische Verkleinerung über Grenzwert
- Fehlende Glyphen (`.notdef`) — kritisch bei Namen wie „Đorđević"
- Effektive Bildauflösung am Platzierungsort ≥ 300 dpi
- Alle Pflicht-Slots belegt

Das fängt den Großteil aller Fehler ohne jede KI ab.

#### Gate 2 — Technischer Preflight (auf dem PDF)

PDF/X-Konformität, Schrifteinbettung, CMYK/ICC-Profil, Beschnitt- und Endformatboxen, Anschnitt,
Seitenzahl = erwartete Kartenzahl, Überdrucken-Einstellungen. Standardwerkzeuge (Ghostscript,
veraPDF), kein Eigenbau.

#### Gate 3 — Perzeptive Verifikation

Die eigentliche Prüfung „steht der richtige Name auf dem richtigen Foto". PDF bei 300 dpi rastern, dann:

**3a — Regionsbezogenes OCR.** Aus dem Manifest ist bekannt, *wo* der Name steht. Es wird nur dieser
Ausschnitt an die OCR gegeben, nicht die ganze Seite — das ist deutlich zuverlässiger. Vergleich
gegen den DB-Wert nach Unicode-Normalisierung (NFC), Case-Folding und Diakritika-Behandlung.
Bewertung: exakte Übereinstimmung = Pass; Levenshtein ≤ 1 bei Namen > 6 Zeichen = Pass mit Warnung;
sonst Fail. Analog für Rückennummer, Verein, Saison, Position.

**3b — Bildidentität statt Gesichtserkennung.** Die Frage lautet nicht „wer ist das", sondern „ist
das genau das Foto, das zu diesem Datensatz gehört". Also: gerenderten Fotobereich ausschneiden, die
geometrische Transformation aus dem Manifest zurückrechnen und gegen das Quell-Asset vergleichen —
perzeptueller Hash (pHash/dHash), Feature-Matching (ORB) und SSIM, zusammengeführt zu einem
Ähnlichkeitswert mit klarer Schwelle.

> **Bewusste Entscheidung:** Das ist *keine* biometrische Gesichtserkennung. Gesichts-Embeddings
> gegen eine Personendatenbank wären biometrische Daten nach Art. 9 DSGVO — bei Minderjährigen ein
> Risiko, das man nicht eingeht. Der Bildvergleich Quelle ↔ Rendering ist eine rein technische
> Integritätsprüfung: günstiger, deterministischer und rechtlich unbedenklich.

**3c — Vision-Modell als Eskalation, nicht als Standard.** Ein Vision-Modell beantwortet holistische
Fragen, die sich schlecht in Regeln fassen lassen: überlappende Elemente, verrutschte
Freistellungskante, Halo um den Kopf, kopfstehende Karte, Artefakte in der Maske. Aufruf **nicht** bei
jeder Karte, sondern bei niedriger Konfidenz aus 3a/3b, bei jeder neuen Design-Version und als
Stichprobe (z. B. 2 %). Die Antwort wird strukturiert angefordert (JSON mit Befund und Konfidenz),
nie als Freitext interpretiert.

#### Gate 4 — Batch-übergreifende Prüfungen

Erst auf Ebene des Druckauftrags sichtbar:

- Kartenanzahl = Summe der bestellten Mengen
- Keine Person mit zwei unterschiedlichen Fotos im selben Batch
- Keine doppelte `card_item_id`
- Rückennummern innerhalb des Teams eindeutig (Warnung, kein Fail — Ausnahmen existieren)
- Nutzenplan: Bogenposition ↔ Karten-ID konsistent

#### Gate 5 — Quarantäne

Alles, was durchfällt oder unsicher bleibt, geht in die Review-Queue: Side-by-Side-Ansicht
(Datensatz links, gerenderte Karte rechts, beanstandete Region markiert) mit drei Aktionen —
*Freigeben*, *Neu rendern*, *Blockieren*. Jede Entscheidung wird mit Nutzer, Zeit und Begründung
protokolliert.

### 2.3 Die Freigabe-Verriegelung

Die QA-Freigabe wird gegen den `artifact_fingerprint` gespeichert, nicht gegen die Karten-ID.
Der Transfer an die Druckerei prüft in derselben Transaktion:

```
qa_verdict.decision      = PASS
qa_verdict.fingerprint   = card_item.artifact_fingerprint
offene HARD-Blocker      = 0
consent_valid_at(now)    = true
```

Ändert sich irgendetwas am Input, passt der Hash nicht mehr und der Transfer bricht ab. Das ist die
Verriegelung, die verhindert, dass jemals eine nicht freigegebene Datei die Druckerei erreicht.

### 2.4 Golden Set

Ein fixes Testteam mit absichtlich schwierigen Fällen — sehr lange Namen, Umlaute, Apostroph,
Diakritika, sehr helles und sehr dunkles Foto, Brille, Mütze, unruhiger Hintergrund — läuft bei
**jeder** Änderung an Template, Renderer oder QA-Schwellen automatisch durch die komplette Pipeline,
mit Pixelvergleich gegen freigegebene Referenzbilder. Ohne dieses Regressionsnetz verschiebt jede
Template-Änderung unbemerkt Textboxen.

---

## 3. Datenmodell und Edge Cases

### 3.1 Die zentrale Modellierungsentscheidung

**Kaufmännische Absicht und Produktionseinheit werden getrennt.**

- `order_line` = *was wurde bestellt* — Person + Design + **Menge** + Preis
- `card_item` = *eine physische Karte* — ein Zustand, ein Artefakt, ein Platz auf dem Bogen

Bei Auftragsannahme wird jede Zeile in `quantity` Items expandiert. Alle drei Sonderfälle lösen sich
damit aus der Modellierung heraus, statt in Sonderfall-Code zu landen.

Zwei Regeln folgen daraus:

1. **Menge lebt auf der Zeile, Zustand lebt auf dem Item.** Ein blockierter Spieler blockiert
   niemals das Rendering der anderen 59.
2. **Der Status der Teambestellung wird abgeleitet, nie gepflegt.** Er ist eine Projektion über die
   Item-Zustände, neu berechnet bei jedem Item-Übergang. Ein separat gepflegtes Statusfeld läuft
   garantiert auseinander.

### 3.2 Kernentitäten

| Entität | Zweck | Wesentliche Felder |
|---|---|---|
| `partner` | Mandant (Sticker-König, später weitere) | `id`, `name`, `api_config` |
| `club` / `team` | Verein, Team | `season`, `sport`, `age_group` |
| `person` | Betroffene Person (Spieler, Trainer) | `role`, `is_minor`, `guardian_ref`, `external_ref` |
| `ordering_contact` | Besteller, Rechnungsempfänger | getrennt von `person` |
| `consent` | **Append-only** Einwilligungshistorie | `person_id`, `purpose`, `text_version`, `granted_at`, `granted_by`, `evidence_ref`, `revoked_at` |
| `media_asset` | Unveränderliches Asset | `content_hash`, `origin`, `person_id`, `consent_id`, `parent_asset_id`, `processing_version` |
| `design_version` | Veröffentlichtes, unveränderliches Template | `print_spec_id`, `slots` |
| `team_order` | Kaufmännische Klammer | `fulfillment_policy`, `shipment_policy`, `hold_until`, `snapshot_hash`, `derived_status` |
| `order_line` | Bestellte Position | `person_id`, `design_version_id`, `quantity`, `line_type`, `unit_price`, `recipient_group_key` |
| `card_item` | Eine physische Karte | `order_line_id`, `copy_index`, `state`, `artifact_fingerprint`, `wave_id`, `print_batch_id`, `sheet_position` |
| `render_artifact` | Content-addressed Renderergebnis | `fingerprint` (PK), `pdf_ref`, `preview_ref`, `manifest`, `engine_version` |
| `qa_verdict` | Prüfergebnis je Artefakt | `fingerprint`, `gate_results`, `decision`, `confidence`, `decided_by` |
| `blocker` | Offenes Hindernis je Item | `reason`, `severity`, `owner`, `opened_at`, `resolved_at`, `remediation_attempts` |
| `production_wave` | Produktionswelle innerhalb eines Auftrags | `team_order_id`, `sequence`, `released_at` |
| `print_batch` | Was an die Druckerei geht | `print_spec_id`, `external_job_ref`, `transferred_at`, `acknowledged_at`, `manifest_hash` |
| `shipment` | Lieferung an den Verein | `consolidates[]`, `carrier_ref` |
| `domain_event` | Append-only Audit-Trail | `correlation_id`, `subject`, `type`, `payload`, `at` |

### 3.3 Fall 1 — Ein Spieler möchte 2 oder 3 Karten von sich

Gelöst über `order_line.quantity` plus Expansion in `card_item`.

- Drei Karten = eine Zeile mit `quantity = 3` → drei `card_item`-Zeilen mit `copy_index` 1..3.
- **Aber nur ein `render_artifact`.** Identischer Fingerprint bedeutet: Rendering und QA laufen
  einmal, die drei Items zeigen auf dasselbe Artefakt. Bei 60 Spielern mit Zusatzkarten spart das
  reale Rechenzeit und Vision-Kosten.
- `line_type` unterscheidet Grundpaket (`base_pack`) von Zusatzkarte (`extra_copy`) und Upgrade —
  relevant für Staffelpreise und Rechnungsstellung.
- `recipient_group_key`: Zusatzkarten gehören in das Tütchen *dieses* Spielers, nicht lose in den
  Karton. Die Konfektionierung erhält diesen Schlüssel im Manifest — sonst sortiert der Trainer
  200 Karten von Hand.
- Warum trotzdem drei einzelne Items statt eines Mengenfeldes: Nachdruck einer einzelnen
  beschädigten Karte, Einzelreklamation, exakte Bogenposition. Die Zeilen kosten nichts, die
  Nachvollziehbarkeit ist entscheidend.

### 3.4 Fall 2 — Unterschiedliche Designs innerhalb einer Bestellung

**Das Design hängt an der Zeile, nicht an der Bestellung.** `team_order.default_design_version_id`
ist reine Bequemlichkeit; `order_line.design_version_id` gewinnt immer.

Auflösung über Regeln, aber **materialisiert**:

- `person.role` ∈ {`goalkeeper`, `field`, `coach`, `staff`} kommt aus der Partner-API.
- `design_rule` am Auftrag: „role = goalkeeper → GK-2025", „role = coach → Gold-Edition".
- Die Regeln werden **einmal bei Auftragsannahme ausgewertet** und das Ergebnis in die Zeile
  geschrieben. Niemals lazy beim Rendern auflösen — Regeln ändern sich, und es muss reproduzierbar
  bleiben, warum diese Karte dieses Design bekam. Die Auswertung wird als `domain_event` protokolliert.
- Freie Übersteuerung je Spieler bleibt jederzeit möglich, weil die Zeile die Wahrheit ist.

Zwei Aspekte, die dabei sonst übersehen werden:

**(a) Team-Kontext vs. Karten-Design.** Vereinslogo, Sponsor, Saison und Farbwelt liegen in einem
`team_design_context`, den alle Designs derselben Bestellung konsumieren. Sonst wirkt ein
Mixed-Design-Set nicht mehr wie ein Set — das ist der Unterschied zwischen „verschiedenen Karten"
und „einem Sammelset".

**(b) Nicht jedes Design darf in denselben Druckbogen.** Goldveredelung, anderes Papier oder anderes
Format bedeuten einen anderen Produktionsprozess. Deshalb trägt `design_version` eine
`print_spec_id`, und die Batch-Bildung gruppiert **nach `print_spec`, nicht nach Bestellung**:

> Eine Teambestellung → *n* Druck-Batches (nach Druckspezifikation) → 1 konsolidierte Lieferung.

Das ist der Grund, warum kaufmännischer Auftrag, Produktions-Batch und Lieferung drei getrennte
Entitäten sein müssen. Nebeneffekt: Batches lassen sich **bestellungsübergreifend** bündeln —
zwölf Gold-Trainerkarten aus zwölf Vereinen laufen auf einem Bogen statt auf zwölf. Ein direkter
Margenhebel.

### 3.5 Fall 3 — Foto fehlt oder Freistellung schlägt fehl

Das ist keine technische, sondern eine **Policy-Frage** — sie gehört als Feld ins Datenmodell,
nicht als `if` in den Code.

#### Schritt 1 — Blocker klassifizieren

| Grund | Schwere | Verantwortlich | Auto-Remediation |
|---|---|---|---|
| Einwilligung fehlt / widerrufen | HARD | Partner/Verein | keine — Produktion verboten |
| Minderjährig ohne Nachweis | HARD | Partner/Verein | keine |
| Foto fehlt | SOFT | Verein | Nachforderung |
| Foto zu klein / unbrauchbar | SOFT | Verein | Nachforderung |
| Freistellung fehlgeschlagen | SOFT | intern | Retry-Leiter |
| QA-Fail (Text/Bild) | SOFT | intern | Neu-Rendering |
| Stammdaten unvollständig | SOFT | Partner | Nachforderung |

**HARD-Blocker werden niemals umgangen.** Ohne gültige Einwilligung wird die Karte nicht produziert —
auch nicht vorsorglich. Das ist die eine Stelle ohne Policy-Option.

#### Schritt 2 — Remediation-Leiter bei Freistellungsfehlern

Jeder Schritt protokolliert, mit eigener SLA:

1. Retry mit alternativen Parametern (anderes Segmentierungsmodell, anderer Schwellwert)
2. Retry mit Hintergrund-Hypothese (einfarbig / Rasen / Halle)
3. Manuelle Retusche-Queue (intern oder beim Partner)
4. Neues Foto anfordern — automatisierte Nachricht an den Vereinskontakt über den Partnerkanal

#### Schritt 3 — Fulfillment-Policy am Auftrag

`team_order.fulfillment_policy`:

- `all_or_nothing` — nichts geht in Produktion, bis alle Items grün sind. Für Vereine, die zwingend
  ein vollständiges Set wollen.
- `partial_with_hold` — **Standard.** Fertige Items werden gerendert und QA-geprüft, der Transfer
  wartet bis `hold_until`. Nach Fristablauf wird automatisch gespalten.
- `partial_ship_immediately` — sofortige Teilproduktion, Rest als Nachzügler.

#### Schritt 4 — Wellen statt Mutation

Beim Split wird der Auftrag **nicht verändert**. Es entsteht eine `production_wave`:

- Welle 1: 55 Karten → Batch → Druck
- Welle 2: 5 Nachzügler, sobald die Blocker gelöst sind

Der `team_order` bleibt die kaufmännische Wahrheit und steht auf `PARTIALLY_COMPLETE`, bis alle
Wellen abgeschlossen sind. Kein Datensatz wird überschrieben, die Historie bleibt lesbar.

#### Schritt 5 — Versand entkoppeln

`shipment_policy`: `consolidate` (Standard im Amateursport — der Trainer will *eine* Kiste) mit
`max_consolidation_wait`, alternativ `ship_per_wave`. Läuft die Wartefrist ab, geht Welle 1 raus und
Welle 2 folgt nach.

#### Schritt 6 — Wirtschaftlichkeitsschwelle

Ein Nachzügler-Batch mit fünf Karten kostet bei der Druckerei fast so viel wie einer mit sechzig.
Deshalb gehört ein `wave_split_cost_threshold` ins System: Unterhalb einer Mindestmenge wird eine
Welle nicht sofort produziert, sondern sammelt sich mit Nachzüglern anderer Bestellungen auf einem
gemeinsamen Bogen. Diese Entscheidung darf das System automatisch treffen, muss sie aber im Cockpit
sichtbar machen.

### 3.6 Zustandsautomat `card_item`

```
DRAFT → DATA_VALIDATED → ASSET_READY → RENDER_QUEUED → RENDERED
      → QA_PASSED → APPROVED → BATCHED → SENT_TO_PRINT → PRINTED
      → PACKED → SHIPPED → DELIVERED
```

Nebenzustände: `BLOCKED` (mit Blocker-Referenz; Rückkehr an die Austrittsstelle), `QA_FAILED`
(→ Review oder Re-Render), `CANCELLED`, `REPRINT_REQUESTED`.

**Die eine Übergangsregel, die alles trägt.** `APPROVED → BATCHED` ist nur zulässig, wenn in
derselben Transaktion gilt: QA-Verdikt `PASS`, Verdikt-Fingerprint = Item-Fingerprint, keine offenen
HARD-Blocker, Einwilligung aktuell gültig. Erzwungen als DB-Constraint bzw. Trigger, nicht nur in der
Anwendungsschicht — damit ein Bulk-Update in zwei Jahren nicht daran vorbeikommt.

### 3.7 Zustandsautomat `team_order` (abgeleitet)

```
RECEIVED → VALIDATING → IN_PRODUCTION → PARTIALLY_COMPLETE → COMPLETE → CLOSED
                                     ↘ ON_HOLD    ↘ CANCELLED
```

### 3.8 Datenschutz als Struktur, nicht als Anhang

- Einwilligung ist eine **Vorbedingung im Zustandsautomaten**, kein Häkchen im Formular.
- Widerruf löst ein Event aus: noch nicht gedruckt → Item wird storniert; bereits gedruckt →
  dokumentiert, Assets gelöscht, Nachdrucke gesperrt.
- Aufbewahrung: Originalfotos und Artefakte mit getrennten Fristen und automatischem Löschjob.
  Nach Ablauf bleibt der Audit-Trail ohne Bilddaten bestehen.
- Fotos Minderjähriger: niemals öffentlicher Bucket, ausschließlich signierte URLs mit kurzer
  Laufzeit, EU-Region.
- Druckerei = Auftragsverarbeiter → AVV erforderlich; Übergabe über authentifizierten Kanal mit
  Quittung, nie als E-Mail-Anhang.
- Logs: Personendaten pseudonymisiert, Klartext ausschließlich in der Fachdatenbank.

---

## 4. Admin-Cockpit

Drei Flughöhen: Zustand der Fabrik → Arbeitsvorrat → Forensik am Einzelfall.

### 4.1 Statusleiste (immer sichtbar)

| Kachel | Warum sie oben steht |
|---|---|
| **Auto-Pass-Rate (24 h rollierend)** | Die wichtigste Qualitätszahl. Trend plus Schwellwert. |
| **Karten in Produktion / heute fällig / Kapazität** | Durchsatz gegen Bedarf. |
| **Aufträge mit Terminrisiko** | Nach verbleibender Pufferzeit sortiert — im Saisongeschäft die geschäftskritischste Zahl. |
| **Blockierte Items, getrennt HARD / SOFT** | HARD ist Rechtsrisiko, SOFT ist Arbeit. |
| **Queue-Tiefe und Alter des ältesten Jobs je Pool** | *Alter* ist das Alarmsignal, nicht Tiefe. Eine tiefe, schnell abfließende Queue ist gesund; ein 40 Minuten alter Job in flacher Queue heißt: es hängt. |
| **Druck-Batches: bereit / übertragen / unquittiert** | Unquittiert > 2 h ist ein Vorfall. |
| **Fehlerrate und DLQ-Größe** | Mit Replay-Aktion. |
| **Kosten je Karte** (Render + Vision + Storage) | Belegt Skalierbarkeit — die Zahl für das Partnergespräch. |

### 4.2 Arbeits-Queues (Aufgaben, keine Logs)

Jede Queue mit Anzahl, Alter des ältesten Eintrags und Ein-Klick-Aktion:

1. **QA-Review** — Side-by-Side Datensatz ↔ Rendering, beanstandete Region hervorgehoben;
   Freigeben / Neu rendern / Blockieren
2. **Blockierte Items** — nach Team gruppiert, „Verein erinnern" als Ein-Klick-Aktion
3. **Freistellung / Retusche**
4. **Integrationsfehler** (Partner-API, Druckerei) mit Replay
5. **Offene Entscheidungen** — „jetzt splitten oder auf Nachzügler warten?" mit Kostenfolge daneben
6. **Reklamation / Nachdruck**

### 4.3 Das Team-Board

Eine Teambestellung als Raster aus 60 Kachelvorschauen. Jede Kachel zeigt Miniatur, Name,
Zustandsfarbe und Blocker-Symbol. Ein Blick genügt: 55 grün, 3 gelb (Foto fehlt), 2 rot
(Einwilligung). Klick auf eine Kachel öffnet die vollständige Karten-Historie — Rohdaten des
Partners, Einwilligungsversion, Asset-Kette, Render-Manifest, alle QA-Gate-Ergebnisse mit Messwerten,
Batch und Bogenposition.

### 4.4 Steuerung und Sicherheitsnetz

- **Not-Aus für Transfers.** Ein Schalter, der alle Übertragungen an die Druckerei anhält. Ab dem
  Transfer kostet jeder Fehler Papier und Zeit — die billigste Versicherung im System.
- **Canary für Design-Versionen.** Eine neu veröffentlichte Template-Version schickt die ersten
  *n* Karten automatisch in die menschliche Freigabe, bevor sie vollautomatisch läuft.
- **Rate-Limit und Drosselung** je Partner und je Worker-Pool.
- **Alarme statt Dashboards.** Auto-Pass-Rate unter Schwelle, ältester Job über SLA, Batch
  unquittiert, HARD-Blocker älter als *x*, Kosten je Karte über Budget. Ein Dashboard, das niemand
  ansieht, ist kein Monitoring.

### 4.5 Durchgängige Korrelation

Eine `correlation_id` von der eingehenden Partner-Payload über Auftrag, Item, Artefakt und
QA-Verdikt bis zum Druckauftrag. Im Cockpit muss eine Suche nach Spielername, Auftragsnummer oder
Batch-ID dieselbe Kette öffnen. Ohne das ist Fehlersuche bei tausenden Karten pro Tag nicht machbar.

---

## 5. Nächste Schritte

1. **Partner-API-Vertrag fixieren** — Schema, Einwilligungsformat, Foto-Spezifikation, Idempotenz,
   Sandbox. Größtes Projektrisiko, weil extern.
2. **Druckerei-Schnittstelle fixieren** — Dateiformat, Manifest, Quittung, Nutzenplan,
   Konfektionierung, Mindestlosgröße.
3. **Datenmodell und Zustandsautomaten** als Migration festschreiben.
4. **Golden Set aufbauen**, bevor der erste Renderer entsteht.
5. **Vertikaler Durchstich** — ein echtes Team, 20 Spieler, gemischte Designs, ein bewusst
   fehlendes Foto, end-to-end bis zur Druckdatei.

### Offene Punkte für das Partnergespräch

- Verbindliche Fotospezifikation (Auflösung, Hintergrund, Aufnahmebedingungen) — bestimmt die
  Fehlerquote der Freistellung maßgeblich.
- Versionierung der Einwilligungstexte: Wer besitzt sie, wie wird eine Änderung propagiert?
- Wer kommuniziert Nachforderungen mit dem Verein — Partner oder wir?
- Mindestlosgröße und Vorlaufzeit der Druckerei — bestimmt `wave_split_cost_threshold`.
- Zugesagte Lieferzeit gegenüber dem Verein — bestimmt `hold_until` und die SLA-Schwellen.
