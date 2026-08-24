"""Tests des Aufloesungsdienstes.  python3 -m unittest discover -s resolver/tests -t ."""
from __future__ import annotations

import json
import pathlib
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from engine.fontmetrics import load_font
from engine.layout import CardData, Landmarks, PhotoAsset, build_manifest
from resolver.app import NegativeCache, RateLimiter, make_handler, render_side, SECURITY_HEADERS
from resolver.store import InMemoryStore, token_is_wellformed

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
FAMILIES = {f["id"]: f for f in SCHEMA["families"]}
FONTS = {"display": load_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
         "body": load_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")}

GOOD = "ZriscWhoAWb4NP7aCxspk7"
UNPUBLISHED = "NochNichtGedruckt12345"
UNKNOWN = "GibtEsNichtAAAAAAAAAA"


def demo_store() -> InMemoryStore:
    card = CardData(card_item_id="t", copy_index=1, player_name="Lukas Meier",
                    club_name="TSV Musterstadt", season="25/26",
                    position_label="Feldspieler", jersey_number="7", team_name="D-Jugend",
                    public_token=GOOD, resolver_host="k.mrc.cards", legal_line="© TSV")
    photo = PhotoAsset("a" * 64, 1800, 2400, Landmarks(887, 500, 1360, 900))
    manifest = build_manifest(SCHEMA, FAMILIES["DESIGN-1"], card, photo, FONTS, "1.0.0")
    fp = manifest["fingerprint"]
    return InMemoryStore(
        twins={GOOD: {"status": "OK", "token": GOOD, "player_name": "Lukas Meier",
                      "club_name": "TSV Musterstadt", "team_name": "D-Jugend",
                      "season": "25/26", "role": "FIELD", "jersey_number": "7",
                      "design_family": "DESIGN-1", "card_number": 1, "card_total": 3,
                      "fingerprint": fp},
               UNPUBLISHED: {"status": "GONE"}},
        manifests={fp: manifest})


class TestToken(unittest.TestCase):
    def test_gueltige_form(self):
        self.assertTrue(token_is_wellformed(GOOD))
        self.assertTrue(token_is_wellformed("SK-CARD-9999-a1b2c3"))

    def test_abgelehnte_formen(self):
        for bad in ["", "kurz", "'; drop table card_twin;--",
                    "mit leerzeichen hier", "a" * 60, "sonder$zeichen1234"]:
            with self.subTest(bad=bad):
                self.assertFalse(token_is_wellformed(bad))


class TestNegativeCache(unittest.TestCase):
    def test_merkt_sich_fehlschlaege(self):
        c = NegativeCache()
        self.assertFalse(c.known_bad("x" * 20))
        c.note("x" * 20)
        self.assertTrue(c.known_bad("x" * 20))

    def test_laeuft_ab(self):
        c = NegativeCache(ttl=-1)
        c.note("x" * 20)
        self.assertFalse(c.known_bad("x" * 20))

    def test_bleibt_beschraenkt(self):
        c = NegativeCache(limit=10)
        for i in range(40):
            c.note(f"token{i:015d}")
        self.assertLessEqual(len(c._at), 10)


class TestRateLimiter(unittest.TestCase):
    def test_deckelt_je_aufrufer(self):
        r = RateLimiter(per_min=3)
        self.assertEqual([r.allow("a") for _ in range(5)], [True, True, True, False, False])

    def test_trennt_aufrufer(self):
        r = RateLimiter(per_min=1)
        self.assertTrue(r.allow("a"))
        self.assertTrue(r.allow("b"))


class TestRendern(unittest.TestCase):
    def test_svg_rahmen_enthaelt_den_anschnitt(self):
        store = demo_store()
        data = store.resolve(GOOD)
        svg = render_side(store, data, "front")
        # Sonst faellt der ueberstehende Rand des Motivs aus dem Bild.
        self.assertIn('viewBox="-2.0 -2.0 67.0 92.0"', svg)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("LUKAS MEIER", svg)

    def test_ohne_manifest_kein_bild(self):
        store = demo_store()
        self.assertIsNone(render_side(store, {"fingerprint": "f" * 64}, "front"))


class TestDienst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = make_handler(demo_store(), RateLimiter(per_min=500), NegativeCache())
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path: str):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_gueltiger_code_zeigt_die_karte(self):
        code, body, _ = self.get(f"/k/{GOOD}")
        self.assertEqual(code, 200)
        text = body.decode()
        self.assertIn("Lukas Meier", text)
        self.assertIn("1 von 3", text)

    def test_seite_zeigt_keine_anderen_spieler(self):
        _, body, _ = self.get(f"/k/{GOOD}")
        text = body.decode()
        for other in ("Tim Klein", "Đorđe", "Nele"):
            self.assertNotIn(other, text)

    def test_sicherheitskopfzeilen(self):
        _, _, headers = self.get(f"/k/{GOOD}")
        for key in SECURITY_HEADERS:
            self.assertIn(key, headers, key)
        self.assertIn("noindex", headers["X-Robots-Tag"])

    def test_unbekannt_und_ungedruckt_sind_ununterscheidbar(self):
        a = self.get(f"/k/{UNKNOWN}")
        b = self.get(f"/k/{UNPUBLISHED}")
        self.assertEqual(a[0], b[0], "gleicher Statuscode")
        self.assertEqual(a[1], b[1], "gleicher Seiteninhalt")
        self.assertEqual(a[0], 404)

    def test_kaputter_token_faellt_vor_der_datenbank_durch(self):
        code, _, _ = self.get("/k/'%20or%201=1--")
        self.assertEqual(code, 404)

    def test_bild_wird_dauerhaft_zwischengespeichert(self):
        code, body, headers = self.get(f"/k/{GOOD}/front.svg")
        self.assertEqual(code, 200)
        self.assertIn("immutable", headers["Cache-Control"])
        self.assertTrue(body.startswith(b"<svg"))

    def test_seite_wird_nur_kurz_zwischengespeichert(self):
        _, _, headers = self.get(f"/k/{GOOD}")
        self.assertIn("private", headers["Cache-Control"])

    def test_download_haengt_den_namen_an(self):
        _, _, headers = self.get(f"/k/{GOOD}/download")
        self.assertIn("lukas-meier", headers["Content-Disposition"])

    def test_unbekannter_unterpfad(self):
        self.assertEqual(self.get(f"/k/{GOOD}/geheim")[0], 404)

    def test_wurzel_verraet_nichts(self):
        self.assertEqual(self.get("/")[0], 404)

    def test_gesundheitspruefung(self):
        code, body, _ = self.get("/healthz")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_rateversuche_blockieren_keinen_echten_scan(self):
        # Genau dieser Fehler steckte in der ersten Fassung: die Bremse gegen
        # Durchprobieren sperrte anschliessend auch gueltige Codes.
        for i in range(30):
            self.get(f"/k/Versuch{i:015d}")
        self.assertEqual(self.get(f"/k/{GOOD}")[0], 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
