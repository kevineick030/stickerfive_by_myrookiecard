# Trading-Card-Engine — Architekturkonzept

Status: Entwurf zur Abstimmung · **Rev. 2** · Stand: 2026-08-24
Kontext: Fusion B2C-Kartenshop (Etsy) × Marktführer Amateursport-Sammelalben ("Sticker-König")

---

## 0. Ausgangslage, Annahmen, Änderungen

Vollautomatisierte Verarbeitung von Teambestellungen (20–60 Spieler je Auftrag). Stammdaten,
Einwilligungen und Fotos kommen per API aus der Applikation des Partners. Die physische Produktion
übernimmt eine Großdruckerei.

### 0.1 Was sich gegenüber Rev. 1 geändert hat

| # | Präzisierung | Architektonische Folge |
|---|---|---|
| 1 | Die Fotos sind **keine Profi-Aufnahmen**. Der Partner hat zwar einen Fotografen, in der Regel lädt aber der Kunde sein Bild selbst in die Partner-Software. | Die Fehlerquote der Freistellung wird zum Haupttreiber der Handarbeit. Neuer Abschnitt 2: Qualitätssicherung **an der Quelle**, nicht erst in unserer Pipeline. |
| 2 | Es wird zunächst mit **vier Kartentemplates** gearbeitet, die als Vorlage dienen, auf die Foto und Daten gelegt werden. | Neuer Abschnitt 3: gemeinsames Slot-Schema für alle vier, klarer Zuständigkeitsschnitt zwischen KI und deterministischem Renderer. |
| 3 | **Wir** übernehmen die Kommunikation mit dem Kunden. | Neues Kommunikationsmodul (Abschnitt 7). Erfordert einen Deep-Link je Spieler in die Upload-Maske des Partners. |
| 4 | Auf der **Kartenrückseite steht ein QR-Code**, der die Karte als digitale Datei anzeigt — dauerhaft verfügbar. | Neuer Abschnitt 6: eigener, langlebiger Auflösungsdienst. Der gedruckte Token ist unveränderlich, der Karteninhalt nicht. |
| 5 | Die **Ausgangsbilder des Kunden** werden nach gesetzlicher Frist gelöscht. | Getrennte Aufbewahrungsklassen je Asset-Typ (Abschnitt 6.4). Rohbild kurz, Druckartefakt mittel, digitale Karte dauerhaft. |
| 6 | Die **Einwilligung liegt bei Sticker-König**. | Wir führen kein eigenes Einwilligungsregister, sondern eine eingefrorene Assertion plus Revalidierung unmittelbar vor dem Transfer (Abschnitt 7.3). |
| 7 | Mindestlosgröße und Lieferzeit sind noch offen. | Alle betroffenen Größen laufen als Platzhalter über eine zentrale Konfigurationstabelle (Abschnitt 9), nicht als Konstanten im Code. |

### 0.2 Verbleibende Annahmen

| # | Annahme |
|---|---|
| A1 | Sticker-König stellt eine HTTP-API bereit; wir konsumieren Stammdaten, Einwilligungs-Assertion und Fotos per Pull und/oder Webhook. |
| A2 | Ein erheblicher Teil der abgebildeten Personen sind Minderjährige → Einwilligung durch Erziehungsberechtigte. |
| A3 | Die Druckerei nimmt druckfertige PDF/X-Dateien plus maschinenlesbares Manifest entgegen. |
| A4 | Das bestehende Etsy-Backend bleibt zunächst unverändert in Betrieb. |
| A5 | Zielvolumen: 1.000–5.000 Karten/Tag im Peak, ausgeprägte Saisonspitzen. |
| A6 | Der Partner kann in seiner Upload-Maske eine von uns gelieferte Erklärstrecke und Sofortprüfung einbinden (Abschnitt 2.3 beschreibt auch den Weg, falls nicht). |

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
(Verein/Trainer) ≠ betroffene Person (Spieler bzw. Erziehungsberechtigte). Mit Rev. 2 kommt hinzu,
dass die Einwilligung bei einem *dritten* System liegt. Das ist kein zusätzliches Feld, sondern ein
anderes Schema — und der Teil mit dem Haftungsrisiko.

**(c) Anderes Lastprofil.** Etsy: konstanter Tropf, 1–3 Artikel, Sekunden pro Bestellung.
Team: Burst von 60 Renderings plus 60 Bildprüfungen in einem Schub, CPU/GPU-lastig, Minuten.
Im gemeinsamen Worker-Pool blockiert ein Teamauftrag den laufenden Shop.

**(d) Andere Fehlerkosten und Deploy-Kadenz.** Ein Etsy-Fehler kostet eine Erstattung. Ein
Team-Fehler betrifft 60 Personen, einen Verein, eine Deadline und einen bereits gebuchten
Druckbogen. Mit dem QR-Code kommt eine dritte Kategorie hinzu: ein Fehler, der **dauerhaft** ist,
weil der Code physisch gedruckt wurde.

### 1.2 Was wir bewusst *nicht* bauen

Kein Microservice-Zoo. Empfehlung: **ein eigenständiger Dienst, intern modular geschnitten, mit
getrennten Worker-Pools.**

- 1 API-Service (Ingest, Admin-API, Webhooks, Photo-Precheck)
- 1 Datenbank (PostgreSQL) als Source of Truth, inklusive transaktionaler Job-Queue
- N Worker-Pools nach Ressourcenklasse: `assets`, `render`, `qa`, `transfer`, `notify`
- Object Storage (S3-kompatibel, EU-Region) für Assets und Artefakte

**Eine begründete Ausnahme:** Der Auflösungsdienst für die QR-Codes (Abschnitt 6) wird als
*separater, minimaler* Dienst betrieben. Nicht aus Skalierungsgründen, sondern wegen der Lebensdauer:
Er muss noch laufen, wenn die Engine dreimal umgebaut wurde. Ein zustandsarmer Dienst mit einer
Tabelle und einem CDN davor überlebt Architekturwechsel; ein Endpunkt tief in der Engine nicht.

Warum sonst *eine* Datenbank statt Datenbank-pro-Service: Die zentrale Invariante — „keine Karte in
den Druck ohne gültige Einwilligung und bestandene QA" — will man in einer Transaktion und in
DB-Constraints erzwingen, nicht über Eventual Consistency.

### 1.3 Migrationspfad (Strangler Fig)

1. **Phase 1** — Die Engine übernimmt B2B-Teamaufträge. Das Etsy-Backend bleibt unberührt.
2. **Phase 2** — Die Engine exponiert Render-, QA- und Print-Pipeline als interne API. Das
   Etsy-Backend wird deren Client; eine Etsy-Bestellung ist dann eine Teambestellung mit einer Zeile.
3. **Phase 3** — Das Legacy-Backend schrumpft auf Marktplatz-Anbindung (Etsy-Sync, Payouts).

### 1.4 Anti-Corruption Layer zum Partner

Das Fremdschema wird niemals ins Kerndomänenmodell durchgereicht. Das `partner-gateway`-Modul leistet:

- Übersetzung Fremdschema → eigenes Schema, versioniert (`payload_version`)
- Idempotenz über `(partner_id, external_ref, payload_version)` — Webhook-Retries erzeugen keine Duplikate
- Rohdaten-Archiv: jede eingehende Payload roh plus Hash (Beweislage, Replay bei Mapping-Fehlern)
- Reconciliation: nächtlicher Soll-Ist-Abgleich. Webhooks gehen verloren, immer.
- Contract Tests gegen eine Partner-Sandbox in der CI

