"""Das Admin-Cockpit.

Drei Flughoehen: Zustand der Fabrik, Arbeitsvorrat, Forensik am Einzelfall.
Lesend bis auf eine Ausnahme - den Not-Aus, der die Uebertragung an die
Druckerei anhaelt. Er wirkt in der Datenbank, nicht hier, damit ihn auch ein
Hintergrunddienst nicht umgehen kann.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cockpit.store import CockpitStore
from cockpit.ui import (MARK_CRITICAL, MARK_GOOD, de, page, photo_trend_chart,
                        short, sparkline, tile)

HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


# ------------------------------------------------------------------ Format

def dur(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{seconds // 60} min"
    if seconds < 172800:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} Tage"


def ago(stamp: str | None) -> str:
    if not stamp:
        return "—"
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return escape(str(stamp)[:16])
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return "vor " + dur((datetime.now(timezone.utc) - then).total_seconds())


def until(stamp: str | None) -> tuple[str, str]:
    """Verbleibende Zeit plus Tonfall - Puffer ist die Zahl, die im Saisongeschäft zählt."""
    if not stamp:
        return "—", ""
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return escape(str(stamp)[:16]), ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = (then - datetime.now(timezone.utc)).total_seconds()
    if delta < 0:
        return "überfällig", "crit"
    return "noch " + dur(delta), ("crit" if delta < 86400 else "warn" if delta < 259200 else "")


def chip(text: str, tone: str = "calm") -> str:
    return f'<span class="chip {tone}">{escape(text)}</span>'


STATE_TONE = {"BLOCKED": "crit", "QA_FAILED": "crit", "CANCELLED": "calm",
              "DELIVERED": "info", "PRINTED": "good", "SHIPPED": "info",
              "PACKED": "good", "SENT_TO_PRINT": "good", "BATCHED": "good",
              "APPROVED": "good", "QA_PASSED": "good"}
BOARD_TONE = {"HARD": "hard", "SOFT": "soft", "DONE": "done", "OK": "ok", "CANCELLED": "soft"}


def num(value, default: str = "0") -> str:
    return default if value is None else str(value)


# ------------------------------------------------------------------ Seiten

def overview(store: CockpitStore, csrf: str) -> str:
    t = store.tiles()
    trend = store.photo_trend()
    qa = store.qa_sparkline()
    blockers = store.blocker_queue()
    orders = store.orders()

    paused = bool(t.get("transfers_paused"))
    if paused:
        banner = (f'<div class="banner stop">NOT-AUS AKTIV — es geht nichts an die Druckerei'
                  f'<form method="post" action="/ops/transfers">'
                  f'<input type="hidden" name="csrf" value="{csrf}">'
                  f'<input type="hidden" name="paused" value="false">'
                  f'<button class="btn calm" type="submit">Übertragungen freigeben</button>'
                  f'</form></div>')
    else:
        banner = (f'<div class="banner" style="background:var(--surface);'
                  f'border-color:var(--rule);color:var(--ink-2)">'
                  f'Übertragungen an die Druckerei laufen'
                  f'<form method="post" action="/ops/transfers">'
                  f'<input type="hidden" name="csrf" value="{csrf}">'
                  f'<input type="hidden" name="paused" value="true">'
                  f'<button class="btn danger" type="submit">Not-Aus</button>'
                  f'</form></div>')

    pass_rate = t.get("auto_pass_rate_pct")
    c_pct = t.get("photo_class_c_pct")
    oldest = t.get("oldest_working_seconds")
    hard, soft = t.get("blockers_hard") or 0, t.get("blockers_soft") or 0

    tiles = "".join([
        tile("Auto-Pass-Rate · 24 h",
             f'{pass_rate}' if pass_rate is not None else "—", "%" if pass_rate is not None else "",
             "good" if (pass_rate or 0) >= 99 else "warn" if pass_rate is not None else "",
             sub=f'{num(t.get("qa_verdicts_24h"))} Prüfungen · '
                 f'{num(t.get("qa_in_review"))} in Sichtprüfung',
             spark=sparkline([r["pct"] for r in qa], MARK_GOOD)),
        tile("Ausschuss Fotos · 7 Tage",
             f'{c_pct}' if c_pct is not None else "—", "%" if c_pct is not None else "",
             "crit" if (c_pct or 0) >= 8 else "warn" if (c_pct or 0) >= 5 else "good",
             sub=f'{num(t.get("photo_assessed_7d"))} geprüft · Frühindikator für die Retusche',
             spark=sparkline([float(r["class_c_pct"] or 0) for r in trend], MARK_CRITICAL)),
        tile("Offene Karten", num(t.get("cards_open")), tone="",
             sub=f'{num(t.get("cards_printed"))} gedruckt'),
        tile("Blocker", str(hard), tone="crit" if hard else "good", small=f"/ {soft}",
             sub=f'{hard} hart (Rechtsrisiko) · {soft} weich (Arbeit)'),
        tile("Fotos ausstehend", num(t.get("photos_pending")),
             tone="warn" if (t.get("photos_pending") or 0) else "good",
             sub="Hauptquelle für Wellen-Splits"),
        tile("Ältester Vorgang", dur(oldest),
             tone="crit" if (oldest or 0) > 900 else "warn" if (oldest or 0) > 300 else "good",
             sub="Alter ist das Alarmsignal, nicht die Tiefe"),
        tile("Batches unquittiert", num(t.get("batches_unacknowledged")),
             tone="crit" if (t.get("batches_unacknowledged") or 0) else "good",
             sub=f'{num(t.get("batches_open"))} offen in Bildung'),
        tile("Ausgang gestört", num(t.get("outbox_failed")),
             tone="crit" if (t.get("outbox_failed") or 0) else "good",
             sub=f'{num(t.get("outbox_pending"))} wartend · '
                 f'{num(t.get("changes_open"))} Änderungsanträge'),
    ])

    risk = [o for o in orders if o.get("derived_status") not in ("COMPLETE", "CLOSED", "CANCELLED")]
    def risk_row(o: dict) -> str:
        label, tone = until(o["promised_delivery_at"])
        soft = o["items_with_blocker"] - o["items_hard_blocked"]
        marks = ""
        if o["items_hard_blocked"]:
            marks += chip(str(o["items_hard_blocked"]), "crit")
        if soft > 0:
            marks += chip(str(soft), "warn")
        return (f'<tr><td><a href="/auftrag/{o["team_order_id"]}">{escape(o["club_name"])}</a>'
                f'<div style="color:var(--ink-3);font-size:11.5px">'
                f'{escape(o["team_name"] or "")} · {escape(o["external_ref"])}</div></td>'
                f'<td>{chip(de(o["derived_status"]), "warn" if o["derived_status"] == "PARTIALLY_COMPLETE" else "calm")}</td>'
                f'<td class="r num">{o["items_total"]}</td>'
                f'<td class="r">{marks}</td>'
                f'<td class="r num">{chip(label, tone) if tone else escape(label)}</td></tr>')

    risk_rows = "".join(risk_row(o) for o in risk[:8])

    blocker_rows = "".join(
        f'<tr><td>{chip(de(b["severity"]), "crit" if b["severity"] == "HARD" else "warn")}</td>'
        f'<td>{escape(b["label_de"])}</td>'
        f'<td>{escape(de(b["owner"]))}</td>'
        f'<td class="r num">{b["open_count"]}</td>'
        f'<td class="r num" style="color:var(--ink-3)">{ago(b["oldest_opened_at"])}</td></tr>'
        for b in blockers) or '<tr><td colspan="5" class="empty">Keine offenen Blocker.</td></tr>'

    current = float(trend[-1]["class_c_pct"] or 0) if trend else 0
    earlier = float(trend[0]["class_c_pct"] or 0) if trend else 0
    direction = ("steigt" if current > earlier + 0.5 else
                 "fällt" if current < earlier - 0.5 else "stabil")

    return f"""<h1>Übersicht</h1>
