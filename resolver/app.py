"""Der Aufloesungsdienst hinter dem QR-Code.

Bewusst winzig und ohne Framework: Dieser Dienst muss noch laufen, wenn die
Engine dreimal umgebaut wurde. Er kennt genau eine Tabelle und beantwortet
genau eine Frage - welcher Karteninhalt gehoert zu diesem Token.

Sicherheitseigenschaften, die hier wirklich zaehlen:
  * Der Token wird gegen ein strenges Muster geprueft, bevor irgendetwas
    passiert.
  * Unbekannt, widerrufen und noch nicht gedruckt liefern dieselbe Antwort.
    Sonst waere der Dienst ein Orakel fuer die Existenz von Token.
  * Wiederholt abgefragte falsche Token werden gemerkt und ohne Datenbank
    beantwortet. Das ist eine KOSTEN-Bremse, keine Sicherheitsmassnahme:
    Bei 128 Bit Zufall im Token ist Durchprobieren ohnehin aussichtslos.
    Sie darf deshalb niemals einen echten Scan blockieren - genau dieser
    Fehler steckte in der ersten Fassung.
  * Kein Suchindex, kein Verweis auf andere Karten, keine Kontaktdaten.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from engine.preview import card_svg
from resolver.page import card_page, gone_page
from resolver.store import TwinStore, token_is_wellformed

# Farbwelt je Design. Kommt spaeter aus design_version.assets.
PALETTES = {
    "DESIGN-1": dict(card_bg="#12303f", subject="#8fb9cc", photo_bg="#1d4759",
                     ink="#f2f7f9", muted="#9fc0cd", on_photo="#cfe4ec",
                     guide_trim="#000", guide_bleed="#000", guide_safe="#000"),
    "DESIGN-2": dict(card_bg="#2c1a3d", subject="#b79ccd", photo_bg="#3f2757",
                     ink="#f6f2fa", muted="#c1a9d4", on_photo="#ddcdea",
                     guide_trim="#000", guide_bleed="#000", guide_safe="#000"),
    "DESIGN-3": dict(card_bg="#3a2c0d", subject="#d9be74", photo_bg="#54401a",
                     ink="#fbf5e6", muted="#d3bd8b", on_photo="#eddfbe",
                     guide_trim="#000", guide_bleed="#000", guide_safe="#000"),
    "DESIGN-4": dict(card_bg="#14331f", subject="#8fc4a3", photo_bg="#1e4a2e",
                     ink="#f0f7f2", muted="#a6cbb4", on_photo="#cfe6d8",
                     guide_trim="#000", guide_bleed="#000", guide_safe="#000"),
}
DEFAULT_PALETTE = PALETTES["DESIGN-1"]

SECURITY_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy":
        "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


class RateLimiter:
    """Deckelt die Anfragen je Aufrufer. Das ist der eigentliche Schutz."""

    def __init__(self, per_min: int = 60):
        self.per_min = per_min
        self._seen: dict[str, deque] = defaultdict(deque)

    def allow(self, who: str) -> bool:
        now = time.time()
        bucket = self._seen[who]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= self.per_min:
            return False
        bucket.append(now)
        return True


class NegativeCache:
    """Merkt sich kurz, welche Token ins Leere liefen.

    Wer denselben falschen Code hundertmal abruft, kostet uns danach keine
    Datenbankabfrage mehr. Ein Token, das hier NICHT steht, wird immer
    nachgeschlagen - eine gueltige Karte darf nie an einer Bremse haengen
    bleiben, die jemand anderes ausgeloest hat.
    """

    def __init__(self, ttl: float = 120.0, limit: int = 20000):
        self.ttl, self.limit = ttl, limit
        self._at: dict[str, float] = {}

    def known_bad(self, token: str) -> bool:
        seen = self._at.get(token)
        if seen is None:
            return False
        if time.time() - seen > self.ttl:
            self._at.pop(token, None)
            return False
        return True

    def note(self, token: str) -> None:
        now = time.time()
        if len(self._at) >= self.limit:
            for key, seen in list(self._at.items()):
                if now - seen > self.ttl:
                    self._at.pop(key, None)
            if len(self._at) >= self.limit:
                self._at.clear()
        self._at[token] = now


def render_side(store: TwinStore, data: dict, side: str) -> str | None:
    """Fertiges SVG-Element der gewuenschten Kartenseite.

    Das Bildfeld reicht bewusst bis in den Anschnitt, deshalb beginnt der
    Koordinatenrahmen bei minus der Anschnittbreite - sonst faellt der
    ueberstehende Rand des Motivs aus dem Bild.
    """
    fingerprint = data.get("fingerprint")
    if not fingerprint:
        return None
    manifest = store.manifest(fingerprint)
    if not manifest:
        return None
    palette = PALETTES.get(data.get("design_family", ""), DEFAULT_PALETTE)
    inner = card_svg(manifest, side, palette, f"r{side}", show_guides=False)

    geo = manifest["geometry"]
    bleed = geo["bleed"]
    view = (f'{-bleed} {-bleed} {geo["trim_width"] + 2 * bleed} '
            f'{geo["trim_height"] + 2 * bleed}')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" '
            f'preserveAspectRatio="xMidYMid slice" role="img" '
            f'aria-label="Sammelkarte {side}">{inner}</svg>')


def make_handler(store: TwinStore, limiter: RateLimiter,
                 misses: NegativeCache | None = None, base: str = ""):
    misses = misses if misses is not None else NegativeCache()

    class Handler(BaseHTTPRequestHandler):
        server_version = "card-resolver/1.0"
        sys_version = ""

        # ------------------------------------------------------------
        def _send(self, code: int, body: bytes, ctype: str, cache: str,
                  extra: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _gone(self) -> None:
            # 404 statt 410: auch der Statuscode soll nichts verraten.
            self._send(404, gone_page().encode("utf-8"),
                       "text/html; charset=utf-8", "no-store")

        def _client(self) -> str:
            return self.client_address[0] if self.client_address else "?"

        def log_message(self, fmt: str, *args) -> None:
            # Kein Token, keine Adresse, kein Geraet im Log. Wer scannt,
            # hinterlaesst hier keine Spur - gezaehlt wird nur in Tagessummen.
            pass

        # ------------------------------------------------------------
        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            who = self._client()
            if not limiter.allow(who):
                self._send(429, b"zu viele Anfragen", "text/plain; charset=utf-8", "no-store",
                           {"Retry-After": "60"})
                return

            path = urlparse(self.path).path.rstrip("/") or "/"

            if path == "/healthz":
                self._send(200, b'{"status":"ok"}', "application/json", "no-store")
                return

            parts = [p for p in path.split("/") if p]
            if len(parts) < 2 or parts[0] != "k":
                self._gone()
                return

            token = parts[1]
            what = parts[2] if len(parts) > 2 else ""

            # Formfehler und bereits bekannte Fehlschlaege kosten keine Abfrage.
            if not token_is_wellformed(token) or misses.known_bad(token):
                self._gone()
                return

            data = store.resolve(token)
            if data.get("status") != "OK":
                misses.note(token)
                self._gone()
                return

            if what in ("front.svg", "back.svg"):
                side = "front" if what.startswith("front") else "back"
                svg = render_side(store, data, side)
                if svg is None:
                    self._gone()
                    return
                # Der Inhalt ist an den Fingerprint gebunden und aendert sich
                # nie - also darf er beliebig lange zwischengespeichert werden.
                self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8",
                           "public, max-age=31536000, immutable")
                return

            if what == "download":
                svg = render_side(store, data, "front")
                if svg is None:
                    self._gone()
                    return
                body = svg.encode("utf-8")
                name = (data.get("player_name", "karte").replace(" ", "-").lower())
                self._send(200, body, "image/svg+xml; charset=utf-8",
                           "public, max-age=31536000, immutable",
                           {"Content-Disposition": f'attachment; filename="{name}.svg"'})
                return

            if what:
                self._gone()
                return

            front = render_side(store, data, "front")
            back = render_side(store, data, "back")
            html = card_page(data, front, back, token, base)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                       "private, max-age=300")

    return Handler


def serve(store: TwinStore, host: str = "127.0.0.1", port: int = 8088,
          base: str = "") -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port), make_handler(store, RateLimiter(), NegativeCache(), base))