Mit Rev. 2 kommen drei Vertragsgegenstände hinzu, die über die Datenübertragung hinausgehen:
die **Einwilligungs-Assertion** (7.3), der **Widerrufs-Webhook** (7.3) und der **Deep-Link je
Spieler** in die Upload-Maske (7.2).

### 1.5 Zwei nicht verhandelbare Bauprinzipien

**Immutable Snapshot bei Auftragsannahme.** Mit der Annahme werden die Daten eingefroren
(`order_snapshot` inklusive Hash). Der Partner darf Spielerdaten danach ändern — was wir gedruckt
haben, bleibt dokumentiert.

**Content-Addressed Artefakte.**

```
fingerprint = hash(snapshot_row + design_version + asset_version + engine_version)
```

Deterministisch, deduplizierbar, gefahrlos wiederholbar; die QA-Freigabe klebt am Hash statt am
Zeitpunkt. Lädt ein Kunde ein besseres Foto nach, ändert sich `asset_version` → neuer Fingerprint →
die alte Freigabe verfällt automatisch. Genau das braucht man bei Laienfotos, weil Nachbesserungen
der Normalfall sind und nicht die Ausnahme.

---

## 2. Fotoqualität an der Quelle

### 2.1 Das eigentliche Problem

Der Upload passiert in fremder Software. Die Fehler entstehen dort — die Kosten entstehen bei uns.
Wenn ein untaugliches Foto erst in unserer Pipeline auffällt, ist der Kunde längst weg, und die
Korrektur ist eine Nachrichtenrunde über Tage statt eine Korrektur in Sekunden.

| Ort der Prüfung | Korrekturdauer | Kosten je Fall |
|---|---|---|
| Im Upload-Dialog beim Partner | Sekunden | ~0 |
| In unserer Pipeline, Nachforderung per Nachricht | 2–10 Tage | Nachricht, Wartezeit, Terminrisiko, ggf. Wellen-Split |
| Erst in der manuellen Retusche | Stunden Arbeitszeit | Personalkosten je Karte |

Daraus folgt die zentrale Empfehlung dieses Abschnitts: **Die Prüfung gehört in den Moment des
Uploads, auch wenn dieser Moment nicht uns gehört.**

Erwartungswerte als Planungsgrundlage (Erfahrungswerte, im Betrieb zu messen):

| Szenario | Anteil problematischer Fotos |
|---|---|
| Handyfoto ohne jede Führung | 15–30 % |
| Mit Erklärstrecke, ohne Sofortprüfung | 8–15 % |
| Mit Erklärstrecke **und** Sofortprüfung im Upload-Dialog | 3–8 % |

Der Unterschied zwischen der ersten und der letzten Zeile ist bei 1.000 Karten der Unterschied
zwischen etwa zwei und etwa zehn Stunden Handarbeit — pro Tag.

### 2.2 `photo_spec` — eine Quelle, drei Ausspielungen

Die Fotoanforderungen werden **einmal** als versionierte, maschinenlesbare Spezifikation definiert
und daraus dreifach ausgespielt:

1. **Die Erklärstrecke** (Text, Bildbeispiele, Animation) — was der Kunde sieht
2. **Die Sofortprüfung** im Upload-Dialog — was der Kunde direkt zurückgemeldet bekommt
3. **Gate 0** in unserer Pipeline — was verbindlich entscheidet

Ohne diese gemeinsame Quelle laufen die drei garantiert auseinander: Das Video sagt „ruhiger
Hintergrund", der Client prüft es nicht, und unser Gate lehnt ab. Der Kunde hat dann alles richtig
gemacht und ärgert sich trotzdem.

Inhalt von `photo_spec` (Auszug, Werte sind Platzhalter bis zur Freigabe des ersten Templates):

| Regel | Zielwert | Prüfbar durch |
|---|---|---|
| Mindestauflösung | 1200 × 1600 px für 300 dpi im Bild-Slot | Client + Server |
| Ausschnitt | Oberkörper, Kopfoberkante bis etwa Brustmitte | Landmarks |
| Kopfhöhe im Bild | 35–55 % der Bildhöhe | Landmarks |
| Kopfposition | Augenlinie im oberen Drittel, mittig ±10 % | Landmarks |
| Personen im Bild | genau eine | Gesichtserkennung |
| Hintergrund | ruhig, kontrastarm zum Motiv, keine Muster | Kantendichte im Randbereich |
| Schärfe | Laplace-Varianz über Schwelle | Client + Server |
| Belichtung | keine ausgefressenen Lichter/Tiefen im Gesicht | Histogramm |
| Verdeckungen | keine Mütze, Kapuze, verspiegelte Brille | Vision-Modell |
| Format | JPEG/PNG/HEIC, EXIF-Rotation angewandt | Server |
| Pose | frontal bis leicht angewinkelt, Schultern im Bild | Landmarks |

Zwei Fallen aus der Praxis, die hier explizit hingehören: **HEIC** (iPhone-Standardformat, viele
Bildbibliotheken können es nicht) und **nicht angewandte EXIF-Rotation** (das Bild liegt quer, alle
Landmark-Prüfungen schlagen fehl). Beides wird serverseitig normalisiert, bevor irgendeine Prüfung
läuft.

### 2.3 Die Erklärstrecke — und wo sie läuft

Der Kunde soll erfahren: typische Spielerpose, richtiger Schnitt, ruhiger Hintergrund,
Oberkörperfoto, gute Qualität. Drei Ausbaustufen, aufsteigend nach Wirkung und Aufwand:

**Stufe 1 — Erklärstrecke, vom Partner eingebaut.** Wir liefern Skript, Beispielbilder und eine
kurze Animation; der Partner bindet sie in seine Upload-Maske ein.
Empfehlung zur Form: **eine kurze, tonlose Schleifenanimation (8–12 Sekunden) schlägt ein Video.**
Ein Video wird weggeklickt; eine Animation, die neben dem Upload-Feld läuft, wird gesehen.
Am wirksamsten ist eine **Gegenüberstellung richtig/falsch** mit denselben vier Fehlern, die in
unseren Daten am häufigsten sind — die Auswahl wird nach den ersten Betriebswochen aus den echten
Ablehnungsgründen nachgeschärft. Die Animation muss auf dem Telefon funktionieren, denn dort wird
sie stattfinden.

**Stufe 2 — Sofortprüfung über eine Precheck-API (empfohlen).** Wir stellen einen Endpunkt bereit:
Bild rein, in wenigen Sekunden ein Urteil zurück — Qualitätsklasse, Begründungscodes in Klartext
und eine Vorschau der automatischen Freistellung. Die Partner-App zeigt das im Upload-Dialog an.
Der Kunde sieht „Der Hintergrund ist zu unruhig — bitte stell dich vor eine glatte Wand" und
korrigiert sofort. Für uns ist das ein kleiner, zustandsloser Dienst; der Hebel auf die
Retusche-Quote ist der größte im ganzen System.

**Stufe 3 — Einbettbares Aufnahme-Widget.** Ein iframe/JS-Baustein mit Kameraansicht und
**Schablone**: Silhouette für Kopfhöhe und Schulterlinie, live eingeblendet. Damit wird die richtige
Pose und der richtige Schnitt nicht erklärt, sondern erzwungen. Der Partner baut eine Zeile Code
ein, wir kontrollieren die Qualität am Entstehungsort.