<p class="sub">Jede Kachel soll eine Entscheidung auslösen können — sonst ist sie Dekoration.</p>
{banner}
<div class="tiles">{tiles}</div>

<div class="cols two" style="margin-top:22px">
  <div class="panel">
    <div class="ph">Ausschussquote der Fotos · 14 Tage
      <span class="right">{direction} · {earlier:g} % → {current:g} %</span></div>
    <div class="body">{photo_trend_chart(trend)}
      <p style="font-size:12.5px;color:var(--ink-3);margin:12px 0 0">
        Kippt diese Kurve, steigt die Retusche-Last etwa drei Tage später. Deshalb steht sie
        neben der Auto-Pass-Rate und nicht in einem Bericht.</p>
    </div>
  </div>
  <div class="panel">
    <div class="ph">Offene Blocker <span class="right">nach Grund</span></div>
    <div class="tw"><table>
      <thead><tr><th>Schwere</th><th>Grund</th><th>Zuständig</th>
        <th class="r">Offen</th><th class="r">Ältester</th></tr></thead>
      <tbody>{blocker_rows}</tbody></table></div>
  </div>
</div>

<h2>Aufträge in Produktion</h2>
<div class="panel"><div class="tw"><table>
  <thead><tr><th>Verein</th><th>Status</th><th class="r">Karten</th>
    <th class="r">Blocker</th><th class="r">Puffer</th></tr></thead>
  <tbody>{risk_rows or '<tr><td colspan="5" class="empty">Nichts in Produktion.</td></tr>'}</tbody>
