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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine.fontmetrics import load_font
from engine.gate1 import check
from engine.layout import CardData, Landmarks, PhotoAsset, build_manifest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
FAMILIES = {f["id"]: f for f in SCHEMA["families"]}
GEO = SCHEMA["geometry"]

# Die Hausschriften: Montserrat fuer Namen und Zahlen, Poppins fuer die
# Zeilen darunter. Beide sind deutlich breiter als der frueher benutzte
# Notbehelf - die Groessen sind daran neu ausgerichtet.
# Eine Systemschrift wie DejaVu ist zu breit und zu weich - Namen mussten
# verkleinert werden und wirkten dadurch beliebig. Sobald die Originalschrift
# vorliegt, wird hier nur der Pfad getauscht; alle Groessen bleiben gueltig,
# weil die Engine mit echten Schriftmetriken rechnet.
TTF = {"display": str(ROOT / "assets" / "fonts" / "montserrat-semibold.ttf"),
       "body": str(ROOT / "assets" / "fonts" / "poppins-semibold.ttf")}
FONTS = {k: load_font(v) for k, v in TTF.items()}

# Vorlagendatei und Textfarben je Design. Die Geometrie steht im Schema,
# die Farben gehoeren zum Artwork - deshalb hier.
# Gold ist auf diesen Karten nie eine Flaeche, sondern ein Verlauf mit
# Glanzkante. Genau das unterscheidet eine gedruckte Sammelkarte von einem
# Etikett - und war der Hauptgrund, warum die Zahlen "billig" wirkten.
GOLD = ("#8A6620", "#FFF3C0", "#C89A3C")     # dunkel, Glanz, tief
WEISS = ("#DCE6F2", "#FFFFFF", "#B9C9DD")
DUNKEL = ("#3A2B0A", "#5A4410", "#1A1204")
BLAU   = ("#12318F", "#2E5FD8", "#0B1F63")

DESIGNS = {
    "DESIGN-1": ("blau.png",    {"player_name": GOLD, "club_name": BLAU,
                                 "jersey_number": GOLD, "serial": GOLD}),
    "DESIGN-2": ("schwarz.png", {"player_name": GOLD, "club_name": DUNKEL,
                                 "jersey_number": GOLD, "serial": GOLD}),
    # Auf der Goldvorlage ist Gold auf Gold unsichtbar. Die Zahlen bekommen
    # dort Creme mit dunklem Schatten - so wie auf der Beispielkarte.
    "DESIGN-3": ("gold.png",    {"player_name": DUNKEL, "club_name": DUNKEL,
                                 "jersey_number": ("#FFF6D8", "#FFFFFF", "#E7CE8E"),
                                 "serial": ("#FFF6D8", "#FFFFFF", "#E7CE8E")}),
    "DESIGN-4": ("premium.png", {"player_name": GOLD, "club_name": GOLD,
                                 "jersey_number": GOLD, "serial": GOLD}),
}


def _verlauf(w: int, h: int, farben: tuple[str, str, str]) -> Image.Image:
    """Senkrechter Dreiklang dunkel - Glanz - tief, wie bei Goldpraegung."""
    unten, glanz, tief = (Image.new("RGB", (1, 1), c).getpixel((0, 0)) for c in farben)
    band = Image.new("RGB", (1, max(h, 2)))
    px = band.load()
    for y in range(band.height):
        t = y / (band.height - 1)
        a, b, lokal = (unten, glanz, t / 0.42) if t < 0.42 else (glanz, tief, (t - 0.42) / 0.58)
        px[0, y] = tuple(round(a[i] + (b[i] - a[i]) * lokal) for i in range(3))
    return band.resize((max(w, 1), max(h, 1)), Image.BILINEAR)


def _setze(zeichner, xy, zeile, font, anker, spur, **kw):
    """Eine Zeile setzen, bei Bedarf mit Laufweite (Zeichen fuer Zeichen)."""
    if not spur:
        zeichner.text(xy, zeile, font=font, anchor=anker, **kw)
        return
    breite = sum(font.getlength(c) + spur for c in zeile) - spur
    x = xy[0] - (breite / 2 if anker[0] == "m" else breite if anker[0] == "r" else 0)
    for c in zeile:
        zeichner.text((x, xy[1]), c, font=font, anchor="l" + anker[1], **kw)
        x += font.getlength(c) + spur