Fällt Stufe 2 und 3 aus, bleibt die Architektur unverändert — nur die Nachforderungsquote steigt,
und die Kommunikationsleiter aus Abschnitt 7 wird der Hauptlastpfad. Das ist der Grund, warum sie
in Rev. 2 so ausführlich modelliert ist.

### 2.4 Qualitätsklassen statt Pass/Fail

Ein binäres Urteil ist bei Laienfotos falsch: Es lehnt zu viel ab und verärgert Vereine, oder es
lässt zu viel durch und druckt Matsch. Stattdessen drei Klassen:

| Klasse | Bedeutung | Behandlung |
|---|---|---|
| **A** | Direkt verwendbar | Geht ohne Zwischenschritt in die Freistellung |
| **B** | Mit automatischer Aufbereitung verwendbar | Aufhellung, Rauschminderung, moderates Upscaling, Farbangleichung an die Template-Farbwelt — protokolliert als eigene `asset_version` |
| **C** | Nicht verwendbar | Blocker `PHOTO_REJECTED` mit Begründungscode → Nachforderung über Abschnitt 7 |

Die Klassengrenzen sind Konfigurationswerte (Abschnitt 9) und werden im Betrieb nachjustiert. Im
Cockpit wird die Verteilung A/B/C je Verein und je Woche sichtbar gemacht — kippt sie, stimmt etwas
an der Erklärstrecke oder es ist ein neuer Handy-Jahrgang mit aggressiven Beauty-Filtern unterwegs.

**Wichtig:** Klasse B verändert das Bild. Jede Aufbereitung erzeugt eine neue `asset_version` mit
`processing_version`, das Original bleibt unangetastet, und der Fingerprint ändert sich — die
Kette bleibt lückenlos rekonstruierbar.

---

## 3. Die vier Templates und der Zuständigkeitsschnitt der KI

### 3.1 Eine Anmerkung zur KI-gestützten Komposition

Der Wunsch lautet, die vier Templates als Vorlage zu verwenden, auf die eine KI Spielerfoto und
Daten legt. Fachlich ist das genau richtig — beim *Wie* ist eine Unterscheidung entscheidend:

Ein generatives Modell, das die fertige Druckdatei erzeugt, ist für Druckproduktion die falsche
Wahl. Es ist nicht deterministisch (dieselbe Eingabe liefert zweimal ein anderes Ergebnis, womit der
Fingerprint und damit jeder reproduzierbare Nachdruck wertlos wird), es kann Textposition und
Schriftschnitt nicht garantieren, und es erfindet bei Namen zuverlässig Buchstaben. Man würde die
QA-Kaskade aus Abschnitt 4 im Wesentlichen bauen, um die Fehler des Generators zu fangen.

Der Vorschlag erfüllt denselben Zweck mit einem sauberen Schnitt in **drei Schichten**. Die KI macht
genau den Teil, den nur sie kann — und der exakte Teil bleibt exakt.

### 3.2 Schicht A — KI am Motiv

Eingabe: das Kundenfoto. Ausgabe: ein normalisiertes Freisteller-Asset mit **bekannter Geometrie**.

- Segmentierung / Freistellung des Motivs vom Hintergrund
- Landmark-Erkennung: Augenlinie, Kopfoberkante, Kinn, Schulterlinie
- Ableitung der Ankergeometrie (Kopfhöhe, Augenlinienhöhe, horizontale Mitte)
- Aufbereitung bei Klasse B: Belichtung, Rauschen, Upscaling, Farbangleichung
- Ausgabe: PNG mit Alphakanal plus ein Geometrie-Datensatz

Die Schicht liefert **keine Karte**, sondern ein sauberes, vermessenes Motiv.

### 3.3 Schicht B — Deterministische Komposition

Das Template ist kein Bild, auf das etwas „gelegt" wird, sondern ein **parametrisiertes Layout mit
Slots**:

- **Bild-Slot** mit Ankerregel statt festem Rechteck: „Augenlinie auf 38 % der Slot-Höhe, Kopfhöhe
  auf 46 % der Slot-Höhe, horizontal zentriert". Der Renderer berechnet Skalierung und Versatz aus
  der Geometrie aus Schicht A.
- **Text-Slots** mit Schrift, Größe, Autofit-Grenzen, Ausrichtung, Farbe
- **Grafikebenen** des Templates (Rahmen, Farbwelt, Verlauf, Veredelungsbereiche)
- **Vereinskontext** (Logo, Sponsor, Saison) aus `team_design_context`
- **QR-Slot** auf der Rückseite (Abschnitt 6)
- Beschnitt, Sicherheitszonen, Farbprofil

Die Ankerregel ist bei Laienfotos der entscheidende Punkt: Sie ist der Grund, warum 60
unterschiedlich geschnittene Handyfotos am Ende wie ein **Set** aussehen und nicht wie 60 Zufälle.
Ohne sie sitzt jeder Kopf woanders.

Diese Schicht ist vollständig deterministisch, exakt und hash-stabil.

### 3.4 Schicht C — KI als Prüfer

Das Vision-Modell schaut auf das Ergebnis, es erzeugt es nicht (Gate 3c in Abschnitt 4).

### 3.5 Die vier Templates

Vier `design_family`-Einträge, die konkrete Benennung ist noch offen; naheliegend sind Feldspieler,
Torwart, Trainer/Gold und eine Mannschaftskarte. Jede Familie hat versionierte, unveränderliche
`design_version`-Einträge.

**Die wichtigste Regel für den Start: Alle vier Templates teilen dasselbe Slot-Schema.** Gleiche
Feldnamen, gleiche Ankerregeln, gleiche Textfelder — es unterscheiden sich nur Grafik, Farbwelt und
gegebenenfalls die Druckspezifikation.

Der Gewinn daraus ist erheblich:

- **ein** Renderer statt vier Sonderfälle
- **ein** QA-Regelsatz, weil die Prüfregionen bei allen vier an derselben Stelle liegen
- **ein** Golden Set, das alle vier gleichzeitig absichert
- ein fünftes Template kostet dann eine Grafikdatei, keinen Code

Abweichungen sind später möglich, sollten aber eine bewusste Entscheidung sein und nicht durch
Wildwuchs entstehen. Jede Template-Version durchläuft vor dem Vollautomatikbetrieb den Canary aus
Abschnitt 8.

---

## 4. Automatisierte Qualitätskontrolle

### 4.1 Zwei Vorbemerkungen

**Zur 100-%-Automatisierung.** Das Ziel sollte lauten: 100 % automatisierter Happy Path plus eine
deterministische Quarantäne-Spur. Ein System ohne menschliche Bahn hat nicht 100 % Automatisierung —
es liefert 100 % der Fehler aus. Die Steuerungsgröße ist die **Auto-Pass-Rate**, nicht die
Abwesenheit einer Review-Queue.

**Der Prüfer darf nicht der Renderer sein.** Die QA arbeitet ausschließlich auf dem fertigen PDF,
rasterisiert zu Pixeln, und vergleicht gegen den Datenbank-Snapshot — zwei unabhängige Pfade.

### 4.2 Die Gate-Kaskade

Billig und deterministisch zuerst, teuer und probabilistisch zuletzt.

#### Gate −1 — Sofortprüfung im Upload-Dialog (beim Partner)

