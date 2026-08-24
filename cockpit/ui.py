"""Bausteine der Cockpit-Oberflaeche.

Serverseitig gerendert, ohne Framework und ohne Build-Schritt. Ein Cockpit
wird ueberflogen und bedient, nicht gelesen: erst die Zusammenfassung, dann
der Arbeitsvorrat, dann der Einzelfall.

Zu den Farben: Zustaende tragen immer Form UND Zahl - Plakette, Farbstreifen
und Beschriftung -, nie Farbe allein. Die Markierungen im Diagramm nutzen
gepruefte Statusfarben; Texte tragen Textfarben, nie die Reihenfarbe.
"""
from __future__ import annotations

from html import escape

# Diagrammfarben: je eine Reihe, deshalb kein Nebeneinander zweier Toene,
# das bei Farbenblindheit verschmelzen koennte. Gegen beide Flaechen geprueft.
MARK_CRITICAL = "#d03b3b"
MARK_GOOD = "#0ca30c"

# Aufzaehlungen der Datenbank sind englisch und knapp - im Cockpit steht,
# was ein Mensch liest.
LABEL = {
    # Kartenzustaende
    "DRAFT": "Entwurf", "DATA_VALIDATED": "Daten geprüft", "PHOTO_ACCEPTED": "Foto angenommen",
    "ASSET_READY": "Freisteller fertig", "RENDER_QUEUED": "Rendern eingeplant",
    "RENDERED": "Gerendert", "QA_PASSED": "QA bestanden", "QA_FAILED": "QA gescheitert",
    "APPROVED": "Freigegeben", "BATCHED": "Im Druck-Batch", "SENT_TO_PRINT": "An Druckerei",
    "PRINTED": "Gedruckt", "PACKED": "Konfektioniert", "SHIPPED": "Versandt",
    "DELIVERED": "Geliefert", "BLOCKED": "Blockiert", "CANCELLED": "Storniert",
    "REPRINT_REQUESTED": "Nachdruck",
    # Auftragszustaende
    "RECEIVED": "Eingegangen", "VALIDATING": "In Prüfung", "IN_PRODUCTION": "In Produktion",
    "PARTIALLY_COMPLETE": "Teilweise fertig", "COMPLETE": "Fertig", "CLOSED": "Abgeschlossen",
    "ON_HOLD": "Angehalten", "ACCEPTED": "Angenommen",
    # Zustaendigkeiten
    "PARTNER": "Partner", "CLUB": "Verein", "CUSTOMER": "Kunde", "INTERNAL": "Intern",
    # Schwere
    "HARD": "Hart", "SOFT": "Weich",
    # Ausgangskanaele und -zustaende
    "PRINTER": "Druckerei", "MESSAGE": "Nachricht", "WEBHOOK": "Webhook",
    "PENDING": "Wartend", "IN_FLIGHT": "Unterwegs", "SENT": "Gesendet",
    "FAILED": "Fehlgeschlagen", "ABANDONED": "Aufgegeben",
    # Druck-Batches
    "OPEN": "In Bildung", "SEALED": "Versiegelt", "TRANSFERRED": "Übertragen",
    "ACKNOWLEDGED": "Quittiert",
    # Rollen
    "FIELD": "Feldspieler", "KEEPER": "Torwart", "COACH": "Trainer", "STAFF": "Betreuer",
}


# Auf dem Team-Board ist je Kachel nur eine Zeile Platz - dort steht die
# Kurzform, sonst die ausgeschriebene.
SHORT = {
    "DATA_VALIDATED": "Daten ok", "PHOTO_ACCEPTED": "Foto ok",
    "ASSET_READY": "Freisteller", "RENDER_QUEUED": "Rendern",
    "SENT_TO_PRINT": "Im Druck", "REPRINT_REQUESTED": "Nachdruck",
    "PARTIALLY_COMPLETE": "Teilweise",
}


def short(value: str | None) -> str:
    return SHORT.get(value or "", de(value))


def de(value: str | None) -> str:
    """Datenbankwert -> lesbare Bezeichnung. Unbekanntes bleibt, wie es ist."""
    if not value:
        return "—"
    return LABEL.get(value, value.replace("_", " ").capitalize())

