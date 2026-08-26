# assets

Hier liegen die Bilddateien, die die Engine braucht. Alles in diesem Ordner ist
**Eingangsmaterial**, kein erzeugtes Ergebnis.

## assets/templates — die Kartenvorlagen

Ein Bild je Design. Flach, ohne Ebenen — mehr wird nicht gebraucht.

Benennung, damit die Werkzeuge sie ohne Nachfragen finden:

```
assets/templates/blau.png
assets/templates/schwarz.png
assets/templates/gold.png
assets/templates/premium.png
```

**Die Vorlage muss leer sein.** Kein Spieler, kein Name, keine Trikotnummer,
keine Auflagennummer. Das alles setzen wir, und es wechselt bei jeder Karte.
Steht es schon in der Grafik, erscheint es hinterher doppelt — genau daran
erkennt man, dass die Vorlage noch nicht leer ist.

Format: PNG oder JPG, mindestens 1428 x 2000 px (das entspricht 63 x 88 mm bei
300 dpi). Groesser ist besser, kleiner nicht brauchbar.

## assets/beispielfotos — echte Spielerfotos zum Kalibrieren

Damit die Schwellwerte in `specs/photo_spec.v1.json` auf echten Aufnahmen
beruhen und nicht auf Schaetzungen. Gebraucht werden **Originale**, keine
Kopien aus WhatsApp oder einem Chat — eine weitergeleitete Kopie ist auf ein
Viertel heruntergerechnet, und dann misst man die Kompression statt des Fotos.

Gern auch schlechte Beispiele: zu nah, zu weit weg, Gegenlicht, unruhiger
Hintergrund. Die braucht der Freisteller genauso wie die guten.

Benennung frei. Hilfreich ist ein Hinweis im Dateinamen, z. B.
`gut-wand.jpg`, `zu-nah.jpg`, `gegenlicht.jpg`.

## Wie die Dateien hierher kommen

Ohne Kommandozeile, direkt im Browser:

1. auf GitHub in den Ordner `assets/templates` gehen
2. **Add file → Upload files**
3. Dateien hineinziehen
4. unten **Commit changes**

Wichtig: der Branch muss `claude/trading-card-engine-architecture-yap1m2`
heissen, nicht `main` — oben links im Zweig-Auswahlfeld umstellen, bevor du
hochlaedst.