Neu in Rev. 2. Läuft auf fremdem Boden, ist unverbindlich und wird serverseitig vollständig
wiederholt — aber sie fängt den Großteil der Fälle dort ab, wo die Korrektur Sekunden kostet.
Siehe Abschnitt 2.3.

#### Gate 0 — Eingangsvalidierung (verbindlich, vor dem Rendering)

- Normalisierung zuerst: HEIC-Konvertierung, EXIF-Rotation anwenden, Farbraum vereinheitlichen
- Alle Regeln aus `photo_spec` — verbindlich, unabhängig vom Ergebnis der Sofortprüfung
- Einstufung in Qualitätsklasse A / B / C (Abschnitt 2.4)
- Einwilligungs-Assertion vorhanden, gültig, richtige Textversion → **Hard Gate**
- Pflichtfelder, Zeichensatz, Namenslänge gegen die Layoutgrenzen des gewählten Templates
- **Die Zuordnung Foto → Spieler stammt ausschließlich aus der Partner-ID, niemals aus dem
  Dateinamen.** Bei Laienfotos, die reihenweise `IMG_2831.jpg` heißen, ist das nicht
  Best Practice, sondern Voraussetzung.

#### Gate 1 — Render-Manifest (deterministisch, im Renderer)

Der Renderer erzeugt neben dem PDF ein Manifest: welcher String in welche Box, welcher Asset-Hash in
welchen Slot, Schriftgrößen, berechnete Textbreiten, die angewandte Ankertransformation, die
QR-Geometrie.

- Textüberlauf beziehungsweise Autofit-Verkleinerung über Grenzwert
- Fehlende Glyphen (`.notdef`) — kritisch bei Namen wie „Đorđević"
- Effektive Bildauflösung am Platzierungsort ≥ 300 dpi **nach** der Ankerskalierung — bei
  Laienfotos der häufigste stille Fehler, weil ein knappes Foto durch das Heranskalieren des Kopfes
  unter die Grenze rutscht
- QR-Modulgröße, Ruhezone und Kontrast innerhalb der Spezifikation
- Alle Pflicht-Slots belegt

#### Gate 2 — Technischer Preflight (auf dem PDF)

PDF/X-Konformität, Schrifteinbettung, CMYK/ICC-Profil, Beschnitt- und Endformatboxen, Anschnitt,
Seitenzahl, Überdrucken. Standardwerkzeuge (Ghostscript, veraPDF), kein Eigenbau.

#### Gate 3 — Perzeptive Verifikation

PDF bei 300 dpi rastern, dann vier Prüfungen:

**3a — Regionsbezogenes OCR.** Aus dem Manifest ist bekannt, *wo* der Name steht; es wird nur dieser
Ausschnitt geprüft. Vergleich gegen den DB-Wert nach Unicode-Normalisierung (NFC), Case-Folding und
Diakritika-Behandlung. Exakte Übereinstimmung = Pass; Levenshtein ≤ 1 bei Namen über sechs Zeichen =
Pass mit Warnung; sonst Fail.

**3b — Bildidentität statt Gesichtserkennung.** Gerenderten Fotobereich ausschneiden, die
Ankertransformation aus dem Manifest zurückrechnen und gegen das Quell-Asset vergleichen —
perzeptueller Hash, Feature-Matching und SSIM.

> Bewusste Entscheidung: Das ist *keine* biometrische Gesichtserkennung. Gesichts-Embeddings gegen
> eine Personendatenbank wären biometrische Daten nach Art. 9 DSGVO — bei Minderjährigen ein Risiko,
> das man nicht eingeht. Der Bildvergleich Quelle ↔ Rendering ist eine technische Integritätsprüfung.

**3c — Vision-Modell als Eskalation.** Für holistische Fehler: überlappende Elemente, verrutschte
Freistellungskante, Halo um den Kopf, Artefakte in der Maske, abgeschnittene Schulter. Bei
Laienfotos die wichtigste Auffangstufe, weil die Freistellung häufiger scheitert als bei
Studioaufnahmen. Aufruf bei niedriger Konfidenz aus 3a/3b, bei jeder neuen Design-Version, bei
jedem Klasse-B-Asset und als Stichprobe.

**3d — QR-Rücklesung.** Neu in Rev. 2 und nicht verhandelbar: Der QR-Code wird aus dem gerasterten
PDF **wieder ausgelesen** und der dekodierte Token gegen den erwarteten Token geprüft. Ein QR-Code,
der im Layout gut aussieht, aber wegen Modulgröße, Kontrast oder Überdruckung nicht dekodierbar ist,
fällt sonst erst auf, wenn 60 gedruckte Karten beim Verein liegen — und ist dann unreparierbar.

#### Gate 4 — Batch-übergreifende Prüfungen

- Kartenanzahl gleich Summe der bestellten Mengen
- Keine Person mit zwei unterschiedlichen Fotos im selben Batch
- Keine doppelte `card_item_id`, **keine doppelte QR-Token im Batch**
- Rückennummern innerhalb des Teams eindeutig (Warnung, kein Fail)
- Nutzenplan: Bogenposition ↔ Karten-ID konsistent

#### Gate 5 — Quarantäne

Side-by-Side-Ansicht (Datensatz links, Rendering rechts, beanstandete Region markiert), drei
Aktionen: Freigeben, Neu rendern, Blockieren. Jede Entscheidung protokolliert.

### 4.3 Die Freigabe-Verriegelung

Der Transfer an die Druckerei prüft in derselben Transaktion:

```
qa_verdict.decision        = PASS
qa_verdict.fingerprint     = card_item.artifact_fingerprint
offene HARD-Blocker        = 0
consent_assertion_valid    = true   (frisch revalidiert, siehe 7.3)
card_twin.public_token     = im PDF dekodierter Token
```

### 4.4 Golden Set

Ein fixes Testteam mit absichtlich schwierigen Fällen läuft bei jeder Änderung an Template, Renderer
oder QA-Schwellen automatisch durch die komplette Pipeline, mit Pixelvergleich gegen freigegebene
Referenzbilder.

Für Rev. 2 wird das Golden Set um die realistischen Laienfoto-Fehlerbilder erweitert: Gegenlicht,
Bewegungsunschärfe, unruhiger Hintergrund, Ganzkörperaufnahme, zweite Person im Bild, Mütze,
verspiegelte Brille, Hochformat/Querformat, HEIC mit EXIF-Rotation, starker Beauty-Filter, sowie
je ein Fall pro Template und ein Fall mit maximal langem Namen.

---

## 5. Datenmodell und Edge Cases

### 5.1 Die zentrale Modellierungsentscheidung

**Kaufmännische Absicht und Produktionseinheit werden getrennt.**

- `order_line` = *was wurde bestellt* — Person + Design + **Menge** + Preis
- `card_item` = *eine physische Karte* — ein Zustand, ein Artefakt, ein Bogenplatz, **ein QR-Token**

Zwei Regeln folgen daraus:

1. **Menge lebt auf der Zeile, Zustand lebt auf dem Item.** Ein blockierter Spieler blockiert
   niemals das Rendering der anderen 59.
2. **Der Status der Teambestellung wird abgeleitet, nie gepflegt.**

### 5.2 Kernentitäten

