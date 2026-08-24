"""Die Seite, die nach dem Scannen erscheint.

Selbsttragend: keine externen Schriften, keine Skripte von aussen, keine
Bilder von anderen Servern. Das haelt die Sicherheitsregeln des Dienstes
streng und die Seite auch in schlechtem Netz schnell.
"""
from __future__ import annotations

from html import escape

ROLE_LABEL = {"FIELD": "Feldspieler", "KEEPER": "Torwart",
              "COACH": "Trainer", "STAFF": "Betreuer"}

_BASE = """*{box-sizing:border-box}
:root{--bg:#0d1417;--card:#151f24;--ink:#eef5f7;--ink-2:#93a9b1;--accent:#4fc0e4;--rule:#223036}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);
  font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  display:flex;flex-direction:column;align-items:center;
  padding:28px 20px 40px;-webkit-font-smoothing:antialiased}
.wrap{width:100%;max-width:420px}
"""

PAGE = _BASE + """
.eyebrow{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);
  text-align:center;margin-bottom:18px;font-weight:600}
.stage{perspective:1400px;margin-bottom:14px}
.flip{position:relative;width:100%;aspect-ratio:63/88;
  transition:transform .55s cubic-bezier(.4,.15,.2,1);transform-style:preserve-3d;
  cursor:pointer;border:0;padding:0;background:none;display:block}
.flip.turned{transform:rotateY(180deg)}
.face{position:absolute;inset:0;backface-visibility:hidden;border-radius:12px;
  overflow:hidden;box-shadow:0 18px 44px -18px rgba(0,0,0,.85),0 2px 6px rgba(0,0,0,.4)}
.face.back{transform:rotateY(180deg)}
.face svg,.face img{width:100%;height:100%;display:block}
.hint{text-align:center;font-size:12.5px;color:var(--ink-2);margin:0 0 22px}
h1{font-size:24px;line-height:1.15;margin:0 0 4px;text-align:center;letter-spacing:-.02em}
.sub{text-align:center;color:var(--ink-2);font-size:14.5px;margin:0 0 20px}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--rule);
  border:1px solid var(--rule);border-radius:8px;overflow:hidden;margin-bottom:22px}
.fact{background:var(--card);padding:11px 13px}
.fact dt{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2);margin:0 0 3px}
.fact dd{margin:0;font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.actions{display:flex;flex-direction:column;gap:10px}
.btn{display:block;text-align:center;padding:13px 16px;border-radius:9px;
  text-decoration:none;font-size:15px;font-weight:600;border:1px solid var(--accent)}
.btn.primary{background:var(--accent);color:#06222c}
.btn.ghost{color:var(--accent)}
.foot{margin-top:26px;text-align:center;font-size:11.5px;color:var(--ink-2);line-height:1.6}
.foot code{font-size:11px;opacity:.8}
@media (prefers-reduced-motion:reduce){.flip{transition:none}}
"""

GONE_CSS = _BASE + """
.box{background:var(--card);border:1px solid var(--rule);border-radius:12px;
  padding:30px 26px;text-align:center;margin-top:12vh}
h1{font-size:20px;margin:0 0 12px;letter-spacing:-.01em}
p{color:var(--ink-2);font-size:14.5px;margin:0 0 10px}
p:last-child{margin:0}
.mark{width:44px;height:44px;border-radius:50%;border:2px solid var(--rule);
  margin:0 auto 18px;display:flex;align-items:center;justify-content:center;
  color:var(--ink-2);font-size:20px}
"""


def _fact(label: str, value: str) -> str:
    return (f'<div class="fact"><dt>{escape(label)}</dt>'
            f'<dd>{escape(str(value))}</dd></div>')


def card_page(data: dict, front_svg: str | None, back_svg: str | None,
              token: str, base: str = "") -> str:
    name = data.get("player_name", "")
    club = data.get("club_name", "")
    season = data.get("season", "")
    team = data.get("team_name", "")
    role = ROLE_LABEL.get(data.get("role", ""), data.get("role", "") or "")
    number = data.get("jersey_number")
    card_no, card_total = data.get("card_number"), data.get("card_total")

    facts = []
    if role:
        facts.append(_fact("Position", role))
    if number:
        facts.append(_fact("Rückennummer", number))
    if season:
        facts.append(_fact("Saison", season))
    if card_no and card_total and card_total > 1:
        facts.append(_fact("Ausgabe", f"{card_no} von {card_total}"))
    elif team:
        facts.append(_fact("Mannschaft", team))

    def face(svg: str | None, side: str, cls: str) -> str:
        if svg:
            return f'<div class="face {cls}">{svg}</div>'
        return (f'<div class="face {cls}" style="background:#1d2a30;display:flex;'
                f'align-items:center;justify-content:center;color:#7b8f97;font-size:13px">'
                f'{escape(side)}</div>')

    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#0d1417">
<title>{escape(name)} · Sammelkarte</title>
<style>{PAGE}</style></head><body><div class="wrap">
<p class="eyebrow">Deine digitale Karte</p>
<div class="stage">
  <button class="flip" id="flip" aria-label="Karte umdrehen">
    {face(front_svg, "Vorderseite", "front")}
    {face(back_svg, "Rückseite", "back")}
  </button>
</div>
<p class="hint">Tippen zum Umdrehen</p>
<h1>{escape(name)}</h1>
<p class="sub">{escape(club)}{(' · ' + escape(team)) if team else ''}</p>
<dl class="facts">{''.join(facts)}</dl>
<div class="actions">
  <a class="btn primary" href="{base}/k/{escape(token)}/download">Karte speichern</a>
  <a class="btn ghost" href="{base}/k/{escape(token)}/back.svg">Rückseite einzeln ansehen</a>
</div>
<p class="foot">Diese Seite zeigt ausschließlich diese eine Karte.<br>
Keine anderen Spieler, keine Kontaktdaten.<br>
<code>{escape(token)}</code></p>
</div>
<script>
(function(){{
  var f=document.getElementById('flip');
  if(!f)return;
  f.addEventListener('click',function(){{f.classList.toggle('turned');}});
}})();
</script>
</body></html>"""


def gone_page() -> str:
    """Eine Antwort fuer alle Faelle: unbekannt, widerrufen, noch nicht gedruckt.

    Verraet nichts darueber, welcher davon zutrifft.
    """
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="referrer" content="no-referrer">
<title>Karte nicht verfügbar</title>
<style>{GONE_CSS}</style></head><body><div class="wrap"><div class="box">
<div class="mark" aria-hidden="true">—</div>
<h1>Diese Karte ist nicht verfügbar</h1>
<p>Der Code gehört zu keiner abrufbaren Karte, oder die Karte wurde zurückgezogen.</p>
<p>Wenn du meinst, das sei ein Fehler, wende dich an deinen Verein.</p>
</div></div></body></html>"""
