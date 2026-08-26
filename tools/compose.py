#!/usr/bin/env python3
"""Schicht B: aus Vorlage, freigestelltem Spieler und Daten eine fertige Karte.

Kein Modell, kein Zufall - dieselben Eingaben ergeben Byte fuer Byte dieselbe
Datei. Deshalb kostet ein Nachdruck nichts und sieht exakt aus wie die
Erstlieferung. Die Platzierung kommt aus engine.layout, damit Vorschau,
Druckdatei und Pruefung dieselbe Quelle haben.

    python3 tools/compose.py --alle
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from engine.fontmetrics import load_font
from engine.gate1 import check
from engine.layout import CardData, Landmarks, PhotoAsset, build_manifest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
FAMILIES = {f["id"]: f for f in SCHEMA["families"]}
GEO = SCHEMA["geometry"]

TTF = {"display": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
       "body": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}
FONTS = {k: load_font(v) for k, v in TTF.items()}

# Vorlagendatei und Textfarben je Design. Die Geometrie steht im Schema,
# die Farben gehoeren zum Artwork - deshalb hier.
DESIGNS = {
    "DESIGN-1": ("blau.png",    {"player_name": "#FFFFFF", "club_name": "#241A05",
                                 "jersey_number": "#F0D28A", "serial": "#EBD9A6"}),
    "DESIGN-2": ("schwarz.png", {"player_name": "#FFFFFF", "club_name": "#241A05",
                                 "jersey_number": "#F0D28A", "serial": "#EBD9A6"}),
    "DESIGN-3": ("gold.png",    {"player_name": "#1A1204", "club_name": "#241A05",
                                 "jersey_number": "#FFF3C8", "serial": "#FFF3C8"}),
    "DESIGN-4": ("premium.png", {"player_name": "#F3E3AE", "club_name": "#D6B15C",
                                 "jersey_number": "#F3E3AE", "serial": "#D6B15C"}),
}


def mm(v: float, dpi: int) -> float:
    return v / 25.4 * dpi


def compose(family_id: str, card: CardData, cut_png: pathlib.Path, lm: dict,
            dpi: int = 300) -> tuple[Image.Image, list]:
    family = FAMILIES[family_id]
    tpl_name, farben = DESIGNS[family_id]
    cut = Image.open(cut_png).convert("RGBA")
    photo = PhotoAsset("sha-" + cut_png.stem, cut.width, cut.height,
                       Landmarks(lm["eye_line_y"], lm["head_top_y"],
                                 lm["chin_y"], lm["center_x"]),
                       cutout=True, subject_bottom_y=lm.get("subject_bottom_y"))
    manifest = build_manifest(SCHEMA, family, card, photo, FONTS, "1.0.0")
    befunde = check(manifest)
    sperre = family.get("blocker")
    if sperre:
        befunde = list(befunde) + [f'[{sperre["severity"]}] {sperre["code"]} · design: '
                                   f'{family["name"]} ist fuer die Produktion gesperrt']

    W, H = round(mm(GEO["trim_width"], dpi)), round(mm(GEO["trim_height"], dpi))
    tpl = Image.open(ROOT / "assets" / "templates" / tpl_name).convert("RGB").resize((W, H), Image.LANCZOS)
    karte = tpl.copy()

    def kasten(box):
        return tuple(round(mm(v, dpi)) for v in (box["x"], box["y"],
                                                 box["x"] + box["w"], box["y"] + box["h"]))

    # --- Spieler, auf das Fotofenster beschnitten ---
    pl = next(p for p in manifest["front"]["placements"] if p["slot"] == "photo")
    pw, ph = (round(mm(v, dpi)) for v in pl["placed_size_mm"])
    ox, oy = (round(mm(v, dpi)) for v in pl["offset_mm"])
    schicht = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    schicht.paste(cut.resize((pw, ph), Image.LANCZOS), (ox, oy))
    # Fenstermaske mit weicher Unterkante. Der Verlauf bleibt kurz: der
    # Oberkoerper soll HINTER der Unterschriftenplatte verschwinden, nicht
    # schon auf halber Brust in Luft aufloesen.
    fx0, fy0, fx1, fy1 = kasten(pl["box_mm"])
    fenster = Image.new("L", (W, H), 0)
    ImageDraw.Draw(fenster).rectangle((fx0, fy0, fx1, fy1), fill=255)
    verlauf = round(mm(4, dpi))
    for i in range(verlauf):
        y = fy1 - verlauf + i
        if 0 <= y < H:
            ImageDraw.Draw(fenster).line([(fx0, y), (fx1, y)],
                                         fill=round(255 * (1 - i / verlauf) ** 1.6))
    schicht.putalpha(Image.fromarray(
        (np.asarray(schicht.getchannel("A")).astype(np.uint16)
         * np.asarray(fenster).astype(np.uint16) // 255).astype(np.uint8)))
    karte = Image.alpha_composite(karte.convert("RGBA"), schicht).convert("RGB")

    # --- Teile der Vorlage, die vor dem Spieler liegen ---
    for o in family.get("overlays", SCHEMA["front"].get("overlays", [])):
        k = kasten(o["box"])
        karte.paste(tpl.crop(k), k[:2])

    # --- eingedruckte Auflagennummer ueberdecken; MUSS nach den Overlays
    #     laufen, sonst holt das Kopfband sie bei Premium wieder zurueck ---
    for p in family.get("patches", SCHEMA["front"].get("patches", [])):
        b, off = p["box"], p["source_offset"]
        quelle = tpl.crop(tuple(round(mm(v, dpi)) for v in (
            b["x"] + off["dx"], b["y"] + off["dy"],
            b["x"] + b["w"] + off["dx"], b["y"] + b["h"] + off["dy"])))
        karte.paste(quelle, kasten(b)[:2])

    # --- Text ---
    d = ImageDraw.Draw(karte)
    for p in manifest["front"]["placements"]:
        if p["type"] != "text" or not p.get("text"):
            continue
        f = ImageFont.truetype(TTF.get(p["font"], TTF["body"]),
                               round(mm(p["size_pt"] * 25.4 / 72, dpi)))
        farbe = farben.get(p["slot"], "#FFFFFF")
        for zeile, basis in zip(p["lines"], p["baselines_mm"]):
            x = mm(p["anchor_x_mm"], dpi)
            anker = {"center": "ms", "right": "rs", "left": "ls"}.get(p["align"], "ls")
            d.text((x, mm(basis, dpi)), zeile, font=f, fill=farbe, anchor=anker,
                   stroke_width=max(1, round(mm(p["size_pt"] * 0.09 * 25.4 / 72, dpi)))
                   if p["slot"] in ("jersey_number", "serial") else 0,
                   stroke_fill="#0B0D12")
    return karte, befunde


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", default="out/karten")
    a = ap.parse_args()

    frei = ROOT / "out" / "freigestellt"
    daten = json.loads((frei / "landmarks.json").read_text(encoding="utf-8"))
    ziel = ROOT / a.out
    ziel.mkdir(parents=True, exist_ok=True)

    namen = [("Adnan Sahanic", "9", "SV Sparta Lichtenberg"),
             ("Lukas Schröder", "7", "FC Blauwald"),
             ("Jonas Wenger", "11", "SV Waldkirch"),
             ("Elias Brandt", "4", "TSV Ringsee"),
             ("Noah Keller", "6", "FC Teststadt")]
    familien = ["DESIGN-1", "DESIGN-2", "DESIGN-3", "DESIGN-4", "DESIGN-1"]

    for i, eintrag in enumerate(daten):
        if not eintrag.get("landmarks"):
            print(f"uebersprungen: {eintrag['quelle']} (keine Landmarken)")
            continue
        name, nr, verein = namen[i % len(namen)]
        fam = familien[i % len(familien)]
        card = CardData(card_item_id=f"demo-{i}", copy_index=1, copies_total=3,
                        player_name=name, club_name=verein, season="25/26",
                        position_label="Feldspieler", jersey_number=nr,
                        team_name="D-Jugend", public_token="Demo" + "z" * 18,
                        resolver_host="k.mrc.cards",
                        legal_line=f"© {verein}")
        png = frei / (pathlib.Path(eintrag["quelle"]).stem + ".png")
        karte, befunde = compose(fam, card, png, eintrag["landmarks"], a.dpi)
        datei = ziel / f"{fam}-{pathlib.Path(eintrag['quelle']).stem[:16]}.png"
        karte.save(datei)
        harte = [f for f in befunde if str(f).startswith("[FAIL]")]
        print(f"{datei.name}  {karte.size[0]} x {karte.size[1]} px  "
              f"{'FAIL' if harte else 'ok'}  {len(befunde)} Befund(e)")
        for f in befunde:
            print(f"      {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
