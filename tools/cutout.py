#!/usr/bin/env python3
"""Schicht A: freistellen und die Anker-Landmarken bestimmen.

Das Freistellen ist die einzige Stelle, an der ein Modell arbeitet - und es
laeuft einmal je SPIELER, nicht je Karte. Die Landmarken danach sind reine
Geometrie auf der Freistellmaske: der oberste gedeckte Punkt ist der Scheitel,
die schmalste Stelle unter dem Kopf ist der Hals. Dafuer braucht es keine
Gesichtserkennung und damit auch keine biometrischen Daten - ein Unterschied,
der datenschutzrechtlich zaehlt (Art. 9 DSGVO).

    python3 tools/cutout.py assets/beispielfotos/*.jpg --out out/freigestellt
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import numpy as np
from PIL import Image, ImageOps

MODELL = "u2net_human_seg"


def landmarks(alpha: np.ndarray) -> dict | None:
    """Scheitel, Kinn, Mitte und Augenlinie aus der Silhouette."""
    deckung = alpha > 96
    breite = deckung.sum(1)
    zeilen = np.where(breite > 0)[0]
    if len(zeilen) < 40:
        return None
    oben, unten = int(zeilen[0]), int(zeilen[-1])

    # Der Kopf ist der obere Teil bis zur schmalsten Stelle. Erst die groesste
    # Breite im oberen Fuenftel suchen, dann abwaerts bis es deutlich schmaler
    # wird - das ist der Hals, und damit ungefaehr die Kinnhoehe.
    fenster = max(10, int((unten - oben) * 0.22))
    kopf_breit = int(breite[oben:oben + fenster].max())
    hals = None
    for y in range(oben + fenster // 2, min(oben + int((unten - oben) * 0.75), unten)):
        if breite[y] < kopf_breit * 0.74:
            hals = y
            break
    if hals is None:                      # Kopf ohne erkennbaren Hals: Notfallmass
        hals = oben + int((unten - oben) * 0.30)

    kopf_hoehe = hals - oben
    if kopf_hoehe < 10:
        return None
    kopfband = deckung[oben:hals]
    spalten = np.where(kopfband.sum(0) > 0)[0]
    mitte = float((spalten[0] + spalten[-1]) / 2)
    # Augenlinie: bei einem menschlichen Kopf rund 45 % unter dem Scheitel.
    return {
        "head_top_y": float(oben),
        "chin_y": float(hals),
        "center_x": mitte,
        "eye_line_y": float(oben + kopf_hoehe * 0.45),
        "head_height": float(kopf_hoehe),
        "subject_bottom_y": float(unten),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bilder", nargs="+")
    ap.add_argument("--out", default="out/freigestellt")
    ap.add_argument("--max", type=int, default=1280,
                help="Aufloesung, mit der das Modell rechnet; die Maske wird danach auf das Originalbild hochgezogen")
    a = ap.parse_args()

    from rembg import new_session, remove
    ziel = pathlib.Path(a.out)
    ziel.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    sess = new_session(MODELL)
    print(f"Modell {MODELL} bereit ({time.time()-t0:.1f} s)\n")

    bericht = []
    for pfad in sorted(pathlib.Path(p) for p in a.bilder):
        voll = ImageOps.exif_transpose(Image.open(pfad)).convert("RGB")
        roh = voll.size
        # Das Modell rechnet ohnehin auf kleiner Aufloesung. Also klein
        # freistellen, aber die MASKE aufs Originalbild anwenden - sonst
        # verschenkt man genau die Aufloesung, an der die Druckregel haengt.
        klein = voll.copy()
        klein.thumbnail((a.max, a.max), Image.LANCZOS)
        t = time.time()
        maske = remove(klein, session=sess, only_mask=True)
        dauer = time.time() - t
        frei = voll.copy()
        frei.putalpha(maske.resize(roh, Image.LANCZOS))
        arr = np.asarray(frei)
        lm = landmarks(arr[:, :, 3])
        name = pfad.stem + ".png"
        frei.save(ziel / name)
        eintrag = {"quelle": pfad.name, "px_original": roh, "px_bearbeitet": frei.size,
                   "sekunden": round(dauer, 2),
                   "freigestellt_prozent": round(float((arr[:, :, 3] > 96).mean() * 100), 1),
                   "landmarks": lm}
        if lm:
            eintrag["kopfhoehe_original_px"] = round(lm["head_height"])
        bericht.append(eintrag)
        kh = eintrag.get("kopfhoehe_original_px")
        print(f"{pfad.name}")
        print(f"   {dauer:.2f} s · Person deckt {eintrag['freigestellt_prozent']} % der Flaeche")
        print(f"   Kopfhoehe im Original: {kh if kh else 'nicht bestimmbar'} px")
    (ziel / "landmarks.json").write_text(
        json.dumps(bericht, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ngeschrieben: {ziel}/ ({len(bericht)} Bilder + landmarks.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
