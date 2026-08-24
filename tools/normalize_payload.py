#!/usr/bin/env python3
"""Rohform des Partners -> normalisierte Nutzlast, geprueft gegen den Vertrag.

  python3 tools/normalize_payload.py roh.json                 # normalisiert ausgeben
  python3 tools/normalize_payload.py roh.json --sql            # als psql-Aufruf
  python3 tools/normalize_payload.py roh.json --sql | psql     # direkt einspielen

Bricht ab, sobald die Nutzlast dem Vertrag nicht entspricht - lieber hier
als mit 60 halbfertigen Karten in der Produktion.
"""
from __future__ import annotations

import argparse, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from gateway.contract import Contract          # noqa: E402
from gateway.mapping import Mapper             # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", help="Rohdatei des Partners")
    ap.add_argument("--mapping", default=str(ROOT / "specs" / "partner_mapping.stickerkoenig.v1.json"))
    ap.add_argument("--schema", default=str(ROOT / "specs" / "partner_payload.v1.schema.json"))
    ap.add_argument("--sql", action="store_true", help="als SQL-Aufruf ausgeben")
    args = ap.parse_args()

    mapper = Mapper.load(args.mapping)
    raw = json.loads(pathlib.Path(args.raw).read_text(encoding="utf-8"))
    payload = mapper.to_payload(raw)

    violations = Contract.load(args.schema).validate(payload)
    if violations:
        print(f"Vertragsverletzung ({len(violations)}):", file=sys.stderr)
        for v in violations:
            print(f"  · {v}", file=sys.stderr)
        return 2

    if args.sql:
        literal = json.dumps(payload, ensure_ascii=False)
        print(f"select ingest_team_order('{mapper.partner_code}', $payload${literal}$payload$::jsonb);")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
