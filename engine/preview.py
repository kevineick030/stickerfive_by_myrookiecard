"""Layout-Vorschau als SVG - gezeichnet ausschliesslich aus dem Manifest.

Kein Druckersatz, sondern eine Sichtpruefung des Layouts: Wenn die Vorschau
richtig aussieht, ist das Manifest vollstaendig genug, damit ein
Produktionsrenderer daraus PDF/X erzeugen kann.

Der QR-Code wird SCHEMATISCH gezeichnet. Ein echter Encoder gehoert in die
Produktion und wird dort von einer geprueften Bibliothek geliefert - ein
selbstgebauter, nicht gegen einen Decoder verifizierter Encoder waere
schlimmer als gar keiner.
"""
from __future__ import annotations

import hashlib
from xml.sax.saxutils import escape

from .fontmetrics import MM_PER_PT

FONT_STACK = {
    "display": "DejaVu Sans, Verdana, sans-serif",
    "body": "DejaVu Sans, Verdana, sans-serif",
}


def _qr_modules(payload: str, n: int) -> list[list[bool]]:
    """Schematisches, aber deterministisches Modulmuster mit echten Suchmustern."""
    digest = hashlib.sha256(payload.encode()).digest()
    grid = [[bool((digest[(r * n + c) % len(digest)] >> ((r + c) % 8)) & 1)
             for c in range(n)] for r in range(n)]
    for oy, ox in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(7):
            for c in range(7):
                edge = r in (0, 6) or c in (0, 6)
                core = 2 <= r <= 4 and 2 <= c <= 4
                grid[oy + r][ox + c] = edge or core
        for r in range(-1, 8):
            for c in range(-1, 8):
                if 0 <= oy + r < n and 0 <= ox + c < n and not (0 <= r < 7 and 0 <= c < 7):
                    grid[oy + r][ox + c] = False
    return grid


def _silhouette(p: dict, palette: dict) -> str:
    """Platzhaltermotiv in Quellpixel-Koordinaten, aus den Landmarks gebaut.

    Steht stellvertretend fuer das freigestellte Kundenfoto und macht sichtbar,
    wohin die Ankerregel Kopf und Schultern setzt.
    """
    w, h = p["source_px"]
    lm = p.get("landmarks_px")
    parts = [f'<rect x="0" y="0" width="{w}" height="{h}" fill="{palette["photo_bg"]}"/>']
    if lm:
        head_r = (lm["chin_y"] - lm["head_top_y"]) / 2
        cx, cy = lm["center_x"], lm["head_top_y"] + head_r
        sh_w = head_r * 2.9
        parts += [
            f'<path d="M {cx - sh_w/2} {h} '
            f'C {cx - sh_w/2} {lm["chin_y"] + head_r*0.6} {cx - head_r*0.9} {lm["chin_y"]} '
            f'{cx} {lm["chin_y"]} '
            f'C {cx + head_r*0.9} {lm["chin_y"]} {cx + sh_w/2} {lm["chin_y"] + head_r*0.6} '
            f'{cx + sh_w/2} {h} Z" fill="{palette["subject"]}"/>',
            f'<circle cx="{cx}" cy="{cy}" r="{head_r}" fill="{palette["subject"]}"/>',
            f'<line x1="{cx - head_r*0.75}" y1="{lm["eye_line_y"]}" '
            f'x2="{cx + head_r*0.75}" y2="{lm["eye_line_y"]}" '
            f'stroke="{palette["photo_bg"]}" stroke-width="{max(head_r*0.10, 1)}"/>',
        ]
    else:
        parts.append(f'<rect x="{w*0.15}" y="{h*0.2}" width="{w*0.7}" height="{h*0.8}" '
                     f'fill="{palette["subject"]}"/>')
    return "".join(parts)


