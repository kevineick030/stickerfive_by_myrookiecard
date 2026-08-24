#!/usr/bin/env python3
"""Erzeugt db/seed/0002_specs.generated.sql aus specs/*.json.

Die JSON-Dateien sind die Quelle der Wahrheit; die Seed-Datei ist abgeleitet.
So koennen Slot-Schema und photo_spec nicht zwischen Repository und Datenbank
auseinanderlaufen. Nach jeder Aenderung an specs/ dieses Skript erneut laufen
lassen und beide Dateien gemeinsam committen.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
OUT = ROOT / "db" / "seed" / "0002_specs.generated.sql"


def q(value) -> str:
    """JSON-Literal fuer Postgres, dollar-quoted (die Specs enthalten Apostrophe)."""
    return "$json$" + json.dumps(value, ensure_ascii=False, indent=2) + "$json$::jsonb"


def lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def main() -> int:
    slot = json.loads((SPECS / "slot_schema.v1.json").read_text(encoding="utf-8"))
    photo = json.loads((SPECS / "photo_spec.v1.json").read_text(encoding="utf-8"))

    schema_id = f"{slot['id']}@{slot['version']}"
    lines = [
        "-- =====================================================================",
        "-- GENERIERT von tools/gen_spec_seed.py - NICHT VON HAND AENDERN.",
        "-- Quelle: specs/slot_schema.v1.json, specs/photo_spec.v1.json",
        "-- =====================================================================",
        "",
        "-- ---------------------------------------------------- Slot-Schema",
        "insert into slot_schema (id, version, definition) values",
        f"  ({lit(schema_id)}, {lit(slot['version'])}, {q(slot)})",
        "on conflict (id) do update set definition = excluded.definition;",
        "",
        "-- ---------------------------------------------------- photo_spec",
        "update photo_spec set is_active = false where is_active;",
        "insert into photo_spec (version, rules, is_active) values",
        f"  ({lit(photo['version'])}, {q(photo)}, true)",
        "on conflict (version) do update"
        " set rules = excluded.rules, is_active = excluded.is_active;",
        "",
        "-- ---------------------------------------------------- Design-Versionen",
        "-- Alle vier Templates auf demselben Slot-Schema: ein Renderer,",
        "-- ein QA-Regelsatz, ein Golden Set.",
    ]

    for fam in slot["families"]:
        assets = {"slot_overrides": fam.get("slot_overrides", {})}
        if fam.get("note"):
            assets["note"] = fam["note"]
        lines += [
            "insert into design_version"
            " (family_id, version, slot_schema_id, print_spec_id, assets)",
            f"  values ({lit(fam['id'])}, {lit(slot['version'])},"
            f" {lit(schema_id)}, {lit(fam['print_spec'])}, {q(assets)})",
            "on conflict (family_id, version) do update"
            " set assets = excluded.assets, print_spec_id = excluded.print_spec_id;",
            "",
        ]

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"geschrieben: {OUT.relative_to(ROOT)} "
          f"({len(slot['families'])} Design-Familien, photo_spec {photo['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
