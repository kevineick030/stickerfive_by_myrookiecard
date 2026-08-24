#!/usr/bin/env python3
"""Erzeugt ein Musterblatt aus dem echten Slot-Schema.

  python3 tools/render_sample.py [-o out/sample-sheet.html]

Vier Karten mit absichtlich unterschiedlichen Fotogeometrien und Namen,
jede durch Gate 1 geprueft. Zeigt, ob die Ankerregel greift und ob die
deterministischen Pruefungen anschlagen, wo sie sollen.
"""
from __future__ import annotations

import argparse, base64, html, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.fontmetrics import load_font
from engine.gate1 import check, passed
from engine.layout import CardData, Landmarks, PhotoAsset, build_manifest
from engine.preview import card_svg

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = {
    "display": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "body": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}
PALETTES = {
    "DESIGN-1": dict(card_bg="#12303f", subject="#8fb9cc", photo_bg="#1d4759",
                     ink="#f2f7f9", muted="#9fc0cd", on_photo="#cfe4ec",
                     guide_trim="#d92e6a", guide_bleed="#9aa7ad", guide_safe="#2f9e6e"),
    "DESIGN-2": dict(card_bg="#2c1a3d", subject="#b79ccd", photo_bg="#3f2757",
                     ink="#f6f2fa", muted="#c1a9d4", on_photo="#ddcdea",
                     guide_trim="#d92e6a", guide_bleed="#9aa7ad", guide_safe="#2f9e6e"),
    "DESIGN-3": dict(card_bg="#3a2c0d", subject="#d9be74", photo_bg="#54401a",
                     ink="#fbf5e6", muted="#d3bd8b", on_photo="#eddfbe",
                     guide_trim="#d92e6a", guide_bleed="#9aa7ad", guide_safe="#2f9e6e"),
    "DESIGN-4": dict(card_bg="#14331f", subject="#8fc4a3", photo_bg="#1e4a2e",
                     ink="#f0f7f2", muted="#a6cbb4", on_photo="#cfe6d8",
                     guide_trim="#d92e6a", guide_bleed="#9aa7ad", guide_safe="#2f9e6e"),
}
HOST = "k.mrc.cards"

# Vier Faelle. Die ersten drei sind regelkonform, aber unterschiedlich
# geschnitten - genau dafuer gibt es die Ankerregel. Der vierte ist ein
# absichtlicher Grenzfall und muss durch Gate 1 fallen.
CASES = [
    dict(family="DESIGN-1", label="weiter Ausschnitt, viel Luft um den Kopf",
         name="Lukas Meier", nr="7", pos="Feldspieler",
         photo=PhotoAsset("a" * 64, 1800, 2400, Landmarks(887, 500, 1360, 900)),
         stats=[("Spiele", "18"), ("Tore", "11")]),
    dict(family="DESIGN-2", label="enger Ausschnitt, gerade noch regelkonform",
         name="Tim Klein", nr="1", pos="Torwart",
         photo=PhotoAsset("b" * 64, 1600, 2000, Landmarks(742, 400, 1160, 800)),
         stats=[("Spiele", "20"), ("Zu null", "6")]),
    dict(family="DESIGN-3", label="Diakritika · löst Autofit aus",
         name="Đorđe Đorđević", nr=None, pos="Trainer",
         photo=PhotoAsset("c" * 64, 2000, 2600, Landmarks(1023, 600, 1540, 1000)),
         stats=[("Seit", "2019")]),
    dict(family="DESIGN-1", label="Grenzfall: knappes Foto und sehr langer Name",
         name="Maximilian von Hohenberg-Schönau", nr="42", pos="Feldspieler",
         photo=PhotoAsset("d" * 64, 720, 960, Landmarks(373, 200, 584, 360)),
         stats=[]),
]

