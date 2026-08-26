"""Tests der Layout-Engine.  python3 -m unittest discover -s engine/tests -v"""
from __future__ import annotations

import copy
import json
import pathlib
import unittest

from engine.fontmetrics import load_font
from engine.gate1 import check, passed
from engine.layout import (CardData, Landmarks, PhotoAsset, build_manifest,
                           coverage_scale, qr_plan)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
FAMILIES = {f["id"]: f for f in SCHEMA["families"]}
# Dieselben Schriften wie in der Produktion - sonst rechnet die Engine mit
# anderen Breiten als der Renderer setzt, und der Autofit stimmt nie.
FONTS = {
    "display": load_font(str(ROOT / "assets" / "fonts" / "anton.ttf")),
    "body": load_font(str(ROOT / "assets" / "fonts" / "oswald.ttf")),
}
# Der Normalfall: ein FREIGESTELLTER Spieler. Kopf 700 px, darunter 1980 px
# Oberkoerper - das sind 2,8 Kopfhoehen und damit genug, um vom Scheitelanker
# bis zur Unterkante des Fotofensters zu reichen.
PHOTO_OK = PhotoAsset("a" * 64, 1800, 2400, Landmarks(830, 400, 1100, 900),
                      cutout=True, subject_bottom_y=2380)
# Ein unfreigestelltes Vollbild - fuer die Deckungsregel, die nur dort gilt.
PHOTO_VOLL = PhotoAsset("v" * 64, 2000, 2400, Landmarks(887, 500, 1360, 1000))


def make_card(**kw) -> CardData:
    base = dict(card_item_id="t-1", copy_index=1, copies_total=3, player_name="Lukas Meier",
                club_name="TSV Musterstadt", season="25/26", position_label="Feldspieler",
                jersey_number="7", team_name="D-Jugend",
                public_token="Demo1Tokenzzzzzzzzzzzz", resolver_host="k.mrc.cards",
                legal_line="© TSV Musterstadt")
    base.update(kw)
    return CardData(**base)


def manifest(card=None, photo=PHOTO_OK, family="DESIGN-1", schema=SCHEMA):
    return build_manifest(schema, FAMILIES[family], card or make_card(), photo, FONTS, "1.0.0")


def photo_of(m):
    return next(p for p in m["front"]["placements"] if p["type"] == "image")


def slot_of(m, side, sid):
    return next(p for p in m[side]["placements"] if p["slot"] == sid)


class TestAnkerregel(unittest.TestCase):
    """Der Kern: unterschiedliche Ausschnitte, dieselbe Augenlinie."""

    def test_scheitel_trifft_anker_unabhaengig_vom_ausschnitt(self):
        """Der Kern: drei verschiedene Ausschnitte, ein Scheitel auf einer Hoehe."""
        slot = next(s for s in SCHEMA["front"]["slots"] if s["id"] == "photo")
        soll = slot["box"]["y"] + slot["anchors"]["head_top_ratio"] * slot["box"]["h"]
        varianten = [
            PhotoAsset("a" * 64, 1800, 2400, Landmarks(830, 400, 1100, 900),
                       cutout=True, subject_bottom_y=2380),
            PhotoAsset("b" * 64, 1400, 2000, Landmarks(690, 330, 910, 700),
                       cutout=True, subject_bottom_y=1980),
            PhotoAsset("c" * 64, 2400, 3200, Landmarks(1100, 520, 1470, 1200),
                       cutout=True, subject_bottom_y=3180),
        ]
        for p in varianten:
            with self.subTest(px=(p.width_px, p.height_px)):
                pl = photo_of(manifest(photo=p))
                self.assertAlmostEqual(pl["head_top_mm"], soll, places=3)
                self.assertAlmostEqual(pl["resulting_head_height_ratio"],
                                       slot["anchors"]["head_height_ratio"], places=3)

    def test_freisteller_wird_nie_wegen_deckung_hochskaliert(self):
        """Den Hintergrund liefert die Vorlage - es gibt nichts zu decken."""
        anchors = next(s for s in SCHEMA["front"]["slots"] if s["id"] == "photo")["anchors"]
        pl = photo_of(manifest())
        self.assertFalse(pl["scale_adjusted_for_coverage"])
        self.assertAlmostEqual(pl["resulting_head_height_ratio"],
                               anchors["head_height_ratio"], places=3)

    def test_zu_wenig_oberkoerper_meldet_schwebenden_spieler(self):
        kurz = PhotoAsset("k" * 64, 1800, 1500, Landmarks(830, 400, 1100, 900),
                          cutout=True, subject_bottom_y=1480)
        befunde = check(manifest(photo=kurz))
        self.assertTrue(any(f.code == "SUBJECT_FLOATS" for f in befunde))

    def test_zu_enger_ausschnitt_wird_hochskaliert_und_gemeldet(self):
        eng = PhotoAsset("z" * 64, 900, 2400, Landmarks(887, 500, 1360, 450))
        pl = photo_of(manifest(photo=eng))
        self.assertFalse(eng.cutout, "die Deckungsregel gilt nur fuer Vollbilder")
        self.assertTrue(pl["scale_adjusted_for_coverage"])
        self.assertGreater(pl["scale_mm_per_px"], pl["scale_from_anchor"])
        self.assertGreater(pl["head_ratio_deviation"], 0)
        # Der Scheitel bleibt trotzdem exakt auf dem Anker - sonst zerfaellt das Set.
        slot = next(s for s in SCHEMA["front"]["slots"] if s["id"] == "photo")
        soll = slot["box"]["y"] + slot["anchors"]["head_top_ratio"] * slot["box"]["h"]
        self.assertAlmostEqual(pl["head_top_mm"], soll, places=3)

    def test_coverage_scale_ist_die_untere_schranke(self):
        slot = next(s for s in SCHEMA["front"]["slots"] if s["id"] == "photo")
        # Nur beim Vollbild: dort muss das Bild den Slot decken.
        pl = photo_of(manifest(photo=PHOTO_VOLL))
        self.assertLessEqual(coverage_scale(slot, PHOTO_VOLL),
                             pl["scale_mm_per_px"] + 1e-9)
        self.assertTrue(pl["scale_adjusted_for_coverage"])