def card_svg(manifest: dict, side: str, palette: dict, uid: str,
             show_guides: bool = True) -> str:
    geo = manifest["geometry"]
    bleed, safe = geo["bleed"], geo["safe_margin"]
    tw, th = geo["trim_width"], geo["trim_height"]
    out: list[str] = []

    out.append(f'<clipPath id="trim-{uid}">'
               f'<rect x="0" y="0" width="{tw}" height="{th}" rx="1.5"/></clipPath>')
    out.append(f'<g clip-path="url(#trim-{uid})">')
    out.append(f'<rect x="{-bleed}" y="{-bleed}" width="{tw+2*bleed}" '
               f'height="{th+2*bleed}" fill="{palette["card_bg"]}"/>')

    for p in manifest[side]["placements"]:
        box = p.get("box_mm")
        kind = p["type"]

        if kind == "image":
            dx, dy = p["offset_mm"]
            s = p["scale_mm_per_px"]
            out.append(f'<clipPath id="ph-{uid}"><rect x="{box["x"]}" y="{box["y"]}" '
                       f'width="{box["w"]}" height="{box["h"]}"/></clipPath>')
            out.append(f'<g clip-path="url(#ph-{uid})">'
                       f'<g transform="translate({dx} {dy}) scale({s})">'
                       f'{_silhouette(p, palette)}</g></g>')
            out.append(f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" '
                       f'height="{box["h"]}" fill="url(#fade-{uid})"/>')

        elif kind == "qr":
            n = p["modules"] or 33
            m = p["module_mm"] or (box["w"] / (n + 8))
            grid = _qr_modules(p["payload"], n)
            origin_x = box["x"] + (box["w"] - n * m) / 2
            origin_y = box["y"] + (box["h"] - n * m) / 2
            out.append(f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" '
                       f'height="{box["h"]}" fill="#ffffff"/>')
            cells = "".join(
                f'<rect x="{origin_x + c*m:.3f}" y="{origin_y + r*m:.3f}" '
                f'width="{m:.3f}" height="{m:.3f}"/>'
                for r in range(n) for c in range(n) if grid[r][c])
            out.append(f'<g fill="#000000" shape-rendering="crispEdges">{cells}</g>')

        elif kind == "keyvalue":
            size_mm = p["size_pt"] * MM_PER_PT
            for i, (k, v) in enumerate(p["rows"]):
                y = box["y"] + size_mm * 0.9 + i * size_mm * 1.5
                out.append(
                    f'<text x="{box["x"]}" y="{y}" font-family="{FONT_STACK["body"]}" '
                    f'font-size="{size_mm}" fill="{palette["muted"]}">{escape(k)}</text>'
                    f'<text x="{box["x"]+box["w"]}" y="{y}" text-anchor="end" '
                    f'font-family="{FONT_STACK["body"]}" font-size="{size_mm}" '
                    f'font-weight="600" fill="{palette["ink"]}">{escape(v)}</text>')

        elif kind == "text" and p.get("lines"):
            size_mm = p["size_pt"] * MM_PER_PT
            anchor = {"left": "start", "right": "end", "center": "middle"}[p.get("align", "left")]
            weight = "700" if p.get("font") == "display" else "400"
            spacing = p.get("letter_spacing_em", 0.0) * size_mm
            colour = palette["on_photo"] if p["slot"] in ("season",) else palette["ink"]
            for line, base in zip(p["lines"], p["baselines_mm"]):
                out.append(
                    f'<text x="{p["anchor_x_mm"]}" y="{base}" text-anchor="{anchor}" '
                    f'font-family="{FONT_STACK[p.get("font","body")]}" '
                    f'font-size="{size_mm}" font-weight="{weight}" '
                    f'letter-spacing="{spacing}" fill="{colour}">{escape(line)}</text>')

    out.append("</g>")

    if show_guides:
        out.append(
            f'<rect x="{-bleed}" y="{-bleed}" width="{tw+2*bleed}" height="{th+2*bleed}" '
            f'fill="none" stroke="{palette["guide_bleed"]}" stroke-width="0.12" '
            f'stroke-dasharray="0.8 0.6"/>'
            f'<rect x="0" y="0" width="{tw}" height="{th}" rx="1.5" fill="none" '
            f'stroke="{palette["guide_trim"]}" stroke-width="0.18"/>'
            f'<rect x="{safe}" y="{safe}" width="{tw-2*safe}" height="{th-2*safe}" '
            f'fill="none" stroke="{palette["guide_safe"]}" stroke-width="0.1" '
            f'stroke-dasharray="0.5 0.5"/>')

    defs = (f'<linearGradient id="fade-{uid}" x1="0" y1="0.55" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{palette["card_bg"]}" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="{palette["card_bg"]}" stop-opacity="0.92"/>'
            f'</linearGradient>')
    return f"<defs>{defs}</defs>" + "".join(out)