| Entität | Zweck | Wesentliche Felder |
|---|---|---|
| `partner` | Mandant | `id`, `name`, `api_config`, `deeplink_template` |
| `club` / `team` | Verein, Team | `season`, `sport`, `age_group` |
| `person` | Betroffene Person | `role`, `is_minor`, `external_ref` |
| `ordering_contact` | Besteller, Rechnungsempfänger | getrennt von `person` |
| `consent_assertion` | **Eingefrorene Aussage** über die beim Partner liegende Einwilligung | `person_id`, `partner_consent_id`, `text_version`, `granted_at`, `subject_type`, `asserted_at`, `assertion_hash`, `revoked_at` |
| `media_asset` | Unveränderliches Asset | `content_hash`, `origin`, `person_id`, `parent_asset_id`, `processing_version`, `quality_class`, `retention_class`, `landmarks` |
| `photo_spec` | Versionierte Fotoanforderungen | `version`, `rules`, `thresholds`, `published_at` |
| `photo_assessment` | Ergebnis einer Fotoprüfung | `asset_id`, `spec_version`, `quality_class`, `reason_codes`, `source` (precheck / gate0) |
| `design_family` / `design_version` | Die vier Templates, versioniert | `slot_schema_id`, `print_spec_id`, `assets` |
| `slot_schema` | Gemeinsames Slot-Schema aller Templates | `image_slot_anchors`, `text_slots`, `qr_slot` |
| `team_design_context` | Gemeinsame Klammer eines Sets | `club_logo`, `sponsor`, `season`, `palette` |
| `team_order` | Kaufmännische Klammer | `fulfillment_policy`, `shipment_policy`, `hold_until`, `snapshot_hash`, `derived_status` |
| `order_line` | Bestellte Position | `person_id`, `design_version_id`, `quantity`, `line_type`, `unit_price`, `recipient_group_key` |
| `card_item` | Eine physische Karte | `order_line_id`, `copy_index`, `state`, `artifact_fingerprint`, `card_twin_id`, `wave_id`, `print_batch_id`, `sheet_position` |
| `render_artifact` | Content-addressed Renderergebnis | `fingerprint` (PK), `pdf_ref`, `preview_ref`, `manifest`, `engine_version` |
| `qa_verdict` | Prüfergebnis je Artefakt | `fingerprint`, `gate_results`, `decision`, `confidence`, `decided_by` |
| `blocker` | Offenes Hindernis je Item | `reason`, `severity`, `owner`, `opened_at`, `resolved_at`, `remediation_attempts` |
| `card_twin` | **Die digitale Karte hinter dem QR-Code** | `public_token` (stabil, gedruckt), `card_item_id`, `published_fingerprint`, `published_at`, `revoked_at`, `availability_class` |
| `message` | Ausgehende Kommunikation | `recipient_ref`, `channel`, `template`, `sent_at`, `delivery_status`, `bounce_reason` |
| `production_wave` | Produktionswelle | `team_order_id`, `sequence`, `released_at` |
| `print_batch` | Was an die Druckerei geht | `print_spec_id`, `external_job_ref`, `transferred_at`, `acknowledged_at`, `manifest_hash` |
| `shipment` | Lieferung an den Verein | `consolidates[]`, `carrier_ref` |
| `system_config` | Betriebsparameter, inkl. Platzhaltern | `key`, `value`, `unit`, `is_placeholder`, `changed_by`, `changed_at` |
| `domain_event` | Append-only Audit-Trail | `correlation_id`, `subject`, `type`, `payload`, `at` |

### 5.3 Fall 1 — Ein Spieler möchte zwei oder drei Karten von sich

Gelöst über `order_line.quantity` plus Expansion in `card_item`. Drei Karten sind eine Zeile mit
`quantity = 3` und drei Items mit `copy_index` 1 bis 3.

- **Nur ein `render_artifact`** — identischer Fingerprint, Rendering und QA laufen einmal.
- `line_type` unterscheidet Grundpaket, Zusatzkarte und Upgrade — für Staffelpreise und Rechnung.
- `recipient_group_key` — Zusatzkarten gehören in das Tütchen *dieses* Spielers.

**Neu in Rev. 2 und wichtig:** Die drei Kopien teilen sich das Rendering, aber sie brauchen eine
Entscheidung beim QR-Code. Zwei Optionen:

| Option | Wirkung | Empfehlung |
|---|---|---|
| **Ein Token für alle Kopien** | Alle drei Karten zeigen dieselbe digitale Karte. Ein Rendering, ein Artefakt, geringste Kosten. | **Standard.** Fachlich ist es dieselbe Karte, dreimal gedruckt. |
| Ein Token je Kopie | Jede physische Karte ist einzeln identifizierbar (Voraussetzung für Echtheitsnachweis oder eine spätere Tauschfunktion). | Nur wenn das Produkt es verlangt — es kostet drei Renderings statt einem. |

Da die Entscheidung **gedruckt** wird, sollte sie vor dem ersten Auftrag fallen und nicht später.
Der Standard bleibt „ein Token je Karteninhalt"; für limitierte Editionen kann eine `design_family`
auf „ein Token je Kopie" gestellt werden.

### 5.4 Fall 2 — Unterschiedliche Designs innerhalb einer Bestellung

**Das Design hängt an der Zeile, nicht an der Bestellung.** `order_line.design_version_id` gewinnt
immer gegen den Vorgabewert der Bestellung. Ein Spieler kann damit zwei Standardkarten *und* eine
Gold-Karte haben — zwei Zeilen, dieselbe Person.

Die Zuordnung läuft über Regeln, aber **materialisiert**: `person.role` kommt aus der Partner-API,
eine `design_rule` am Auftrag übersetzt sie in eine `design_version`. Die Auswertung erfolgt einmal
bei Auftragsannahme, das Ergebnis wird in die Zeile geschrieben und als `domain_event` protokolliert.
Niemals lazy beim Rendern auflösen — Regeln ändern sich, und es muss reproduzierbar bleiben, warum
diese Karte dieses Design bekam.

Zwei Aspekte:

**a — Team-Kontext gegen Karten-Design.** Vereinslogo, Sponsor, Saison und Farbwelt liegen in
`team_design_context`, den alle vier Templates konsumieren. Sonst wirkt ein gemischtes Set nicht mehr
wie ein Set.

**b — Nicht jedes Design darf in denselben Druckbogen.** `design_version.print_spec_id` steuert die
Batch-Bildung, die **nach Druckspezifikation** gruppiert, nicht nach Bestellung:

> Eine Teambestellung → *n* Druck-Batches → 1 konsolidierte Lieferung

Nebeneffekt und Margenhebel: Batches lassen sich bestellungsübergreifend bündeln — zwölf
Gold-Trainerkarten aus zwölf Vereinen laufen auf *einem* Bogen. Bei einer noch unbekannten
Mindestlosgröße (Abschnitt 9) ist das der Mechanismus, der die Wirtschaftlichkeit rettet.

### 5.5 Fall 3 — Foto fehlt oder Freistellung schlägt fehl

Eine Policy-Frage, also ein Feld im Modell und kein `if` im Code.

#### Blocker-Katalog