class TestTextsatz(unittest.TestCase):
    def test_kurzer_name_bleibt_bei_der_deklarierten_groesse(self):
        p = slot_of(manifest(), "front", "player_name")
        self.assertFalse(p["autofit_applied"])
        self.assertEqual(p["size_pt"], p["declared_size_pt"])

    def test_langer_name_wird_verkleinert_statt_abgeschnitten(self):
        p = slot_of(manifest(make_card(player_name="Maximilian Oberhauser-Schmid")), "front", "player_name")
        self.assertTrue(p["autofit_applied"])
        self.assertLess(p["size_pt"], p["declared_size_pt"])
        self.assertGreaterEqual(p["size_pt"], p["min_size_pt"])
        self.assertLessEqual(p["measured_width_mm"], p["box_mm"]["w"] + 1e-6)

    def test_ueberlanger_name_meldet_overflow_statt_still_zu_passen(self):
        card = make_card(player_name="Maximilian Alexander von Hohenberg-Schoenau-Wittelsbach")
        p = slot_of(manifest(card), "front", "player_name")
        self.assertTrue(p.get("overflow"))
        self.assertTrue(any(f.code == "TEXT_OVERFLOW" for f in check(manifest(card))))

    def test_diakritika_werden_als_vorhanden_erkannt(self):
        p = slot_of(manifest(make_card(player_name="Maximilian Oberhauser-Schmid")), "front", "player_name")
        self.assertEqual(p["missing_glyphs"], [])

    def test_fehlende_glyphe_faellt_auf(self):
        p = slot_of(manifest(make_card(player_name="Lukas 日本語 Meier")), "front", "player_name")
        self.assertTrue(p["missing_glyphs"])
        self.assertTrue(any(f.code == "MISSING_GLYPH" for f in check(manifest(
            make_card(player_name="Lukas 日本語 Meier")))))


class TestQR(unittest.TestCase):
    def setUp(self):
        self.slot = next(s for s in SCHEMA["back"]["slots"] if s["type"] == "qr")

    def test_kuerzerer_host_ergibt_groessere_module(self):
        kurz = qr_plan("https://k.mrc.cards/k/" + "x" * 22, self.slot)
        lang = qr_plan("https://karte.myrookiecard.de/k/" + "x" * 22, self.slot)
        self.assertLessEqual(kurz["version"], lang["version"])
        self.assertGreater(kurz["module_mm"], lang["module_mm"])
        for p in (kurz, lang):
            self.assertTrue(p["module_ok"], "beide Hosts muessen druckbar bleiben")

    def test_budget_folgt_aus_der_boxgroesse(self):
        p = qr_plan("x", self.slot)
        self.assertEqual(p["payload_budget_bytes"], 74)

    def test_langer_partnertoken_verkleinert_die_module(self):
        # Ein fremd vergebener Token darf laenger sein als unserer. Die Folge
        # muss sichtbar werden, nicht stillschweigend hingenommen.
        kurz = qr_plan("https://k.mrc.cards/k/" + "x" * 22, self.slot)
        lang = qr_plan("https://k.mrc.cards/k/" + "x" * 48, self.slot)
        self.assertGreater(lang["version"], kurz["version"])
        self.assertLess(lang["module_mm"], kurz["module_mm"])
        self.assertTrue(lang["module_ok"], "48 Zeichen muessen noch druckbar sein")

    def test_zu_lange_nutzlast_bekommt_keine_version(self):
        p = qr_plan("https://" + "a" * 400 + "/k/x", self.slot)
        self.assertIsNone(p["version"])


