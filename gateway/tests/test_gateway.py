"""Tests des Partner-Gateways.  python3 -m unittest discover -s gateway/tests -t ."""
from __future__ import annotations

import copy
import json
import pathlib
import unittest

from gateway.contract import Contract
from gateway.mapping import Mapper, MappingError, apply_rule, dig

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "specs" / "partner_payload.v1.schema.json"
MAPPING = ROOT / "specs" / "partner_mapping.stickerkoenig.v1.json"
RAW = json.loads((pathlib.Path(__file__).parent / "fixtures" / "sk_raw_example.json")
                 .read_text(encoding="utf-8"))


def payload(raw=None):
    return Mapper.load(MAPPING).to_payload(copy.deepcopy(raw if raw is not None else RAW))


def player(pl, ref):
    return next(p for p in pl["order"]["players"] if p["external_ref"] == ref)


class TestMapping(unittest.TestCase):
    def test_fremdformat_wird_vertragskonform(self):
        self.assertEqual(Contract.load(SCHEMA).validate(payload()), [])

    def test_name_wird_zusammengesetzt(self):
        self.assertEqual(player(payload(), "SP-1001")["display_name"], "Lukas Meier")

    def test_positionen_werden_auf_rollen_abgebildet(self):
        p = payload()
        self.assertEqual(player(p, "SP-1001")["role"], "FIELD")
        self.assertEqual(player(p, "SP-1002")["role"], "KEEPER")
        self.assertEqual(player(p, "SP-1003")["role"], "COACH")

    def test_unbekannte_position_blockiert_keine_bestellung(self):
        # "Libera" kennt die Tabelle nicht - Rueckfall auf FIELD statt Abbruch.
        self.assertEqual(player(payload(), "SP-1004")["role"], "FIELD")

    def test_deutsche_wahrheitswerte(self):
        self.assertIs(player(payload(), "SP-1001")["is_minor"], True)
        self.assertIs(player(payload(), "SP-1003")["is_minor"], False)

    def test_zahlen_als_text_werden_umgewandelt(self):
        p = player(payload(), "SP-1001")
        self.assertEqual(p["photo"]["width_px"], 1800)      # kam als "1800"
        self.assertEqual(p["jersey_number"], "7")           # kam als 7

    def test_hash_und_mimetype_werden_normalisiert(self):
        photo = player(payload(), "SP-1001")["photo"]
        self.assertEqual(photo["content_hash"], photo["content_hash"].lower())
        self.assertEqual(photo["mime_type"], "image/jpeg")   # kam als "image/JPEG"

    def test_fehlendes_foto_erzeugt_kein_leeres_objekt(self):
        self.assertNotIn("photo", player(payload(), "SP-1004"))

    def test_menge_faellt_auf_eins_zurueck(self):
        self.assertEqual(player(payload(), "SP-1001")["quantity"], 3)
        self.assertEqual(player(payload(), "SP-1002")["quantity"], 1)

    def test_unbekannte_fremdfelder_erreichen_das_kernmodell_nicht(self):
        raw = copy.deepcopy(RAW)
        raw["auftrag"]["spieler"][0]["interne_notiz"] = "nicht weitergeben"
        raw["geheimes_feld"] = 42
        text = json.dumps(payload(raw), ensure_ascii=False)
        self.assertNotIn("interne_notiz", text)
        self.assertNotIn("geheimes_feld", text)

    def test_unlesbare_zahl_wird_gemeldet_statt_verschluckt(self):
        raw = copy.deepcopy(RAW)
        raw["auftrag"]["spieler"][0]["anzahl_karten"] = "drei"
        with self.assertRaises(MappingError):
            payload(raw)

    def test_dig_ist_gegen_luecken_robust(self):
        self.assertIsNone(dig({"a": {"b": None}}, "a.b.c"))
        self.assertIsNone(dig({"a": "text"}, "a.b"))

    def test_leere_zeichenketten_gelten_als_nicht_gesetzt(self):
        self.assertIsNone(apply_rule({"x": "   "}, {"path": "x"}))


class TestVertrag(unittest.TestCase):
    def setUp(self):
        self.contract = Contract.load(SCHEMA)

    def assert_flags(self, pl, needle):
        found = [str(v) for v in self.contract.validate(pl)]
        self.assertTrue(any(needle in f for f in found), f"nicht gemeldet: {found}")

    def test_fehlende_pflichtfelder_werden_alle_gemeldet(self):
        found = [str(v) for v in self.contract.validate({})]
        self.assertEqual(len(found), 2)

    def test_unbekannte_vertragsversion(self):
        pl = payload(); pl["payload_version"] = "9.9"
        self.assert_flags(pl, "nicht erlaubt")

    def test_kaputte_email(self):
        pl = payload(); pl["order"]["ordering_contact"]["email"] = "keine-adresse"
        self.assert_flags(pl, "Muster")

    def test_kaputter_fotohash(self):
        pl = payload(); player(pl, "SP-1001")["photo"]["content_hash"] = "zzz"
        self.assert_flags(pl, "Muster")

    def test_zu_langer_name(self):
        pl = payload(); player(pl, "SP-1001")["display_name"] = "X" * 200
        self.assert_flags(pl, "laenger als")

    def test_unbekanntes_feld_wird_abgelehnt(self):
        pl = payload(); player(pl, "SP-1001")["lieblingsfarbe"] = "blau"
        self.assert_flags(pl, "unbekanntes Feld")

    def test_ohne_spieler_keine_bestellung(self):
        pl = payload(); pl["order"]["players"] = []
        self.assert_flags(pl, "weniger als 1")

    def test_menge_ausserhalb_des_rahmens(self):
        pl = payload(); player(pl, "SP-1001")["quantity"] = 500
        self.assert_flags(pl, "groesser als 50")

    def test_wahrheitswert_ist_keine_zahl(self):
        pl = payload(); player(pl, "SP-1001")["is_minor"] = 1
        self.assert_flags(pl, "erwartet boolean/null")

    def test_null_ist_erlaubt_wo_vorgesehen(self):
        pl = payload(); player(pl, "SP-1001")["jersey_number"] = None
        self.assertEqual(self.contract.validate(pl), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