</table></div></div>"""


def orders_page(store: CockpitStore) -> str:
    rows = "".join(
        f'<tr><td><a href="/auftrag/{o["team_order_id"]}">{escape(o["club_name"])}</a></td>'
        f'<td>{escape(o["team_name"] or "")}</td><td class="mono">{escape(o["external_ref"])}</td>'
        f'<td>{chip(de(o["derived_status"]), "info" if o["derived_status"] in ("COMPLETE", "CLOSED") else "calm")}</td>'
        f'<td class="r num">{o["items_total"]}</td>'
        f'<td class="r num">{o["items_delivered"]}</td>'
        f'<td class="r num">{o["items_with_blocker"]}</td>'
        f'<td class="r">{escape(until(o["promised_delivery_at"])[0])}</td></tr>'
        for o in store.orders())
    return f"""<h1>Aufträge</h1><p class="sub">Der Produktionsstatus wird abgeleitet, nie gepflegt.</p>
<div class="panel"><div class="tw"><table>
  <thead><tr><th>Verein</th><th>Mannschaft</th><th>Referenz</th><th>Status</th>
    <th class="r">Karten</th><th class="r">Geliefert</th><th class="r">Blocker</th>
    <th class="r">Puffer</th></tr></thead>
  <tbody>{rows or '<tr><td colspan="8" class="empty">Noch keine Aufträge.</td></tr>'}</tbody>
</table></div></div>"""


def board_page(store: CockpitStore, order_id: str) -> str | None:
    head = store.order_head(order_id)
    if not head:
        return None
    cards = store.board(order_id)
    counts = {"OK": 0, "SOFT": 0, "HARD": 0, "DONE": 0, "CANCELLED": 0}
    for c in cards:
        counts[c["board_status"]] = counts.get(c["board_status"], 0) + 1

    def cell(c: dict) -> str:
        # Mehrere Kopien derselben Karte sehen sonst wie Dubletten aus.
        total = c.get("quantity") or 1
        badge = (f'<div class="cp">{c["copy_index"]}/{total}</div>' if total > 1 else "")
        return (f'<a class="cell {BOARD_TONE.get(c["board_status"], "ok")}" '
                f'href="/karte/{c["card_item_id"]}" '
                f'title="{escape(c["player_name"])} — {escape(de(c["state"]))}">'
                f'{badge}<div class="nm">{escape(c["player_name"])}</div>'
                f'<div class="st">{escape(short(c["state"]))}</div></a>')

    cells = "".join(cell(c) for c in cards)

    return f"""<h1>{escape(head["club_name"])} · {escape(head["team_name"] or "")}</h1>