| Grund | Schwere | Verantwortlich | Automatische Behandlung |
|---|---|---|---|
| Einwilligungs-Assertion fehlt oder widerrufen | HARD | Partner | keine — Produktion verboten |
| Minderjährig ohne Nachweis | HARD | Partner | keine |
| Revalidierung vor Transfer fehlgeschlagen | HARD | Partner | Transfer bricht ab, Eskalation |
| Foto fehlt | SOFT | Kunde | Nachforderung über Abschnitt 7 |
| Foto Klasse C abgelehnt | SOFT | Kunde | Nachforderung mit Begründungscode |
| Freistellung fehlgeschlagen | SOFT | intern | Retry-Leiter, dann Retusche-Queue |
| QA-Fail (Text, Bild oder QR) | SOFT | intern | Neu-Rendering, dann Review |
| Stammdaten unvollständig | SOFT | Partner | Nachforderung |
| Kontakt nicht erreichbar (Bounce) | SOFT | Verein | Eskalation an den Trainer, **kein stilles Warten** |

Die letzte Zeile ist neu in Rev. 2 und verdient eine Anmerkung: Ohne Bounce-Behandlung wartet das
System vierzehn Tage auf einen Kunden, dessen Postfach gar nicht existiert — und splittet dann den
Auftrag. Ein Zustellfehler muss sofort zum Trainer eskalieren, nicht die Karenzfrist absitzen.

**HARD-Blocker werden niemals umgangen.**

#### Remediation-Leiter bei Freistellungsfehlern

1. Retry mit alternativen Parametern (anderes Segmentierungsmodell, anderer Schwellwert)
2. Retry mit Hintergrund-Hypothese (einfarbig, Rasen, Halle)
3. Manuelle Retusche-Queue
4. Neues Foto anfordern (Abschnitt 7)

#### Fulfillment-Policy

- `all_or_nothing` — nichts geht in Produktion, bis alle Items grün sind
- `partial_with_hold` — **Standard.** Fertige Items werden gerendert und QA-geprüft, der Transfer
  wartet bis `hold_until`. Nach Fristablauf automatischer Split.
- `partial_ship_immediately` — sofortige Teilproduktion

#### Wellen statt Mutation

Beim Split wird der Auftrag nicht verändert; es entsteht eine `production_wave`. Der `team_order`
bleibt die kaufmännische Wahrheit und steht auf `PARTIALLY_COMPLETE`, bis alle Wellen abgeschlossen
sind.

`shipment_policy = consolidate` mit `max_consolidation_wait` ist der Standard — der Trainer will
*eine* Kiste. `wave_split_cost_threshold` verhindert, dass ein Nachzügler-Batch mit fünf Karten
denselben Rüstaufwand kostet wie einer mit sechzig.

### 5.6 Zustandsautomat `card_item`

```
DRAFT → DATA_VALIDATED → PHOTO_ACCEPTED → ASSET_READY → RENDER_QUEUED → RENDERED
      → QA_PASSED → APPROVED → BATCHED → SENT_TO_PRINT → PRINTED
      → PACKED → SHIPPED → DELIVERED

Nebenzustände:  BLOCKED · QA_FAILED · CANCELLED · REPRINT_REQUESTED
```

`PHOTO_ACCEPTED` ist neu in Rev. 2 und trennt „Stammdaten sind da" von „ein verwendbares Foto ist
da" — bei Laienfotos zwei sehr verschiedene Dinge, die getrennt gemessen werden müssen.

**Die eine Übergangsregel, die alles trägt:** `APPROVED → BATCHED` ist nur zulässig, wenn in
derselben Transaktion alle Bedingungen aus 4.3 gelten. Erzwungen als DB-Constraint, nicht nur in
der Anwendungsschicht.

### 5.7 Zustandsautomat `team_order` (abgeleitet)

```
RECEIVED → VALIDATING → IN_PRODUCTION → PARTIALLY_COMPLETE → COMPLETE → CLOSED
                                     ↘ ON_HOLD    ↘ CANCELLED
```

---

## 6. Die digitale Karte und der QR-Code

### 6.1 Warum das ein eigener Baustein ist

Ein gedruckter QR-Code ist eine Zusage, die man nicht zurücknehmen kann. Er muss noch funktionieren,
wenn die Engine dreimal umgebaut, das Storage gewechselt und die Domain umgezogen ist. Deshalb gilt
eine Regel ohne Ausnahme:

> **Im QR-Code steht niemals eine Speicher-URL, sondern immer ein Verweis auf unseren
> Auflösungsdienst.**

`https://karte.<domain>/k/<token>` — der Dienst schlägt den Token nach und entscheidet, was
ausgeliefert wird. Damit bleiben Widerruf, Versionierung, Storage-Wechsel und Domainumzug
beherrschbar, ohne dass je eine Karte nachgedruckt werden muss.

### 6.2 Der stabile Token — die zentrale Unterscheidung

Zwei Kennungen, die man leicht verwechselt und die getrennt bleiben müssen:

| Kennung | Gehört zu | Ändert sich | Wird gedruckt |
|---|---|---|---|
| `card_twin.public_token` | der **Karten-Identität** | **nie** | ja |
| `render_artifact.fingerprint` | dem **Karteninhalt** | bei jeder Änderung | nein |

Wird eine Karte nach einem Tippfehler neu gerendert, ändert sich der Fingerprint — der gedruckte
Token bleibt. Der Auflösungsdienst zeigt dann die korrigierte Fassung, und der QR auf der bereits
gedruckten Karte funktioniert weiter.

Anforderungen an den Token: mindestens 22 Zeichen aus einem kollisionsarmen Alphabet, kryptografisch
zufällig, **nicht** aus IDs abgeleitet und nicht aufzählbar. Er wird bei der Erzeugung des
`card_item` vergeben, also **vor** dem ersten Rendering — sonst kann er nicht in das Artefakt
eingebettet werden.

### 6.3 Was der Auflösungsdienst ausliefert

- Vorder- und Rückseite der Karte in Bildschirmauflösung
- Name, Verein, Saison, Position
- Download der Karte in hoher Auflösung
- Keine Kontaktdaten, keine Suchfunktion, keine Verlinkung auf andere Spieler

Der letzte Punkt ist eine bewusste Datenschutzentscheidung: Eine Karte kann verloren gehen oder
weitergegeben werden. Wer den Code scannt, sieht genau *diese* Karte — nie das Team, nie eine Liste.
Eine Team-Galerie ist denkbar, aber nur mit ausdrücklicher Zustimmung aller Betroffenen und deshalb
nicht Teil der Grundfunktion. Zusätzlich: `noindex`, Rate-Limit auf dem Auflösungsdienst, keine
aufzählbaren Adressen.

**Ausbaupfad, der dem Partner gefallen dürfte:** Der Twin ist bereits die technische Grundlage für
ein digitales Sammelalbum — Sammlung, Tausch, Vervollständigung. Wenn die Token- und
Auflösungsschicht jetzt richtig gebaut wird, kostet dieser Ausbau später keine Migration und keinen
Nachdruck. Wenn sie falsch gebaut wird, ist er nicht mehr möglich.

### 6.4 Aufbewahrung — zwei Uhren, die getrennt laufen

Die Vorgabe lautet: Kundenfotos nach gesetzlicher Frist löschen, die digitale Karte dauerhaft
verfügbar halten. Das ist widerspruchsfrei, sobald man nach Asset-Typ trennt:

