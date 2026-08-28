#!/usr/bin/env python3
"""Textlayer-Dienst: Satz auf eine fertige, textlose Karte.

    POST /satz   {"design": "DESIGN-1",
                  "karte_base64": "...",          # textlose Karte
                  "spieler": {"name": ..., "verein": ..., "nummer": ...},
                  "auflage": {"kopie": 1, "gesamt": 3},
                  "unterschrift_base64": "..."}   # optional
    -> 200       {"karte_base64": "...", "befunde": [...], "fingerprint": "..."}

Warum dieser Schnitt: das Bildmodell liefert das BILD, die Datenbank den
TEXT. Ein Bildmodell malt Buchstaben - es setzt sie nicht. Der Text hier
kommt aus derselben Quelle wie die Bestellung und laesst sich hinterher
per OCR dagegen pruefen, was bei gemaltem Text nicht geht.

    python3 tools/run_textlayer.py --port 8081
"""
from __future__ import annotations

import base64
import binascii
import json
import pathlib
import subprocess
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from textlayer.plan import FARBEN, baue

ROOT = pathlib.Path(__file__).resolve().parents[1]
RENDER = ROOT / "tools" / "render.mjs"
MAX_BYTES = 24 * 1024 * 1024


class Fehler(ValueError):
    """Eingabe, die der Aufrufer korrigieren kann - also 400, nicht 500."""


def _bild(feld: str, wert, ziel: pathlib.Path) -> pathlib.Path | None:
    if not wert:
        return None
    if not isinstance(wert, str):
        raise Fehler(f"{feld} muss base64 sein")
    roh = wert.split(",", 1)[-1]          # data:-URL-Praefix ist erlaubt
    try:
        daten = base64.b64decode(roh, validate=True)
    except (binascii.Error, ValueError) as e:
        raise Fehler(f"{feld} ist kein gueltiges base64: {e}") from None
    if not daten:
        raise Fehler(f"{feld} ist leer")
    ziel.write_bytes(daten)
    return ziel


def satz(anfrage: dict) -> dict:
    design = anfrage.get("design")
    if design not in FARBEN:
        raise Fehler(f"unbekanntes Design {design!r}, bekannt: {sorted(FARBEN)}")
    spieler = anfrage.get("spieler") or {}
    if not spieler.get("name"):
        raise Fehler("spieler.name fehlt")

    with tempfile.TemporaryDirectory(prefix="satz-") as tmp:
        ordner = pathlib.Path(tmp)
        karte = _bild("karte_base64", anfrage.get("karte_base64"), ordner / "karte.png")
        if karte is None:
            raise Fehler("karte_base64 fehlt")
        unterschrift = _bild("unterschrift_base64", anfrage.get("unterschrift_base64"),
                             ordner / "unterschrift.png")

        plan = baue(design, spieler, anfrage.get("auflage") or {}, str(karte),
                    str(unterschrift) if unterschrift else None,
                    int(anfrage.get("dpi") or 300))
        plan["id"] = "satz-" + uuid.uuid4().hex[:12]
        planweg = ordner / "plan.json"
        planweg.write_text(json.dumps(plan), encoding="utf-8")

        lauf = subprocess.run(["node", str(RENDER), str(planweg), "--out", str(ordner)],
                              capture_output=True, text=True, timeout=120)
        ergebnis = ordner / (plan["id"] + ".png")
        if lauf.returncode != 0 or not ergebnis.exists():
            raise RuntimeError((lauf.stderr or lauf.stdout).strip()[-800:] or "Renderer ohne Ausgabe")
        return {
            "karte_base64": base64.b64encode(ergebnis.read_bytes()).decode(),
            "befunde": plan["befunde"],
            "gesperrt": plan["gesperrt"],
            "fingerprint": plan["fingerprint"],
            "design": plan["designName"],
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "mrc-textlayer"

    def _antwort(self, code: int, nutzlast: dict) -> None:
        roh = json.dumps(nutzlast, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(roh)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self) -> None:          # noqa: N802
        if self.path == "/gesund":
            self._antwort(200, {"status": "bereit", "designs": sorted(FARBEN)})
        else:
            self._antwort(404, {"fehler": "nicht gefunden"})

    def do_POST(self) -> None:         # noqa: N802
        if self.path != "/satz":
            self._antwort(404, {"fehler": "nicht gefunden"})
            return
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge <= 0 or laenge > MAX_BYTES:
            self._antwort(413, {"fehler": f"Rumpf fehlt oder ueber {MAX_BYTES} Byte"})
            return
        try:
            anfrage = json.loads(self.rfile.read(laenge))
        except json.JSONDecodeError as e:
            self._antwort(400, {"fehler": f"kein gueltiges JSON: {e}"})
            return
        try:
            self._antwort(200, satz(anfrage))
        except Fehler as e:
            self._antwort(400, {"fehler": str(e)})
        except Exception as e:                                  # noqa: BLE001
            self._antwort(500, {"fehler": f"Satz fehlgeschlagen: {e}"})

    def log_message(self, fmt: str, *args) -> None:
        print(f"[textlayer] {fmt % args}")


def serve(port: int = 8081) -> None:
    print(f"Textlayer auf http://127.0.0.1:{port}  (POST /satz, GET /gesund)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