<p class="sub">{escape(head["external_ref"])} · Saison {escape(head["season"] or "")} ·
  {head["items_total"]} Karten · Puffer {escape(until(head["promised_delivery_at"])[0])}</p>
<div class="panel"><div class="ph">Team-Board
  <span class="right">{counts["OK"] + counts["DONE"]} in Ordnung ·
  {counts["SOFT"]} weich blockiert · {counts["HARD"]} hart blockiert</span></div>
<div class="body">
  <div class="board">{cells or '<div class="empty">Keine Karten.</div>'}</div>
  <div class="legend">
    <span><i style="background:var(--good)"></i>in Ordnung</span>
    <span><i style="background:var(--accent)"></i>ausgeliefert</span>
    <span><i style="background:var(--warn)"></i>weicher Blocker — Arbeit</span>
    <span><i style="background:var(--crit)"></i>harter Blocker — Rechtsrisiko</span>
    <span style="color:var(--ink-3)">Klick öffnet die Karten-Historie</span>
  </div>
</div></div>"""


def card_page(store: CockpitStore, card_id: str) -> str | None:
    c = store.card(card_id)
    if not c:
        return None
    blocks = store.card_blockers(card_id)
    events = store.card_events(c["correlation_id"])

    block_rows = "".join(
        f'<tr><td>{chip(de(b["severity"]), "crit" if b["severity"] == "HARD" else "warn")}</td>'
        f'<td>{escape(b["label_de"])}</td><td>{escape(de(b["owner"]))}</td>'
        f'<td>{ago(b["opened_at"])}</td>'
        f'<td>{chip("offen", "warn") if not b["resolved_at"] else chip("gelöst", "good")}</td></tr>'
        for b in blocks) or '<tr><td colspan="5" class="empty">Keine Blocker.</td></tr>'

    trail = "".join(
        f'<li><span class="t">{escape(str(e["occurred_at"])[:19].replace("T", " "))}</span>'
        f'<span><b>{escape(e["event_type"])}</b>'
        f'<span style="color:var(--ink-3)"> · {escape(e["actor"] or "")}</span></span></li>'
        for e in events) or '<li class="empty">Keine Ereignisse.</li>'

    fp = c.get("artifact_fingerprint")
    return f"""<h1>{escape(c["player_name"])}</h1>
<p class="sub">{escape(c["club_name"])} · {escape(c["team_name"] or "")} ·
  Karte {c["copy_index"]} von {c["quantity"]} ·
  <a href="/auftrag/{c["team_order_id"]}">zurück zum Team-Board</a></p>
<div class="cols two">
  <div class="panel"><div class="ph">Karte</div><div class="body">
    <dl class="kv">
      <dt>Zustand</dt><dd>{chip(de(c["state"]), STATE_TONE.get(c["state"], "calm"))}</dd>
      <dt>Design</dt><dd>{escape(c["design_family"])} @ {escape(c["design_version"])}</dd>
      <dt>Druckspezifikation</dt><dd>{escape(c["print_spec_id"])}</dd>
      <dt>Rolle</dt><dd>{escape(de(c["player_role"]))}</dd>
      <dt>Minderjährig</dt><dd>{"ja" if c["is_minor"] else "nein"}</dd>
      <dt>Foto-Klasse</dt><dd>{escape(c["photo_quality_class"] or "—")}</dd>
      <dt>QR-Token</dt><dd class="mono">{escape(c["qr_token"] or "—")}</dd>
      <dt>Artefakt</dt><dd class="mono">{escape(fp[:24] + "…") if fp else "noch nicht gerendert"}</dd>
      <dt>Konfektionierung</dt><dd class="mono">{escape(c["recipient_group_key"])}</dd>
      <dt>Vorgang</dt><dd class="mono">{escape(str(c["correlation_id"])[:8])}…</dd>
    </dl></div></div>
  <div class="panel"><div class="ph">Blocker</div><div class="tw"><table>
    <thead><tr><th>Schwere</th><th>Grund</th><th>Zuständig</th><th>Seit</th><th>Stand</th></tr></thead>
    <tbody>{block_rows}</tbody></table></div></div>