def text_mit_verlauf(karte, xy, zeile, font, farben, anker, schatten, spur=0.0):
    """Text als Maske setzen und den Verlauf hindurchgiessen.

    Ein harter schwarzer Umriss ringsum ist der WordArt-Effekt, an dem man
    Amateursatz erkennt. Eine Praegung wirft stattdessen einen weichen
    Schatten nach unten - schmal, versetzt, nicht ringsum.
    """
    if isinstance(farben, str):
        _setze(ImageDraw.Draw(karte), xy, zeile, font, anker, spur, fill=farben)
        return
    if schatten:
        sch = Image.new("L", karte.size, 0)
        _setze(ImageDraw.Draw(sch), (xy[0], xy[1] + schatten), zeile, font, anker, spur, fill=190)
        sch = sch.filter(ImageFilter.GaussianBlur(max(1, schatten * 0.9)))
        karte.paste(Image.new("RGB", karte.size, (10, 12, 18)), (0, 0), sch)
    hilfs = Image.new("L", karte.size, 0)
    _setze(ImageDraw.Draw(hilfs), xy, zeile, font, anker, spur, fill=255)
    kasten = hilfs.getbbox()
    if not kasten:
        return
    flaeche = Image.new("RGB", karte.size, farben[1])
    flaeche.paste(_verlauf(kasten[2] - kasten[0], kasten[3] - kasten[1], farben),
                  (kasten[0], kasten[1]))
    karte.paste(flaeche, (0, 0), hilfs)


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
    for p in manifest["front"]["placements"]:
        if p["type"] != "text" or not p.get("text"):
            continue
        f = ImageFont.truetype(TTF.get(p["font"], TTF["body"]),
                               round(mm(p["size_pt"] * 25.4 / 72, dpi)))
        farbe = farben.get(p["slot"], "#FFFFFF")
        # Schatten nur bei den freistehenden Zahlen; Text auf einem Band
        # braucht keinen, dort traegt der Untergrund.
        schatten = round(mm(p["size_pt"] * 0.05 * 25.4 / 72, dpi)) \
            if p["slot"] in ("jersey_number", "serial") else 0
        spur = mm(p.get("letter_spacing_em", 0.0) * p["size_pt"] * 25.4 / 72, dpi)
        anker = {"center": "ms", "right": "rs", "left": "ls"}.get(p["align"], "ls")
        for zeile, basis in zip(p["lines"], p["baselines_mm"]):
            text_mit_verlauf(karte, (mm(p["anchor_x_mm"], dpi), mm(basis, dpi)),
                             zeile, f, farbe, anker, schatten, spur)
    return karte, befunde


def plan(family_id, card, cut_png, lm, dpi=300):
    """Alles, was der Browser-Renderer braucht - ohne selbst zu zeichnen."""
    family = FAMILIES[family_id]
    tpl_name, farben = DESIGNS[family_id]
    cut = Image.open(cut_png)
    photo = PhotoAsset("sha-" + cut_png.stem, cut.width, cut.height,
                       Landmarks(lm["eye_line_y"], lm["head_top_y"],
                                 lm["chin_y"], lm["center_x"]),
                       cutout=True, subject_bottom_y=lm.get("subject_bottom_y"))
    manifest = build_manifest(SCHEMA, family, card, photo, FONTS, "1.0.0")
    return {
        "id": f"{family_id}-{cut_png.stem[:16]}",
        "design": family_id, "designName": family["name"],
        "gesperrt": bool(family.get("blocker")),
        "dpi": dpi, "trim": [SCHEMA["geometry"]["trim_width"], SCHEMA["geometry"]["trim_height"]],
        "vorlage": str((ROOT / "assets" / "templates" / tpl_name).resolve()),
        "spieler": str(cut_png.resolve()),
        "schriften": {k: str(pathlib.Path(v).resolve()) for k, v in TTF.items()},
        "farben": {k: (list(v) if not isinstance(v, str) else v) for k, v in farben.items()},
        "overlays": family.get("overlays", SCHEMA["front"].get("overlays", [])),
        "patches": family.get("patches", SCHEMA["front"].get("patches", [])),
        "placements": manifest["front"]["placements"],
        "befunde": [str(f) for f in check(manifest)],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--plan", action="store_true",
                    help="Renderplaene als JSON schreiben statt selbst zu rastern")
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
        if a.plan:
            pl = plan(fam, card, png, eintrag["landmarks"], a.dpi)
            (ziel / (pl["id"] + ".json")).write_text(
                json.dumps(pl, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f'{pl["id"]}.json  {len(pl["befunde"])} Befund(e)')
            continue
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