CSS = """
:root{
  --paper:#EFF3F3; --surface:#FFFFFF; --surface-2:#E7EDEE; --surface-3:#DCE5E7;
  --ink:#0F1619; --ink-2:#4B5C62; --ink-3:#6D7E84; --rule:#D2DCDE; --rule-2:#BECBCE;
  --accent:#0A6E8F; --accent-wash:#DEEEF4;
  --good:#1D6A4B; --good-wash:#DCEDE4;
  --warn:#86610A; --warn-wash:#F6EDD6;
  --crit:#A81B57; --crit-wash:#F7E2EB;
  --shadow:0 1px 2px rgba(15,22,25,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0B1013; --surface:#131B1F; --surface-2:#1B252A; --surface-3:#222E34;
  --ink:#E3ECEE; --ink-2:#8CA1A8; --ink-3:#71868D; --rule:#222E33; --rule-2:#314147;
  --accent:#4FC0E4; --accent-wash:#0E2C38;
  --good:#5FC79C; --good-wash:#0F2A20;
  --warn:#D6A93E; --warn-wash:#2E2410;
  --crit:#EE7AA4; --crit-wash:#341421;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --paper:#0B1013; --surface:#131B1F; --surface-2:#1B252A; --surface-3:#222E34;
  --ink:#E3ECEE; --ink-2:#8CA1A8; --ink-3:#71868D; --rule:#222E33; --rule-2:#314147;
  --accent:#4FC0E4; --accent-wash:#0E2C38;
  --good:#5FC79C; --good-wash:#0F2A20;
  --warn:#D6A93E; --warn-wash:#2E2410;
  --crit:#EE7AA4; --crit-wash:#341421;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:14.5px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em}
.num{font-variant-numeric:tabular-nums}

header.top{position:sticky;top:0;z-index:10;background:var(--surface);
  border-bottom:1px solid var(--rule);padding:0 22px;
  display:flex;align-items:center;gap:20px;flex-wrap:wrap;min-height:54px}
.brand{font-weight:700;letter-spacing:-.01em;font-size:15px;white-space:nowrap}
.brand span{color:var(--accent)}
nav.top a{padding:6px 0;color:var(--ink-2);font-size:13.5px;font-weight:500;margin-right:16px}
nav.top a.on{color:var(--ink);box-shadow:inset 0 -2px 0 var(--accent)}
.spacer{flex:1}
form.find{display:flex;gap:0}
form.find input{border:1px solid var(--rule-2);background:var(--paper);color:var(--ink);
  padding:6px 10px;border-radius:4px 0 0 4px;font-size:13px;width:200px;outline-offset:2px}
form.find button{border:1px solid var(--rule-2);border-left:0;background:var(--surface-2);
  color:var(--ink-2);padding:6px 12px;border-radius:0 4px 4px 0;font-size:13px;cursor:pointer}
main{padding:22px;max-width:1360px;margin:0 auto}
h1{font-size:19px;margin:0 0 3px;letter-spacing:-.015em}
.sub{color:var(--ink-3);font-size:13px;margin:0 0 20px}
h2{font-size:13px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);
  margin:30px 0 11px;font-weight:600}

.banner{display:flex;align-items:center;gap:12px;padding:11px 16px;border-radius:5px;
  margin-bottom:18px;font-size:13.5px;border:1px solid}
.banner.stop{background:var(--crit-wash);border-color:var(--crit);color:var(--crit);font-weight:600}
.banner form{margin-left:auto}
.btn{border:1px solid var(--rule-2);background:var(--surface);color:var(--ink);
  padding:7px 14px;border-radius:5px;font-size:13px;font-weight:600;cursor:pointer}
.btn.danger{border-color:var(--crit);color:var(--crit);background:var(--crit-wash)}
.btn.calm{border-color:var(--good);color:var(--good);background:var(--good-wash)}

.tiles{display:grid;grid-template-columns:repeat(2,1fr);
  gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:6px;overflow:hidden}
@media (min-width:620px){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{background:var(--surface);padding:13px 15px 15px;min-height:118px;
  display:flex;flex-direction:column}
/* Feste Hoehe fuer die Verlaufszeile, damit alle Kacheln auf einer Linie liegen. */
.tile .spark{height:26px;margin-bottom:6px}
.tile .lbl{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);
  margin-bottom:8px;line-height:1.3}
.tile .val{font-size:27px;font-weight:700;line-height:1;letter-spacing:-.03em;margin-bottom:5px}
.tile .val small{font-size:15px;font-weight:600;color:var(--ink-3);letter-spacing:0}
.tile .sub2{font-size:11.5px;color:var(--ink-3);line-height:1.35;margin-top:auto}
.tile .val.good{color:var(--good)} .tile .val.warn{color:var(--warn)} .tile .val.crit{color:var(--crit)}
.tile .spark svg{display:block}

.panel{background:var(--surface);border:1px solid var(--rule);border-radius:6px;
  overflow:hidden;box-shadow:var(--shadow)}
.panel .ph{padding:10px 15px;border-bottom:1px solid var(--rule);background:var(--surface-2);
  font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);font-weight:600;
  display:flex;align-items:center;gap:10px}
.panel .ph .right{margin-left:auto;font-weight:500;color:var(--ink-3);letter-spacing:.02em;
  text-transform:none;font-size:12px}
.panel .body{padding:15px}
.cols{display:grid;gap:16px;grid-template-columns:1fr}
@media (min-width:980px){.cols.two{grid-template-columns:1.35fr 1fr}}

table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:8px 14px;border-bottom:1px solid var(--rule);vertical-align:middle}
thead th{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);
  background:var(--surface-2);font-weight:600;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--surface-2)}
td.r,th.r{text-align:right}
.tw{overflow-x:auto}

.chip{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:700;
  letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:3px;
  border:1px solid;white-space:nowrap}
.chip::before{content:"";width:6px;height:6px;border-radius:1px;background:currentColor}
.chip.good{background:var(--good-wash);color:var(--good);border-color:var(--good)}
.chip.warn{background:var(--warn-wash);color:var(--warn);border-color:var(--warn)}
.chip.crit{background:var(--crit-wash);color:var(--crit);border-color:var(--crit)}
.chip.calm{background:var(--surface-2);color:var(--ink-2);border-color:var(--rule-2)}
.chip.info{background:var(--accent-wash);color:var(--accent);border-color:var(--accent)}

.board{display:grid;grid-template-columns:repeat(auto-fill,minmax(74px,1fr));gap:9px}
.cell{display:block;border:1px solid var(--rule-2);border-radius:4px;background:var(--surface-2);
  padding:7px 7px 6px;position:relative;overflow:hidden;color:inherit}
.cell:hover{border-color:var(--accent);text-decoration:none}
.cell::after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px}
.cell.ok::after{background:var(--good)} .cell.ok{background:var(--good-wash)}
.cell.soft::after{background:var(--warn)} .cell.soft{background:var(--warn-wash)}
.cell.hard::after{background:var(--crit)} .cell.hard{background:var(--crit-wash)}
.cell.done::after{background:var(--accent)} .cell.done{background:var(--accent-wash)}
.cell .nm{font-size:11px;font-weight:600;line-height:1.2;overflow:hidden;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;min-height:26px}
.cell .st{font-size:9px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);
  margin-top:4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.cell .cp{position:absolute;top:5px;right:6px;font-size:8.5px;font-weight:700;
  color:var(--ink-3);font-variant-numeric:tabular-nums}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px;font-size:12px;color:var(--ink-2)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}

dl.kv{display:grid;grid-template-columns:auto 1fr;gap:7px 16px;margin:0;font-size:13px}
dl.kv dt{color:var(--ink-3)} dl.kv dd{margin:0;font-weight:500;word-break:break-word}
ol.trail{list-style:none;margin:0;padding:0;font-size:12.5px}
ol.trail li{padding:7px 0;border-bottom:1px solid var(--rule);display:grid;
  grid-template-columns:150px 1fr;gap:12px}
ol.trail li:last-child{border-bottom:0}
ol.trail .t{color:var(--ink-3);font-variant-numeric:tabular-nums}
.empty{color:var(--ink-3);font-size:13px;padding:18px 0;text-align:center}
footer{padding:26px 22px;color:var(--ink-3);font-size:11.5px;text-align:center}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


def page(title: str, active: str, body: str, query: str = "") -> str:
    tabs = [("/", "Übersicht"), ("/auftraege", "Aufträge"), ("/queues", "Arbeitsvorrat")]
    nav = "".join(
        f'<a href="{href}" class="{"on" if active == href else ""}">{escape(label)}</a>'
        for href, label in tabs)
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{escape(title)} · Cockpit</title><style>{CSS}</style></head><body>
<header class="top">
  <div class="brand">Trading-Card-<span>Engine</span></div>
  <nav class="top">{nav}</nav>
  <div class="spacer"></div>
  <form class="find" action="/suche" method="get" role="search">
    <input name="q" value="{escape(query)}" placeholder="Name, Auftrag oder QR-Code"
           aria-label="Suche">
    <button type="submit">Suchen</button>
  </form>
</header>
<main>{body}</main>
<footer>Aktualisiert sich alle 30 Sekunden · Alle Werte kommen aus den Sichten der Datenbank</footer>
<script>setTimeout(function(){{location.reload();}}, 30000);</script>
</body></html>"""