</div>
<h2>Spur des Vorgangs</h2>
<div class="panel"><div class="body"><ol class="trail">{trail}</ol></div></div>"""


def queues_page(store: CockpitStore) -> str:
    outbox = store.outbox()
    changes = store.changes()
    batches = store.batches()

    ob = "".join(
        f'<tr><td>{escape(de(o["channel"]))}</td>'
        f'<td>{chip(de(o["state"]), "crit" if o["state"] in ("FAILED", "ABANDONED") else "good" if o["state"] == "SENT" else "calm")}</td>'
        f'<td class="r num">{o["eintraege"]}</td><td class="r num">{o["meiste_versuche"]}</td>'
        f'<td style="color:var(--ink-3);font-size:12px">{escape(o["letzter_fehler"] or "")}</td></tr>'
        for o in outbox) or '<tr><td colspan="5" class="empty">Ausgang leer.</td></tr>'

    ch = "".join(
        f'<tr><td>{escape(c["display_name"] or "—")}</td><td class="mono">{escape(c["external_ref"])}</td>'
        f'<td>{escape(c["field"])}</td>'
        f'<td style="color:var(--ink-3)">{escape(c["old_value"] or "")}</td>'
        f'<td><b>{escape(c["new_value"] or "")}</b></td>'
        f'<td class="r">{ago(c["detected_at"])}</td></tr>'
        for c in changes) or '<tr><td colspan="6" class="empty">Keine offenen Änderungsanträge.</td></tr>'

    bt = "".join(
        f'<tr><td class="mono">{escape(str(b["id"])[:8])}…</td><td>{escape(b["print_spec_id"])}</td>'
        f'<td>{chip(de(b["state"]), "good" if b["state"] in ("TRANSFERRED", "PRINTED") else "calm")}</td>'
        f'<td class="r num">{b["cards"]}</td>'
        f'<td class="r">{chip(dur_from(b["unacknowledged_for"]), "crit") if b["unacknowledged_for"] else "—"}</td></tr>'
        for b in batches) or '<tr><td colspan="5" class="empty">Keine Batches.</td></tr>'

    return f"""<h1>Arbeitsvorrat</h1>
<p class="sub">Aufgaben, keine Protokolle. Alter zählt mehr als Menge.</p>
<h2>Ausgang an Druckerei, Partner und Kunden</h2>
<div class="panel"><div class="tw"><table>
  <thead><tr><th>Kanal</th><th>Stand</th><th class="r">Einträge</th>
    <th class="r">Versuche</th><th>Letzter Fehler</th></tr></thead>
  <tbody>{ob}</tbody></table></div></div>

<h2>Änderungsanträge nach Auftragsannahme</h2>
<div class="panel">
  <div class="ph">Kommt eine Korrektur nach der Annahme, wird sie nicht still übernommen</div>
  <div class="tw"><table>
  <thead><tr><th>Person</th><th>Auftrag</th><th>Feld</th><th>Bisher</th><th>Vorgeschlagen</th>
    <th class="r">Erkannt</th></tr></thead>
  <tbody>{ch}</tbody></table></div></div>

<h2>Druck-Batches</h2>
<div class="panel"><div class="tw"><table>
  <thead><tr><th>Batch</th><th>Spezifikation</th><th>Stand</th><th class="r">Karten</th>
    <th class="r">Unquittiert</th></tr></thead>
  <tbody>{bt}</tbody></table></div></div>"""


def dur_from(interval: str | None) -> str:
    """Postgres-Intervall grob in Text - fuer die Anzeige reicht das."""
    if not interval:
        return "—"
    text = str(interval)
    if ":" in text:
        head = text.split(":")[0].strip()
        try:
            return f"{int(head.split()[-1])} h"
        except (ValueError, IndexError):
            return text[:14]
    return text[:14]


def search_page(store: CockpitStore, term: str) -> str:
    found = store.search(term)
    rows = "".join(
        f'<tr><td><a href="/karte/{r["card_item_id"]}">{escape(r["player_name"])}</a></td>'
        f'<td>{escape(r["club_name"])}</td><td>{escape(r["team_name"] or "")}</td>'
        f'<td class="mono">{escape(r["order_ref"])}</td>'
        f'<td>{chip(de(r["state"]), STATE_TONE.get(r["state"], "calm"))}</td>'
        f'<td class="mono" style="font-size:11.5px">{escape(r["qr_token"] or "—")}</td></tr>'
        for r in found)
    hint = ("" if found else
            '<div class="empty">Nichts gefunden. Gesucht wird in Spielernamen, '
            'Auftragsreferenzen und QR-Codes.</div>')
    return f"""<h1>Suche</h1><p class="sub">{len(found)} Treffer für „{escape(term)}“ ·
  Ein Kunde ruft an und liest den Code von der Rückseite vor — die Suche muss darauf
  genauso reagieren wie auf einen Namen.</p>
