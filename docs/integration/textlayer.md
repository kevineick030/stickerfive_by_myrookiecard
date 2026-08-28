# Text raus aus dem Bildmodell

Stand: 2026-08-26 · betrifft `my-rookie-card/supabase/functions/generate-preview/index.ts`

## Warum

Der heutige Prompt laesst Gemini auch den **Text** malen:

```
━━ CARD TEXT FIELDS ━━
Replace placeholder text with:
${felderBlock}
```

Ein Bildmodell malt Buchstaben, es setzt sie nicht. Bei „Björn Sjögren“ oder
„Nuri Şahin“ ist ein Fehler keine Randerscheinung, und bei 60 Karten je Team
faellt er erst beim Auspacken auf. Gemalter Text laesst sich auch nicht per OCR
gegen die Bestellung pruefen — man haette nur ein zweites Modell, das raet.

Das Bild dagegen kann Gemini besser als jedes deterministische Einsetzen: es
gleicht Licht, Kanten und Farbtemperatur des Spielers an die Karte an.

Also: **Bild vom Modell, Text aus der Datenbank.**

## Aenderung im Prompt

Den Block `━━ CARD TEXT FIELDS ━━` ersetzen durch:

```
━━ CARD TEXT FIELDS ━━
• Leave ALL text fields COMPLETELY EMPTY. The name banner, the club bar, the
  jersey number area, the signature plate and the serial number at the bottom
  must contain NO letters and NO digits whatsoever.
• Keep the banners, bars and plates themselves exactly as in IMAGE 1 — only
  their content stays blank.
• Do NOT invent a name, a number or a signature. Blank is correct.
```

`felderBlock` wird damit unbenutzt und kann entfallen. Der Prompt wird kuerzer,
was die Ausbeute erfahrungsgemaess erhoeht: das Modell hat eine Aufgabe weniger.

## Danach: den Satz auflegen

```
POST http://<host>:8081/satz
{
  "design": "DESIGN-1",
  "karte_base64": "<textlose Karte aus Gemini>",
  "spieler": {"name": "Björn Sjögren", "verein": "SV Sparta Lichtenberg",
              "nummer": "17", "id": "<card_item_id>"},
  "auflage": {"kopie": 2, "gesamt": 3},
  "unterschrift_base64": "<optional, PNG mit Transparenz>"
}
```

Antwort:

```
{ "karte_base64": "...", "befunde": [], "gesperrt": false,
  "fingerprint": "5105fd4f…", "design": "Blau Prizm" }
```

- `befunde` leer heisst: der Satz ist sauber. Sonst steht dort im Klartext, was
  klemmt (`TEXT_OVERFLOW`, `TEXT_IN_SAFE_MARGIN`, …) — vor dem Druck, nicht danach.
- `gesperrt` heisst: dieses Design darf nicht in Produktion. Aktuell trifft das
  Premium Gold, weil dort die Auflagennummer eingedruckt ist.
- `fingerprint` ist ueber Kartendaten, Design und Version gebildet. Gleiche
  Eingabe, gleicher Fingerprint, gleiche Datei — die Grundlage fuer Nachdrucke
  und dafuer, dass drei Kopien einer Karte nicht dreimal gerechnet werden.

## Was das loest und was nicht

| | vorher | nachher |
|---|---|---|
| Rechtschreibung des Namens | Modell raet | aus der Datenbank |
| Pruefbar vor dem Druck | nein | ja, per OCR gegen dieselbe Quelle |
| Tippfehler korrigieren | ganze Karte neu generieren | nur den Satz neu legen |
| Bildqualitaet | gut | unveraendert gut |
| Kosten je Karte | eine Generierung | eine Generierung |

Die Kostenfrage loest der Schnitt **nicht** — sie bleibt am Bildmodell haengen.
Er nimmt nur das Risiko heraus, das ein Modell prinzipiell nicht tragen kann.

## Betrieb

```
python3 tools/run_textlayer.py --port 8081
```

Braucht Node mit Playwright-Chromium fuer `tools/render.mjs`. Der Dienst haelt
keinen Zustand: Karte rein, Karte raus, nichts gespeichert.
