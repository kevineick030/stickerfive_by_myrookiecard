#!/usr/bin/env python3
"""Renderplan fuer den Textlayer.

Nimmt eine FERTIGE, aber textlose Karte und legt nur noch Name, Verein,
Trikotnummer, Auflage und Unterschrift darauf. Das Bild kommt aus dem
Bildmodell, der Text aus der Datenbank - jeder Teil von dort, wo er
zuverlaessig ist.

Der Grund fuer die Trennung: ein Bildmodell MALT Buchstaben, es setzt sie
nicht. Bei "Bjoern Sjoegren" oder "Nuri Sahin" ist ein Fehler keine
Randerscheinung, und bei 60 Karten je Team faellt er erst beim Auspacken
auf. Text, der aus der Datenbank kommt, ist per Konstruktion richtig und
laesst sich hinterher per OCR dagegen pruefen.
"""
from __future__ import annotations

import json
import pathlib

from engine.fontmetrics import load_font
from engine.gate1 import check
from engine.layout import CardData, Landmarks, PhotoAsset, build_manifest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
FAMILIES = {f["id"]: f for f in SCHEMA["families"]}
TTF = {"display": str(ROOT / "assets" / "fonts" / "montserrat-semibold.ttf"),
       "body": str(ROOT / "assets" / "fonts" / "poppins-semibold.ttf")}
FONTS = {k: load_font(v) for k, v in TTF.items()}

GOLD = ("#8A6620", "#FFF3C0", "#C89A3C")
BLAU = ("#12318F", "#2E5FD8", "#0B1F63")
DUNKEL = ("#3A2B0A", "#5A4410", "#1A1204")
CREME = ("#FFF6D8", "#FFFFFF", "#E7CE8E")

FARBEN = {
    "DESIGN-1": {"player_name": GOLD, "club_name": BLAU, "jersey_number": GOLD, "serial": GOLD},
    "DESIGN-2": {"player_name": GOLD, "club_name": DUNKEL, "jersey_number": GOLD, "serial": GOLD},
    "DESIGN-3": {"player_name": DUNKEL, "club_name": DUNKEL,
                 "jersey_number": CREME, "serial": CREME},
    "DESIGN-4": {"player_name": GOLD, "club_name": GOLD, "jersey_number": GOLD, "serial": GOLD},
}

# Die Platzierung des Fotos interessiert hier nicht - das Bild ist fertig.
# build_manifest verlangt trotzdem ein Asset, also bekommt es eines, das
# jede Regel erfuellt. Die Foto-Platzierung wird danach verworfen.
_ATTRAPPE = PhotoAsset("0" * 64, 2000, 2800, Landmarks(900, 600, 1200, 1000),
                       cutout=True, subject_bottom_y=2780)


def baue(design: str, spieler: dict, auflage: dict, karte_datei: str,
         unterschrift: str | None = None, dpi: int = 300) -> dict:
    family = FAMILIES[design]
    card = CardData(
        card_item_id=spieler.get("id", "-"),
        copy_index=int(auflage.get("kopie", 1)),
        copies_total=int(auflage.get("gesamt", 1)),
        player_name=spieler["name"], club_name=spieler.get("verein", ""),
        season=spieler.get("saison", ""), position_label=spieler.get("rolle", ""),
        jersey_number=spieler.get("nummer"), team_name=spieler.get("team"),
        public_token=spieler.get("token", "x" * 22),
        resolver_host=spieler.get("host", "k.mrc.cards"),
        legal_line="")
    manifest = build_manifest(SCHEMA, family, card, _ATTRAPPE, FONTS, "1.0.0")
    texte = [p for p in manifest["front"]["placements"] if p["type"] == "text"]
    # Nur die Textslots der Vorderseite: das Foto stammt von der Attrappe,
    # und die Rueckseite setzt dieser Dienst gar nicht.
    vorne = {p["slot"] for p in texte}
    befunde = [str(f) for f in check(manifest) if getattr(f, "where", "") in vorne]
    return {
        "id": spieler.get("id", "karte"),
        "design": design, "designName": family["name"],
        "gesperrt": bool(family.get("blocker")),
        "dpi": dpi, "trim": [SCHEMA["geometry"]["trim_width"], SCHEMA["geometry"]["trim_height"]],
        "fertigeKarte": karte_datei,
        "unterschrift": unterschrift,
        "unterschriftBox": next(
            (s["box"] for s in SCHEMA["front"]["slots"] if s["id"] == "signature"), None),
        "schriften": {k: str(pathlib.Path(v).resolve()) for k, v in TTF.items()},
        "farben": {k: list(v) for k, v in FARBEN[design].items()},
        "placements": texte,
        "befunde": befunde,
        "fingerprint": manifest.get("fingerprint"),
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(baue(sys.argv[1], {"name": sys.argv[2], "verein": sys.argv[3],
                                        "nummer": sys.argv[4]},
                          {"kopie": 1, "gesamt": 3}, sys.argv[5]), indent=1, ensure_ascii=False))