<div class="panel"><div class="tw"><table>
  <thead><tr><th>Person</th><th>Verein</th><th>Mannschaft</th><th>Auftrag</th>
    <th>Zustand</th><th>QR-Code</th></tr></thead>
  <tbody>{rows}</tbody></table></div>{hint}</div>"""


# ------------------------------------------------------------------ Server

def make_handler(store: CockpitStore, csrf: str, actor: str = "cockpit"):

    class Handler(BaseHTTPRequestHandler):
        server_version = "card-cockpit/1.0"
        sys_version = ""

        def log_message(self, fmt: str, *args) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8",
                  extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in {**HEADERS, **(extra or {})}.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _html(self, code: int, html: str) -> None:
            self._send(code, html.encode("utf-8"))

        def _404(self) -> None:
            self._html(404, page("Nicht gefunden", "", "<h1>Nicht gefunden</h1>"
                                 '<p class="sub">Diese Seite gibt es nicht.</p>'))

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            url = urlparse(self.path)
            path = url.path.rstrip("/") or "/"
            query = parse_qs(url.query)
            try:
                if path == "/":
                    self._html(200, page("Übersicht", "/", overview(store, csrf)))
                elif path == "/auftraege":
                    self._html(200, page("Aufträge", "/auftraege", orders_page(store)))
                elif path == "/queues":
                    self._html(200, page("Arbeitsvorrat", "/queues", queues_page(store)))
                elif path == "/suche":
                    term = (query.get("q") or [""])[0]
                    self._html(200, page("Suche", "", search_page(store, term), term))
                elif path.startswith("/auftrag/"):
                    body = board_page(store, path.split("/")[-1])
                    self._html(200, page("Team-Board", "/auftraege", body)) if body else self._404()
                elif path.startswith("/karte/"):
                    body = card_page(store, path.split("/")[-1])
                    self._html(200, page("Karte", "", body)) if body else self._404()
                elif path == "/healthz":
                    self._send(200, b'{"status":"ok"}', "application/json")
                else:
                    self._404()
            except Exception as exc:  # noqa: BLE001
                self._html(500, page("Fehler", "", "<h1>Fehler</h1>"
                                     f'<p class="sub">{escape(str(exc)[:300])}</p>'))

        def do_POST(self) -> None:
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8")) if length else {}

            # Der Not-Aus ist die einzige schreibende Aktion. Ohne gueltiges
            # Formular-Merkmal passiert nichts - eine fremde Seite soll ihn
            # nicht ausloesen koennen.
            if (form.get("csrf") or [""])[0] != csrf:
                self._html(403, page("Abgelehnt", "", "<h1>Abgelehnt</h1>"
                                     '<p class="sub">Formular-Merkmal fehlt oder ist veraltet. '
                                     'Seite neu laden.</p>'))
                return

            if url.path == "/ops/transfers":
                store.set_transfers_paused((form.get("paused") or ["false"])[0] == "true", actor)
                self.send_response(303)
                self.send_header("Location", "/")
                for k, v in HEADERS.items():
                    self.send_header(k, v)
                self.end_headers()
                return
            self._404()

    return Handler


def serve(store: CockpitStore, host: str = "127.0.0.1", port: int = 8099) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port),
                               make_handler(store, secrets.token_urlsafe(24)))
