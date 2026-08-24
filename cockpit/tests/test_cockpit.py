"""Tests des Cockpits.  python3 -m unittest discover -s cockpit/tests -t ."""
from __future__ import annotations

import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

from cockpit.app import ago, dur, dur_from, make_handler, until
from cockpit.ui import de, photo_trend_chart, sparkline, tile

CSRF = "test-merkmal"


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


class FakeStore:
    """Ersetzt die Datenbank, damit die Oberflaeche fuer sich pruefbar bleibt."""

    def __init__(self, paused: bool = False):
        self.paused = paused
        self.set_calls: list[tuple[bool, str]] = []

    def tiles(self):
        return {"auto_pass_rate_pct": 99.4, "qa_verdicts_24h": 812, "qa_in_review": 6,
                "photo_class_c_pct": 9.5, "photo_assessed_7d": 1434, "cards_open": 90,
                "cards_printed": 5, "blockers_hard": 2, "blockers_soft": 8,
                "photos_pending": 1, "oldest_working_seconds": 72,
                "batches_unacknowledged": 2, "batches_open": 0, "outbox_failed": 1,
                "outbox_pending": 2, "changes_open": 1, "orders_at_risk": 1,
                "transfers_paused": self.paused}

    def photo_trend(self):
        return [{"day": f"2026-08-{11 + i:02d}", "assessed": 200, "class_a": 150,
                 "class_b": 40, "class_c": 10, "class_c_pct": 4.0 + i * 0.55}
                for i in range(14)]

    def qa_sparkline(self):
        return [{"day": f"2026-08-{11 + i:02d}", "pct": 99.0 + (i % 3) * 0.2} for i in range(14)]

    def blocker_queue(self):
        return [{"reason": "CONSENT_REVOKED", "label_de": "Einwilligung widerrufen",
                 "severity": "HARD", "owner": "PARTNER", "open_count": 2,
                 "oldest_opened_at": iso(hours=-5), "oldest_age": "05:00:00"}]

    def orders(self):
        return [{"team_order_id": "11111111-1111-1111-1111-111111111111",
                 "external_ref": "SK-2026-0044", "derived_status": "IN_PRODUCTION",
                 "items_total": 35, "items_delivered": 0, "items_with_blocker": 9,
                 "items_hard_blocked": 2, "club_name": "FC Talblick", "team_name": "C-Jugend",
                 "season": "25/26", "promised_delivery_at": iso(hours=30),
                 "hold_until": iso(days=2), "fulfillment_policy": "PARTIAL_WITH_HOLD",
                 "puffer": "30:00:00"}]

    def outbox(self):
        return [{"channel": "PRINTER", "state": "FAILED", "eintraege": 1,
                 "naechster_versuch": iso(minutes=4), "meiste_versuche": 3,
                 "letzter_fehler": "Zeitüberschreitung"}]

    def changes(self):
        return [{"field": "display_name", "old_value": "Lukas Meier", "new_value": "Lukas Meyer",
                 "detected_at": iso(hours=-2), "display_name": "Lukas Meier",
                 "external_ref": "SK-2026-0045"}]

    def batches(self):
        return [{"id": "22222222-2222-2222-2222-222222222222", "print_spec_id": "PS-STD",
                 "state": "TRANSFERRED", "cards": 19, "transferred_at": iso(hours=-3),
                 "acknowledged_at": None, "unacknowledged_for": "03:12:00"}]

    def order_head(self, order_id):
        return self.orders()[0] if order_id.startswith("1111") else None

    def board(self, order_id):
        return [{"team_order_id": order_id, "order_ref": "SK-2026-0044",
                 "team_name": "C-Jugend", "club_name": "FC Talblick",
                 "card_item_id": "33333333-3333-3333-3333-333333333333",
                 "player_name": "Ben Berger", "player_role": "FIELD",
                 "design_family": "DESIGN-1", "copy_index": 2, "quantity": 3, "state": "BLOCKED",
                 "qr_token": "aaaaaaaaaaaaaaaaaaaaaa", "photo_quality_class": None,
                 "board_status": "HARD", "oldest_blocker_opened_at": iso(hours=-5)}]

    def card(self, card_id):
        if not card_id.startswith("3333"):
            return None
        return {"card_item_id": card_id, "state": "BLOCKED", "copy_index": 1, "quantity": 3,
                "artifact_fingerprint": None, "qr_token": "aaaaaaaaaaaaaaaaaaaaaa",
                "twin_revoked_at": None, "order_line_id": "x", "line_type": "BASE_PACK",
                "recipient_group_key": "SP-1", "team_order_id": "11111111-1111-1111-1111-111111111111",
                "order_ref": "SK-2026-0044",
                "correlation_id": "44444444-4444-4444-4444-444444444444",
                "hold_until": None, "promised_delivery_at": None,
                "fulfillment_policy": "PARTIAL_WITH_HOLD", "team_id": "t",
                "team_name": "C-Jugend", "season": "25/26", "club_name": "FC Talblick",
                "person_id": "p", "player_name": "Ben Berger", "player_role": "FIELD",
                "is_minor": True, "design_family": "DESIGN-1", "design_version": "1.0.0",
                "print_spec_id": "PS-STD", "print_batch_id": None, "wave_id": None,
                "photo_quality_class": None, "has_hard_blocker": True,
                "has_open_blocker": True, "oldest_blocker_opened_at": iso(hours=-5)}

    def card_blockers(self, card_id):
        return [{"reason": "CONSENT_REVOKED", "label_de": "Einwilligung widerrufen",
                 "severity": "HARD", "owner": "PARTNER", "opened_at": iso(hours=-5),
                 "resolved_at": None}]

    def card_events(self, correlation):
        return [{"event_type": "order.accepted", "actor": "demo",
                 "occurred_at": "2026-08-24T10:00:00", "payload": {}}]

    def search(self, term):
        return self.board("11111111-1111-1111-1111-111111111111") if "ben" in term.lower() else []

    def set_transfers_paused(self, paused, actor):
        self.paused = paused
        self.set_calls.append((paused, actor))