def data_uri(path: str) -> str:
    return "data:font/ttf;base64," + base64.b64encode(pathlib.Path(path).read_bytes()).decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(ROOT / "out" / "sample-sheet.html"))
    args = ap.parse_args()

    schema = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
    fonts = {k: load_font(v) for k, v in FONTS.items()}
    families = {f["id"]: f for f in schema["families"]}
    geo = schema["geometry"]
    vb_w = geo["trim_width"] + 2 * geo["bleed"]
    vb_h = geo["trim_height"] + 2 * geo["bleed"]

    blocks, summary = [], []
    for i, case in enumerate(CASES):
        fam = families[case["family"]]
        card = CardData(
            card_item_id=f"demo-{i+1}", copy_index=1,
            player_name=case["name"], club_name="TSV Musterstadt", season="25/26",
            position_label=case["pos"], jersey_number=case["nr"],
            team_name="D-Jugend", stats=case["stats"],
            public_token=f"Demo{i+1}Token{'x'*(22-11-len(str(i+1)))}"[:22].ljust(22, "z"),
            resolver_host=HOST, legal_line="© TSV Musterstadt · Nur für den privaten Gebrauch")

        manifest = build_manifest(schema, fam, card, case["photo"], fonts, "1.0.0")
        findings = check(manifest)
        pal = PALETTES[fam["id"]]

        sides = "".join(
            f'<div class="side"><svg viewBox="{-geo["bleed"]} {-geo["bleed"]} {vb_w} {vb_h}" '
            f'role="img" aria-label="{html.escape(case["name"])} {s}">'
            f'{card_svg(manifest, s, pal, f"c{i}{s}")}</svg>'
            f'<span>{"Vorderseite" if s == "front" else "Rückseite"}</span></div>'
            for s in ("front", "back"))

        photo_p = next(p for p in manifest["front"]["placements"] if p["type"] == "image")
        qr_p = next(p for p in manifest["back"]["placements"] if p["type"] == "qr")
        name_p = next(p for p in manifest["front"]["placements"] if p["slot"] == "player_name")

        facts = [
            ("Ausgangsfoto", f'{photo_p["source_px"][0]}×{photo_p["source_px"][1]} px'),
            ("Skalierung", f'{photo_p["scale_mm_per_px"]:.4f} mm/px'),
            ("Effektive Auflösung", f'{photo_p["effective_dpi"]:.0f} dpi'),
            ("Augenlinie nachher", f'{photo_p["resulting_eye_line_ratio"]:.3f}'),
            ("Kopfhöhe nachher", f'{photo_p["resulting_head_height_ratio"]:.3f}'),
            ("Name gesetzt bei", f'{name_p["size_pt"]} pt von {name_p["declared_size_pt"]} pt'),
            ("Namensbreite", f'{name_p["measured_width_mm"]:.1f} mm in {name_p["box_mm"]["w"]:.0f} mm'),
            ("QR", f'v{qr_p["version"]} · {qr_p["payload_bytes"]} B · {qr_p["module_mm"]:.3f} mm/Modul'),
            ("Front-Fingerprint", manifest["front"]["fingerprint"][:16] + "…"),
        ]
        rows = "".join(f"<tr><td>{k}</td><td>{html.escape(v)}</td></tr>" for k, v in facts)

        if findings:
            fl = "".join(
                f'<li class="{f.severity.lower()}"><b>{f.severity}</b> '
                f'<code>{f.code}</code> · {html.escape(f.slot)}<br>{html.escape(f.message)}</li>'
                for f in findings)
        else:
            fl = '<li class="ok">Gate 1 ohne Befund</li>'

        verdict = "PASS" if passed(findings) else "FAIL"
        summary.append((case["name"], fam["id"], verdict, len(findings)))
        blocks.append(
            f'<section class="card-block">'
            f'<header><h2>{html.escape(case["name"])}</h2>'
            f'<p>{fam["id"]} · {html.escape(case["label"])} '
            f'<span class="pill {verdict.lower()}">Gate 1: {verdict}</span></p></header>'
            f'<div class="cards">{sides}</div>'
            f'<div class="panel"><table>{rows}</table><ul class="findings">{fl}</ul></div>'
            f'</section>')

    sum_rows = "".join(
        f'<tr><td>{html.escape(n)}</td><td><code>{f}</code></td>'
        f'<td class="{v.lower()}">{v}</td><td>{c}</td></tr>' for n, f, v, c in summary)

    page = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Musterblatt · Trading-Card-Engine</title><style>