| Klasse | Inhalt | Aufbewahrung (Platzhalter) | Begründung |
|---|---|---|---|
| `RAW_UPLOAD` | Originalfoto des Kunden | kurz — 90 Tage nach Auslieferung | Vorgabe; nach der Produktion nicht mehr benötigt |
| `CUTOUT_DERIVATIVE` | Freisteller, aufbereitete Fassung | mittel — 24 Monate | Voraussetzung für Nachdruck ohne neues Foto |
| `PRINT_ARTIFACT` | Druck-PDF | mittel — 24 Monate | Reklamation, Nachdruck, Beweisführung |
| `DIGITAL_TWIN` | Bilddatei hinter dem QR-Code | dauerhaft bis Widerruf | das Produktversprechen |
| `AUDIT_TRAIL` | Ereignisse ohne Bilddaten | dauerhaft | Rechenschaftspflicht |

**Ein Punkt, den man sonst schmerzhaft lernt:** Wird nur das Rohbild aufbewahrt und alles Abgeleitete
verworfen, ist nach Ablauf der Frist kein Nachdruck mehr möglich. Deshalb überlebt das
Freisteller-Derivat das Original — es enthält keine zusätzlichen Informationen, ermöglicht aber den
Nachdruck. Diese Fristen sind Platzhalter und gehören juristisch bestätigt.

### 6.5 Widerruf bei gedruckten Codes

Ein Widerruf der Einwilligung erreicht die gedruckte Karte nicht mehr. Was möglich ist:

1. Der Twin wird auf `revoked` gesetzt; der Auflösungsdienst liefert eine neutrale Hinweisseite
   statt der Karte.
2. Die Bilddatei wird gelöscht, der Token bleibt als Adresse bestehen (er ist selbst kein
   Personenbezug).
3. Nachdrucke werden gesperrt, offene Items storniert.
4. Der Vorgang wird im Audit-Trail dokumentiert.

Dass die physische Karte bestehen bleibt, muss in der Einwilligung des Partners so beschrieben sein.
Das ist ein konkreter Prüfpunkt für den Einwilligungstext (Abschnitt 7.3).

---

## 7. Kommunikation und Einwilligung

### 7.1 Die Systemgrenze

Der Upload passiert beim Partner. Die Kommunikation läuft über uns. Daraus folgt eine Kette, die nur
funktioniert, wenn ein Vertragsdetail stimmt:

```
Wir stellen fest: Foto fehlt oder Klasse C
   → wir senden die Nachricht an Kunde/Erziehungsberechtigten
      → der Link führt in die Upload-Maske des Partners, für genau diesen Spieler
         → Kunde lädt neu hoch
            → Partner-Webhook
               → neue asset_version → neuer Fingerprint → alte Freigabe verfällt → Neuprüfung
```

### 7.2 Der Deep-Link ist ein Vertragsgegenstand

Ohne einen **spielerscharfen Deep-Link** in die Upload-Maske des Partners schicken wir Kunden auf
eine Startseite, auf der sie sich anmelden und ihren Spieler suchen müssen. Die Abbruchquote an
dieser Stelle ist erfahrungsgemäß hoch — und jeder Abbruch ist ein Nachzügler, ein Wellen-Split und
ein verärgerter Trainer.

Der Link muss: genau einen Spieler adressieren, wieder verwendbar sein (nicht nur einmal gültig,
weil Nachbesserungen mehrfach vorkommen), ablaufen können, und darf keine Daten anderer Spieler
offenlegen. Als Feld: `partner.deeplink_template`.

### 7.3 Einwilligung: Assertion statt eigenes Register

Die Einwilligung liegt bei Sticker-König. Wir führen deshalb **kein eigenes Einwilligungsregister**,
sondern drei Mechanismen:

1. **Assertion beim Auftragsannahme-Snapshot.** Wir ziehen die Aussage des Partners — Einwilligung
   liegt vor, Textversion, Zeitpunkt, wer sie erteilt hat, Verweis auf den Beleg — und frieren sie
   samt Hash ein. Das ist unsere Beweislage.
2. **Widerrufs-Webhook.** Der Partner muss uns Widerrufe zustellen. Vertraglich zugesagt, technisch
   idempotent.
3. **Revalidierung unmittelbar vor dem Transfer.** Ein Aufruf je Batch, nicht je Karte. Das ist das
   Sicherheitsnetz für den Fall, dass der Webhook ausfällt — und der Fall tritt ein. Schlägt die
   Revalidierung fehl, bricht der Transfer ab.

Ergänzend der nächtliche Abgleich aus Abschnitt 1.4.

**Prüfpunkte für den Einwilligungstext des Partners.** Der Text muss abdecken, was wir tatsächlich
tun — sonst hat eine Funktion keine Rechtsgrundlage:

- Übermittlung von Foto und Stammdaten an uns als Produktionsdienstleister
- automatisierte Bildverarbeitung (Freistellung, Aufbereitung) und automatisierte Prüfung
- Druckproduktion durch einen Dritten (Druckerei als Auftragsverarbeiter)
- **die dauerhafte Bereitstellung der digitalen Karte über den QR-Code**, einschließlich des
  Hinweises, dass die gedruckte Karte bei Widerruf bestehen bleibt
- Kontaktaufnahme durch uns zur Nachforderung von Fotos

Der vierte und der fünfte Punkt sind die kritischen: Beide sind in Rev. 2 neu hinzugekommen, und
beide betreffen Verarbeitungen, die eine bestehende Einwilligung möglicherweise nicht abdeckt. Die
Rollenverteilung — gemeinsame Verantwortliche nach Art. 26 DSGVO oder Auftragsverarbeitung — sollte
juristisch geklärt werden; die Architektur trägt beide Varianten.

### 7.4 Die Kommunikationsleiter

Alle Fristen sind Platzhalter (Abschnitt 9) und im Cockpit einstellbar.

| Zeitpunkt | Empfänger | Inhalt |
|---|---|---|
| T+0 | Kunde | Einladung mit Deep-Link und Verweis auf die Erklärstrecke |
| T+3 | Kunde | Erinnerung |
| T+7 | Kunde + Trainer in Kopie | Zweite Erinnerung |
| T+10 | Trainer | Eskalation: „diese drei Spieler fehlen noch" |
| T+14 | intern | `hold_until` läuft ab → automatischer Wellen-Split |
| sofort bei Bounce | Trainer | Kontakt nicht erreichbar, bitte Adresse prüfen |

**Ein Trainer-Board-Link** je Auftrag: ein Token, eine Seite, eine Ampel — wer hat hochgeladen, wer
fehlt, wer muss nachbessern. Der Trainer kennt seine Leute und telefoniert schneller hinterher, als
jede automatisierte Nachricht wirkt. Das ist die kostengünstigste Maßnahme im ganzen
Kommunikationsteil.

Betriebliche Pflichten des Moduls: jede Nachricht als `domain_event`, keine Doppelversände,
Abmeldelogik, Ruhezeiten, Bounce-Auswertung, Rate-Limit.

---

## 8. Admin-Cockpit

Drei Flughöhen: Zustand der Fabrik → Arbeitsvorrat → Forensik am Einzelfall.

### 8.1 Statusleiste