class TestFormat(unittest.TestCase):
    def test_dauer(self):
        self.assertEqual(dur(45), "45 s")
        self.assertEqual(dur(600), "10 min")
        self.assertEqual(dur(7200), "2 h")
        self.assertEqual(dur(None), "—")

    def test_puffer_wird_nach_dringlichkeit_eingefaerbt(self):
        self.assertEqual(until(iso(hours=-1))[0], "überfällig")
        self.assertEqual(until(iso(hours=-1))[1], "crit")
        self.assertEqual(until(iso(hours=10))[1], "crit")
        self.assertEqual(until(iso(days=2))[1], "warn")
        self.assertEqual(until(iso(days=9))[1], "")

    def test_vergangene_zeit(self):
        self.assertTrue(ago(iso(hours=-3)).startswith("vor "))
        self.assertEqual(ago(None), "—")

    def test_intervall_aus_postgres(self):
        self.assertEqual(dur_from("03:12:00"), "3 h")
        self.assertEqual(dur_from(None), "—")


class TestBezeichnungen(unittest.TestCase):
    def test_datenbankwerte_werden_uebersetzt(self):
        self.assertEqual(de("IN_PRODUCTION"), "In Produktion")
        self.assertEqual(de("BLOCKED"), "Blockiert")
        self.assertEqual(de("CUSTOMER"), "Kunde")
        self.assertEqual(de("HARD"), "Hart")

    def test_unbekanntes_bleibt_lesbar(self):
        self.assertEqual(de("NEUER_ZUSTAND"), "Neuer zustand")
        self.assertEqual(de(None), "—")