class TestFingerprint(unittest.TestCase):
    """Die Behauptung, auf der die Kostenrechnung beruht."""

    def test_gleicher_input_gleicher_fingerprint(self):
        self.assertEqual(manifest()["fingerprint"], manifest()["fingerprint"])

    def test_anderer_token_aendert_nur_die_rueckseite(self):
        a = manifest(make_card(public_token="Demo1Tokenzzzzzzzzzzzz"))
        b = manifest(make_card(public_token="Demo2Tokenyyyyyyyyyyyy"))
        self.assertEqual(a["front"]["fingerprint"], b["front"]["fingerprint"],
                         "drei Kopien teilen die teure Vorderseite")
        self.assertNotEqual(a["back"]["fingerprint"], b["back"]["fingerprint"])
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])

    def test_anderer_name_aendert_die_vorderseite(self):
        a, b = manifest(), manifest(make_card(player_name="Tim Klein"))
        self.assertNotEqual(a["front"]["fingerprint"], b["front"]["fingerprint"])

    def test_anderes_foto_aendert_die_vorderseite(self):
        b = manifest(photo=PhotoAsset("f" * 64, 1800, 2400, Landmarks(887, 500, 1360, 900)))
        self.assertNotEqual(manifest()["front"]["fingerprint"], b["front"]["fingerprint"])


class TestGate1(unittest.TestCase):
    def test_saubere_karte_besteht(self):
        self.assertTrue(passed(check(manifest())))

    def test_knappes_foto_faellt_wegen_aufloesung_durch(self):
        # Kopf nur 200 px hoch - unter den 283 px, die 300 dpi im Fotofenster verlangen.
        knapp = PhotoAsset("d" * 64, 480, 640, Landmarks(213, 120, 320, 240))
        findings = check(manifest(photo=knapp))
        self.assertFalse(passed(findings))
        self.assertTrue(any(f.code == "LOW_EFFECTIVE_DPI" for f in findings))

    def test_textbox_ausserhalb_des_bogens_faellt_durch(self):
        schema = copy.deepcopy(SCHEMA)
        next(s for s in schema["front"]["slots"] if s["id"] == "club_name")["box"]["y"] = 300.0
        self.assertTrue(any(f.code == "BOX_OUTSIDE_SHEET"
                            for f in check(manifest(schema=schema))))

    def test_ohne_prueffeld_kein_gate_3a(self):
        schema = copy.deepcopy(SCHEMA)
        for side in ("front", "back"):
            for s in schema[side]["slots"]:
                s.pop("qa_region", None)
        self.assertTrue(any(f.code == "NO_QA_REGION" for f in check(manifest(schema=schema))))


class TestDesign5(unittest.TestCase):
    """Die eine bewusste Abweichung vom gemeinsamen Slot-Schema."""

    def test_gruppenfoto_ohne_landmarks_nutzt_cover(self):
        gruppe = PhotoAsset("g" * 64, 3000, 2000, None)
        m = manifest(photo=gruppe, family="DESIGN-5")
        self.assertEqual(photo_of(m)["fit_mode"], "COVER")
        self.assertTrue(passed(check(m)))

    def test_rueckennummer_ist_ausgeblendet(self):
        m = manifest(photo=PhotoAsset("g" * 64, 3000, 2000, None), family="DESIGN-5")
        self.assertFalse(any(p["slot"] == "jersey_number" for p in m["front"]["placements"]))

    def test_name_kommt_vom_team(self):
        m = manifest(photo=PhotoAsset("g" * 64, 3000, 2000, None), family="DESIGN-5")
        self.assertEqual(slot_of(m, "front", "player_name")["text"], "D-JUGEND")


if __name__ == "__main__":
    unittest.main(verbosity=2)