@font-face{{font-family:"DejaVu Sans";src:url({data_uri(FONTS["body"])}) format("truetype");font-weight:400}}
@font-face{{font-family:"DejaVu Sans";src:url({data_uri(FONTS["display"])}) format("truetype");font-weight:700}}
*{{box-sizing:border-box}}
body{{margin:0;background:#eef2f3;color:#101719;font:15px/1.55 "DejaVu Sans",system-ui,sans-serif;padding:28px}}
.wrap{{max-width:1180px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}}
.lead{{color:#4b5c62;margin:0 0 22px;max-width:70ch}}
.note{{background:#fff;border:1px solid #cfd9db;border-left:3px solid #0a6e8f;padding:12px 15px;margin:0 0 26px;font-size:13.5px;color:#3d4d53}}
.card-block{{background:#fff;border:1px solid #cfd9db;border-radius:4px;padding:20px;margin-bottom:20px}}
.card-block header h2{{font-size:18px;margin:0 0 3px}}
.card-block header p{{margin:0 0 16px;color:#5b6c72;font-size:13px}}
.cards{{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}}
.side{{text-align:center}}
.side svg{{width:186px;height:auto;display:block;filter:drop-shadow(0 3px 9px rgba(16,23,25,.18))}}
.side span{{display:block;margin-top:7px;font-size:11px;color:#6d7e84;letter-spacing:.06em;text-transform:uppercase}}
.panel{{display:flex;gap:22px;flex-wrap:wrap;margin-top:18px;padding-top:16px;border-top:1px solid #e3eaec}}
table{{border-collapse:collapse;font-size:12.5px;min-width:330px}}
td{{padding:4px 12px 4px 0;border-bottom:1px solid #eef2f3;vertical-align:top}}
td:first-child{{color:#5b6c72;white-space:nowrap}}
td:last-child{{font-variant-numeric:tabular-nums}}
.findings{{list-style:none;margin:0;padding:0;font-size:12.5px;flex:1;min-width:290px}}
.findings li{{padding:7px 10px;border-radius:3px;margin-bottom:6px;line-height:1.4}}
.findings .fail{{background:#fbe6ee;color:#8d1745}}
.findings .warn{{background:#fbf1da;color:#71510a}}
.findings .ok{{background:#e0efe6;color:#1a5d42}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:11.5px}}
.pill{{display:inline-block;padding:2px 8px;border-radius:2px;font-size:11px;font-weight:700;letter-spacing:.05em;margin-left:6px}}
.pill.pass{{background:#e0efe6;color:#1a5d42}} .pill.fail{{background:#fbe6ee;color:#8d1745}}
.summary{{background:#fff;border:1px solid #cfd9db;border-radius:4px;padding:18px 20px}}
.summary h2{{font-size:15px;margin:0 0 10px}}
.summary td.pass{{color:#1a5d42;font-weight:700}} .summary td.fail{{color:#8d1745;font-weight:700}}
.legend{{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#5b6c72;margin-top:14px}}
.legend i{{display:inline-block;width:16px;height:0;border-top:2px solid;margin-right:6px;vertical-align:middle}}
</style></head><body><div class="wrap">
<h1>Musterblatt · Trading-Card-Engine</h1>
<p class="lead">Vier Karten, gerendert allein aus <code>specs/slot_schema.v1.json</code>. Jede Vorschau
ist ausschließlich aus dem Render-Manifest gezeichnet — was hier zu sehen ist, steht auch im Manifest,
und was Gate 1 prüft, sind dieselben Zahlen.</p>
<p class="note"><b>Zwei Hinweise zum Lesen.</b> Die Fotos sind Platzhalter-Silhouetten, aus den
Landmarks derselben Ankerregel aufgebaut — sie stehen für das freigestellte Kundenfoto und machen
sichtbar, wohin Kopf und Schultern gesetzt werden. Der QR-Code ist <b>schematisch</b> und nicht
scannbar: Ein echter Encoder gehört in die Produktion und kommt dort aus einer geprüften Bibliothek.
Version, Modulanzahl und Modulgröße sind dagegen echt gerechnet.</p>
{"".join(blocks)}
<div class="summary"><h2>Gate-1-Ergebnis</h2>
<table><tr><td>Karte</td><td>Design</td><td>Urteil</td><td>Befunde</td></tr>{sum_rows}</table>
<div class="legend">
<span><i style="border-color:#d92e6a"></i>Endformat (Trim)</span>
<span><i style="border-color:#9aa7ad;border-top-style:dashed"></i>Anschnitt</span>
<span><i style="border-color:#2f9e6e;border-top-style:dashed"></i>Sicherheitszone</span>
</div></div>
</div></body></html>"""

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"geschrieben: {out}")
    for n, f, v, c in summary:
        print(f"  {v:4s}  {f:9s}  {c} Befund(e)  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