class TestBausteine(unittest.TestCase):
    def test_kachel_traegt_zahl_und_erlaeuterung(self):
        html = tile("Blocker", "2", small="/ 8", tone="crit", sub="2 hart · 8 weich")
        self.assertIn(">2<", html)
        self.assertIn("/ 8", html)
        self.assertIn("crit", html)
        self.assertIn("2 hart", html)

    def test_verlauf_braucht_mindestens_zwei_punkte(self):
        self.assertEqual(sparkline([1.0], "#000"), "")
        self.assertIn("<polyline", sparkline([1.0, 2.0, 3.0], "#000"))

    def test_diagramm_zeigt_schwelle_und_endpunkt(self):
        rows = [{"day": f"2026-08-{11 + i:02d}", "assessed": 100, "class_c": 5,
                 "class_c_pct": 4.0 + i} for i in range(14)]
        svg = photo_trend_chart(rows, threshold=8.0)
        self.assertIn("Schwelle", svg)
        self.assertIn("<title>", svg, "Berührflächen für die Hoverschicht fehlen")
        self.assertIn("aria-label", svg)
        self.assertIn("17%", svg.replace("17.0%", "17%"))

    def test_diagramm_ohne_daten_bleibt_ruhig(self):
        self.assertIn("Noch keine", photo_trend_chart([]))


class TestSeiten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = FakeStore()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store, CSRF))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def post(self, path, data, redirect=False):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(self.base + path, data=body, method="POST")
        opener = urllib.request.build_opener()
        if not redirect:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k):
                    return None
            opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_uebersicht(self):
        code, html, _ = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("Auto-Pass-Rate", html)
        self.assertIn("99.4", html)
        self.assertIn("In Produktion", html)

    def test_uebersicht_zeigt_notaus_knopf(self):
        _, html, _ = self.get("/")
        self.assertIn("Not-Aus", html)
        self.assertIn('name="csrf"', html)

    def test_kein_suchindex(self):
        _, _, headers = self.get("/")
        self.assertIn("noindex", headers["X-Robots-Tag"])
        self.assertIn("no-store", headers["Cache-Control"])

    def test_team_board(self):
        code, html, _ = self.get("/auftrag/11111111-1111-1111-1111-111111111111")
        self.assertEqual(code, 200)
        self.assertIn("Ben Berger", html)
        self.assertIn("hart blockiert", html)

    def test_board_zeigt_kopie_aus_der_bestellzeile(self):
        # Nicht die Zahl gleichnamiger Personen - zwei Kinder koennen gleich heissen.
        _, html, _ = self.get("/auftrag/11111111-1111-1111-1111-111111111111")
        self.assertIn("2/3", html)

    def test_unbekannter_auftrag(self):
        self.assertEqual(self.get("/auftrag/99999999-9999-9999-9999-999999999999")[0], 404)

    def test_karten_forensik_zeigt_die_spur(self):
        code, html, _ = self.get("/karte/33333333-3333-3333-3333-333333333333")
        self.assertEqual(code, 200)
        self.assertIn("Einwilligung widerrufen", html)
        self.assertIn("order.accepted", html)
        self.assertIn("noch nicht gerendert", html)

    def test_suche_findet_ueber_den_namen(self):
        self.assertIn("Ben Berger", self.get("/suche?q=Ben")[1])
        self.assertIn("Nichts gefunden", self.get("/suche?q=Zzz")[1])

    def test_arbeitsvorrat(self):
        _, html, _ = self.get("/queues")
        self.assertIn("Druckerei", html)
        self.assertIn("Lukas Meyer", html)
        self.assertIn("Fehlgeschlagen", html)

    def test_notaus_ohne_merkmal_wirkt_nicht(self):
        before = list(self.store.set_calls)
        self.assertEqual(self.post("/ops/transfers", {"paused": "true"}), 403)
        self.assertEqual(self.store.set_calls, before)

    def test_notaus_mit_merkmal_schaltet(self):
        self.assertEqual(self.post("/ops/transfers", {"csrf": CSRF, "paused": "true"}), 303)
        self.assertEqual(self.store.set_calls[-1][0], True)
        self.post("/ops/transfers", {"csrf": CSRF, "paused": "false"})
        self.assertEqual(self.store.set_calls[-1][0], False)

    def test_gesundheitspruefung(self):
        self.assertEqual(self.get("/healthz")[0], 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
