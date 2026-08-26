#!/usr/bin/env python3
"""Gate -1: was sich an einem Foto OHNE Gesichtserkennung messen laesst.

Aufloesung, Ruhe des Hintergrunds, Schaerfe und Belichtung braucht kein
Modell - nur Arithmetik. Das ist die Pruefung, die noch im Upload-Dialog
laufen kann, bevor irgendetwas hochgeladen oder bezahlt ist.

Die Kopfhoehe, an der die eigentliche Aufloesungsregel haengt, kommt aus
Schicht A und wird hier als Parameter erwartet, nicht geraten.

    python3 tools/photo_check.py assets/beispielfotos/*.jpg
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
PHOTO = next(s for s in SCHEMA["front"]["slots"] if s["id"] == "photo")
DR = PHOTO["derived_requirements"]


def measure(path: pathlib.Path) -> dict:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    small = im.resize((min(w, 900), round(min(w, 900) * h / w)), Image.LANCZOS)
    a = np.asarray(small).astype(np.float32)
    lum = a @ (0.299, 0.587, 0.114)

    # Ruhe des Hintergrunds. Erster Versuch nahm den ganzen Rand - und
    # meldete jede glatte Wand als unruhig, weil bei einem Brustbild der
    # KOERPER die untere Kante fuellt. Gemessen wird deshalb nur oben und
    # in den oberen 55 % der Seitenraender: dort steht bei einem
    # regelkonformen Ausschnitt garantiert Hintergrund.
    b = max(2, round(small.height * 0.06))
    sw = max(2, round(small.width * 0.08))
    oben = round(small.height * 0.55)
    rand = np.concatenate([lum[:b].ravel(),
                           lum[:oben, :sw].ravel(),
                           lum[:oben, -sw:].ravel()])
    # Schaerfe: Varianz des Laplace-Filters, der klassische Blur-Detektor.
    lap = (lum[:-2, 1:-1] + lum[2:, 1:-1] + lum[1:-1, :-2] + lum[1:-1, 2:]
           - 4 * lum[1:-1, 1:-1])
    return {
        "datei": path.name,
        "px": (w, h),
        "seitenverhaeltnis": round(w / h, 3),
        "megapixel": round(w * h / 1e6, 1),
        "hintergrund_streuung": round(float(rand.std()), 1),
        "schaerfe": round(float(lap.var()), 1),
        "helligkeit": round(float(lum.mean()), 1),
        "ueberstrahlt_prozent": round(float((lum > 250).mean() * 100), 1),
        "abgesoffen_prozent": round(float((lum < 6).mean() * 100), 1),
        # Groesste Kopfhoehe, die dieses Bild noch regelkonform zulaesst:
        # die Breite muss min_image_width_per_head_height mal Kopfhoehe sein.
        "kopf_max_px": round(w / DR["min_image_width_per_head_height"]),
        "kopf_min_px": DR["min_head_height_px"],
    }


def urteil(m: dict) -> list[str]:
    out = []
    if m["kopf_max_px"] < m["kopf_min_px"]:
        out.append(f"BILD_ZU_SCHMAL: bei {m['px'][0]} px Breite ist die groesste regelkonforme "
                   f"Kopfhoehe {m['kopf_max_px']} px, gebraucht werden {m['kopf_min_px']}")
    if m["hintergrund_streuung"] > 45:
        out.append(f"HINTERGRUND_UNRUHIG: Streuung {m['hintergrund_streuung']} (ruhig ist < 30)")
    elif m["hintergrund_streuung"] > 30:
        out.append(f"hintergrund grenzwertig: Streuung {m['hintergrund_streuung']}")
    if m["schaerfe"] < 60:
        out.append(f"UNSCHARF: Laplace-Varianz {m['schaerfe']} (scharf ist > 150)")
    elif m["schaerfe"] < 150:
        out.append(f"schaerfe grenzwertig: {m['schaerfe']}")
    if m["ueberstrahlt_prozent"] > 8:
        out.append(f"UEBERSTRAHLT: {m['ueberstrahlt_prozent']} % ausgebrannt")
    if m["helligkeit"] < 60:
        out.append(f"ZU_DUNKEL: mittlere Helligkeit {m['helligkeit']}")
    return out


def main(argv: list[str]) -> int:
    paths = [pathlib.Path(p) for p in argv[1:]]
    if not paths:
        print(__doc__)
        return 2
    print(f"Regel aus dem Slot-Schema: Kopf >= {DR['min_head_height_px']} px, "
          f"Bildbreite >= {DR['min_image_width_per_head_height']} x Kopfhoehe\n")
    for p in sorted(paths):
        m = measure(p)
        befunde = urteil(m)
        mark = "FAIL" if any(b.isupper() or b[:4].isupper() for b in befunde) else "ok  "
        print(f"{mark} {m['datei']}")
        print(f"      {m['px'][0]} x {m['px'][1]} px ({m['megapixel']} MP, {m['seitenverhaeltnis']}) · "
              f"Hintergrund {m['hintergrund_streuung']} · Schaerfe {m['schaerfe']} · "
              f"Helligkeit {m['helligkeit']}")
        print(f"      regelkonforme Kopfhoehe: {m['kopf_min_px']} bis {m['kopf_max_px']} px")
        for b in befunde:
            print(f"      - {b}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