# ----------------------------------------------------------------- Kacheln

def tile(label: str, value: str, small: str = "", tone: str = "",
         sub: str = "", spark: str = "") -> str:
    """Kachel: Beschriftung, Zahl, optionale Einheit, Verlauf und Erläuterung.

    Reihenfolge folgt der Leserichtung der Kachel, damit die Aufrufe an der
    Aufrufstelle lesbar bleiben.
    """
    suffix = f"<small> {escape(small)}</small>" if small else ""
    return (f'<div class="tile"><div class="lbl">{escape(label)}</div>'
            f'<div class="spark">{spark}</div>'
            f'<div class="val {tone} num">{escape(value)}{suffix}</div>'
            f'<div class="sub2">{sub}</div></div>')


def sparkline(points: list[float], colour: str, width: int = 150, height: int = 26) -> str:
    """Winzige Verlaufskurve in der Kachel - eine Reihe, kein Gitter, kein Text."""
    values = [p for p in points if p is not None]
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / (len(points) - 1)
    coords, last = [], None
    for i, p in enumerate(points):
        if p is None:
            continue
        x = i * step
        y = height - 2 - (p - lo) / span * (height - 5)
        coords.append(f"{x:.1f},{y:.1f}")
        last = (x, y)
    if not coords:
        return ""
    end = (f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="2.6" fill="{colour}"/>'
           if last else "")
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{" ".join(coords)}" fill="none" stroke="{colour}" '
            f'stroke-width="2" vector-effect="non-scaling-stroke" '
            f'stroke-linejoin="round" stroke-linecap="round"/>{end}</svg>')