| Kachel | Warum sie oben steht |
|---|---|
| **Auto-Pass-Rate (24 h)** | Die wichtigste Qualitätszahl |
| **Fotoqualität A / B / C (7 Tage)** | *Neu in Rev. 2.* Der Frühindikator. Kippt die Verteilung, steigt die Retusche-Last drei Tage später |
| **Karten heute fällig / Kapazität** | Durchsatz gegen Bedarf |
| **Aufträge mit Terminrisiko** | Im Saisongeschäft die geschäftskritischste Zahl |
| **Blockierte Items HARD / SOFT** | HARD ist Rechtsrisiko, SOFT ist Arbeit |
| **Ausstehende Fotos, nach Alter** | *Neu.* Die Hauptquelle für Wellen-Splits |
| **Ältester Job je Pool** | Alter ist das Alarmsignal, nicht Tiefe |
| **Batches unquittiert** | Unquittiert über Schwelle ist ein Vorfall |
| **DLQ-Größe** | Mit Replay-Aktion |
| **Kosten je Karte** | Render, Vision, Storage, Twin-Vorhaltung |

### 8.2 Arbeits-Queues

1. **QA-Review** — Side-by-Side, Freigeben / Neu rendern / Blockieren
2. **Freistellung / Retusche** — bei Laienfotos die volumenstärkste Queue
3. **Ausstehende und abgelehnte Fotos** — nach Team gruppiert, Nachforderung als Ein-Klick-Aktion
4. **Blockierte Items**
5. **Integrationsfehler** (Partner-API, Druckerei) mit Replay
6. **Offene Entscheidungen** — splitten oder warten, mit Kostenfolge daneben
7. **Reklamation / Nachdruck**
8. **Twin-Vorfälle** — *neu:* Widerrufe, nicht dekodierbare QR-Codes aus Reklamationen

### 8.3 Das Team-Board

Eine Teambestellung als Raster aus Kachelvorschauen: Miniatur, Name, Zustandsfarbe, Blocker-Symbol.
Ein Blick genügt. Klick auf eine Kachel öffnet die vollständige Karten-Historie — Rohdaten des
Partners, Einwilligungs-Assertion mit Textversion, Asset-Kette vom Original über die Aufbereitung
bis zum Freisteller, Render-Manifest, alle QA-Gate-Ergebnisse mit Messwerten, QR-Token, Batch und
Bogenposition.

### 8.4 Steuerung und Sicherheitsnetz

- **Not-Aus für Transfers** — ab dem Transfer kostet jeder Fehler Papier und Zeit
- **Canary für Design-Versionen** — die ersten *n* Karten einer neuen Template-Version gehen in die
  menschliche Freigabe. Bei vier Templates und einem gemeinsamen Slot-Schema ist das die Stelle, an
  der ein Schema-Fehler auffällt, bevor er alle vier trifft
- **Twin-Widerruf** als eigene, protokollierte Aktion
- **Rate-Limit und Drosselung** je Partner und je Worker-Pool
- **Alarme statt Dashboards** — Auto-Pass-Rate unter Schwelle, Klasse-C-Quote über Schwelle,
  ältester Job über SLA, Batch unquittiert, HARD-Blocker älter als *x*, Auflösungsdienst nicht
  erreichbar, Kosten je Karte über Budget

### 8.5 Durchgängige Korrelation

Eine `correlation_id` von der eingehenden Partner-Payload über Auftrag, Item, Asset-Kette, Artefakt,
QA-Verdikt, Twin-Token bis zum Druckauftrag. Suche im Cockpit nach Spielername, Auftragsnummer,
Batch-ID **oder QR-Token** öffnet dieselbe Kette. Der QR-Token ist dabei der Schlüssel für den
Support: Ein Kunde ruft an und liest den Code von der Rückseite vor.

---

## 9. Konfiguration und Platzhalter

Keiner dieser Werte gehört in den Code. Alle liegen in `system_config`, sind im Cockpit änderbar,
jede Änderung erzeugt ein `domain_event`. Als Platzhalter markierte Werte sind fachlich noch nicht
bestätigt und dürfen keine Vertragszusage begründen.

| Schlüssel | Platzhalterwert | Abhängig von |
|---|---|---|
| `print.min_batch_size` | 250 Karten | **Druckerei — offen** |
| `print.lead_time_days` | 10 Werktage | **Druckerei — offen** |
| `order.promised_lead_time_days` | 15 Werktage | Lieferzeit — offen |
| `order.hold_until_days` | 14 Tage | Lieferzeit — offen |
| `order.max_consolidation_wait_days` | 7 Tage | Lieferzeit — offen |
| `order.wave_split_cost_threshold` | 40 Karten | Mindestlosgröße — offen |
| `comm.reminder_cadence_days` | 3 / 7 / 10 | frei wählbar |
| `photo.min_resolution_px` | 1200 × 1600 | erstes Template |
| `photo.class_b_threshold` | siehe `photo_spec` | Betriebsmessung |
| `photo.class_c_threshold` | siehe `photo_spec` | Betriebsmessung |
| `qa.auto_pass_target` | 99,0 % | Zielvorgabe |
| `qa.ocr_levenshtein_max` | 1 | Betriebsmessung |
| `qa.image_similarity_min` | siehe `photo_spec` | Betriebsmessung |
| `qa.vision_sample_rate` | 2 % | Kostenbudget |
| `retention.raw_upload_days` | 90 nach Auslieferung | **juristisch zu bestätigen** |
| `retention.cutout_months` | 24 | Nachdruckfenster |
| `retention.print_artifact_months` | 24 | Reklamationsfenster |
| `twin.availability_commitment_years` | 10 | **AGB — zu entscheiden** |
| `twin.token_length` | 22 Zeichen | fix |
| `design.template_count` | 4 | gesetzt |

Die vier fett markierten Zeilen sind diejenigen, die eine Zusage gegenüber Vereinen beeinflussen.
Solange sie Platzhalter sind, sollte im Cockpit ein Hinweis stehen und keine automatisierte
Terminzusage an Kunden hinausgehen.

---

## 10. Nächste Schritte

1. **Partner-API-Vertrag fixieren** — Schema, Einwilligungs-Assertion, Widerrufs-Webhook,
   Deep-Link je Spieler, Foto-Übertragung, Idempotenz, Sandbox. Größtes Projektrisiko.
2. **`photo_spec` v1 festlegen** — gemeinsam mit dem ersten Template, weil die Auflösungsgrenze aus
   der Slot-Geometrie folgt.
3. **Slot-Schema für alle vier Templates festlegen** — vor der ersten Grafik, nicht danach.
4. **Druckerei-Schnittstelle fixieren** — Dateiformat, Manifest, Quittung, Nutzenplan,
   Konfektionierung je `recipient_group_key`, Mindestlosgröße, QR-Druckspezifikation
   (Mindestmodulgröße, Kontrast, Veredelung über dem Code vermeiden).
5. **Token- und Auflösungsschicht bauen** — noch vor dem ersten Druck, weil der Token gedruckt wird.
6. **Datenmodell und Zustandsautomaten** als Migration festschreiben, inklusive der Constraints.
7. **Golden Set aufbauen** — mit den realistischen Laienfoto-Fehlerbildern.
8. **Vertikaler Durchstich** — ein echtes Team, 20 Spieler, drei Templates, ein bewusst fehlendes
   Foto, ein bewusst schlechtes Foto, end-to-end bis zur Druckdatei und bis zur gescannten
   digitalen Karte.

### Offene Entscheidungen

- Ein QR-Token je Karteninhalt oder je physischer Kopie (Abschnitt 5.3) — **muss vor dem ersten
  Druck fallen**
- Benennung und Zuschnitt der vier Templates
- Verfügbarkeitszusage für die digitale Karte (AGB)
- Rollenverteilung nach DSGVO zwischen uns und dem Partner
- Mindestlosgröße und Lieferzeit der Druckerei
