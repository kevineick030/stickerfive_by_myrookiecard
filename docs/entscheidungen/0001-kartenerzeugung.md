# Entscheidung 1 · Wie eine Karte entsteht

Stand: 2026-08-25 · Status: entschieden

## Ausgangslage

Auf der bestehenden Website erzeugt ein Werkzeug jede Karte neu: Vorlage,
Kundenfoto und Angaben gehen hinein, ein fertiges Bild kommt heraus. Das
funktioniert bei einzelnen Bestellungen. Für Teambestellungen wirft es drei
Fragen auf, die zusammenhängen:

1. **Kosten.** Ein Team mit 40 Spielern und drei Kopien sind 120 Karten. Wenn
   jede Karte einzeln erzeugt wird, zahlt man 120 Mal. Ein Nachdruck kostet
   noch einmal.
2. **Wiederholbarkeit.** Erzeugt man dieselbe Karte zweimal, kommt zweimal
   etwas leicht anderes heraus. Für einen Nachdruck oder eine Reklamation ist
   das unbrauchbar — die Nachlieferung muss exakt aussehen wie die Erstlieferung.
3. **Verlässlichkeit des Textes.** Ein Bildmodell schreibt Namen nicht zuverlässig
   richtig. Bei „Björn Sjögren" oder „Nuri Şahin" ist das keine Randerscheinung.

Die Alternative — jede Karte von Hand in Canva — ist zuverlässig, skaliert aber
nicht: Eine Saison mit hundert Mannschaften ist Wochen an Handarbeit.

## Entscheidung

**Karten werden zusammengesetzt, nicht erzeugt.**

Drei Schritte, klar getrennt:

| Schritt | Was passiert | Womit | Kosten |
|---|---|---|---|
| A · Freistellen | Spieler vom Hintergrund trennen | Modell, **einmal je Spieler** | einzige bezahlte Stelle |
| B · Zusammensetzen | Vorlage + Freisteller + Text an feste Stellen | eigener Code, deterministisch | Rechenzeit |
| C · Prüfen | Gates 1–5, OCR, QR-Rücklesen | eigener Code + Modell nur als Eskalation | gering |

Was das ändert:

- **Je Spieler ein Freisteller, nicht je Karte.** 40 Spieler × 3 Kopien = 120
  Karten, aber nur 40 bezahlte Schritte. Bei einheitlicher Vorlage teilen sich
  die Kopien ohnehin eine Vorderseite (`front_fingerprint`).
- **Ein Nachdruck kostet nichts.** Derselbe Fingerabdruck ergibt dieselbe Datei.
- **Der Text stimmt**, weil wir ihn mit einer echten Schriftart setzen und
  hinterher per OCR gegen die Datenbank prüfen.

## Die Vorlage bleibt ein flaches Bild

Die vier Vorlagen wurden mit KI erzeugt; es gibt keine Ebenen und sie lassen
sich nachträglich nicht sauber trennen. Das ist kein Hindernis:

**Auf allen vier Karten liegt der Spieler innerhalb des Rahmens.** Er überlappt
weder Goldrahmen noch Namensschild. Damit genügt eine Reihenfolge:

```
flache Vorlage  →  freigestellter Spieler  →  Text
```

Ein Zerlegen in Hintergrund und Rahmen wäre nur nötig, wenn der Spieler hinter
einem Rahmenteil verschwinden soll. Solange das nicht gewünscht ist, ist der
Aufwand unnötig — die frühere Zerlegefunktion ist wieder entfernt.

**Bedingung:** Das Fotofeld muss so liegen, dass der Spieler den Rahmen nicht
berührt. Das wird einmal je Vorlage eingestellt und gilt dann für jede Karte.

**Bedingung:** Die Vorlage muss leer sein — kein Spieler, kein Name, keine
Trikotnummer, keine Auflagennummer. Alles davon setzen wir und es wechselt je
Karte. Steht es schon in der Grafik, erscheint es doppelt.

## Vorschau: erst freistellen, dann zeigen

Eine nachgezeichnete Vorschau ist ein Versprechen, das die Druckdatei nicht
halten muss. Deshalb:

- **Vor dem Freistellen** sieht die Familie ihr hochgeladenes Foto klein und
  einen Satz dazu, was als Nächstes passiert. Daneben steht das Design mit
  Silhouette statt Foto — echtes Design, ehrliche Lücke.
- **Nach dem Freistellen** sieht sie die Karte. Und zwar dieselbe Datei, die in
  den Druck geht, nur kleiner gerechnet.

Das ist erst möglich, weil Schritt B deterministisch und billig ist: Vorschau
und Druckdatei kommen aus derselben Funktion. Bei Erzeugung je Karte wäre eine
Vorschau entweder teuer oder gelogen.

## Was noch offen ist

- Welches Freistell-Modell (gekaufter Dienst vs. selbst betrieben) — entscheidbar,
  sobald echte Beispielfotos vorliegen.
- Schwellwerte für Qualitätsklassen A/B/C — dito.
- Ob je Vorlage doch eine Fassung mit durchsichtigem Fenster entsteht, falls der
  „Spieler hinter dem Rahmen"-Effekt gewünscht wird. Das ist Designarbeit,
  einmalig je Vorlage.