# ----------------------------------------------------------------- Diagramm

def photo_trend_chart(rows: list[dict], threshold: float = 8.0) -> str:
    """Ausschussquote über 14 Tage.

    Eine Reihe, kein Stapel: Der Betreiber fragt nicht nach der Verteilung von
    A, B und C, sondern ob der Ausschuss steigt. Damit entfaellt auch das
    Farbproblem - drei benachbarte Statustoene sind bei Farbenblindheit nicht
    sicher trennbar, eine einzelne Flaeche schon.
    """
    if not rows:
        return '<div class="empty">Noch keine Prüfungen erfasst.</div>'

    w, h = 640, 190
    pad_l, pad_r, pad_t, pad_b = 34, 76, 14, 26
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    values = [float(r["class_c_pct"] or 0) for r in rows]
    top = max(max(values), threshold) * 1.25 or 10
    step = plot_w / max(len(rows) - 1, 1)

    def yy(v: float) -> float:
        return pad_t + plot_h - (v / top) * plot_h

    pts = [(pad_l + i * step, yy(v)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"{pad_l},{pad_t + plot_h} " + line +
            f" {pad_l + (len(pts) - 1) * step:.1f},{pad_t + plot_h}")

    grid = "".join(
        f'<line x1="{pad_l}" y1="{yy(v):.1f}" x2="{w - pad_r}" y2="{yy(v):.1f}" '
        f'stroke="var(--rule)" stroke-width="1"/>'
        f'<text x="{pad_l - 7}" y="{yy(v) + 3.5:.1f}" text-anchor="end" font-size="10" '
        f'fill="var(--ink-3)">{v:g}%</text>'
        for v in (0, top / 2, top))

    ticks = "".join(
        f'<text x="{pad_l + i * step:.1f}" y="{h - 8}" text-anchor="middle" font-size="10" '
        f'fill="var(--ink-3)">{escape(str(r["day"])[8:10])}.</text>'
        for i, r in enumerate(rows) if i % 3 == 0 or i == len(rows) - 1)

    # Beruehrflaechen mit nativem Kurztext - Hoverschicht ohne Skript.
    hits = "".join(
        f'<rect x="{pad_l + i * step - step / 2:.1f}" y="{pad_t}" width="{step:.1f}" '
        f'height="{plot_h}" fill="transparent">'
        f'<title>{escape(str(r["day"]))}: {values[i]:g} % Ausschuss '
        f'({r["class_c"]} von {r["assessed"]})</title></rect>'
        for i, r in enumerate(rows))

    ex, ey = pts[-1]
    return f"""<svg viewBox="0 0 {w} {h}" width="100%" height="auto" role="img"
  aria-label="Ausschussquote der letzten 14 Tage, aktuell {values[-1]:g} Prozent bei einer Schwelle von {threshold:g} Prozent">
  {grid}
  <line x1="{pad_l}" y1="{yy(threshold):.1f}" x2="{w - pad_r}" y2="{yy(threshold):.1f}"
        stroke="var(--ink-3)" stroke-width="1" stroke-dasharray="4 3"/>
  <text x="{w - pad_r + 5}" y="{yy(threshold) + 3.5:.1f}" font-size="10"
        fill="var(--ink-3)">Schwelle</text>
  <polygon points="{area}" fill="{MARK_CRITICAL}" fill-opacity="0.13"/>
  <polyline points="{line}" fill="none" stroke="{MARK_CRITICAL}" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{MARK_CRITICAL}"
          stroke="var(--surface)" stroke-width="2"/>
  <text x="{ex + 8:.1f}" y="{ey + 4:.1f}" font-size="12" font-weight="700"
        fill="var(--ink)">{values[-1]:g}%</text>
  {ticks}{hits}
</svg>"""
