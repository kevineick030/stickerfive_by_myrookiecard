#!/usr/bin/env python3
"""Faehrt die gesamte Kette einmal durch - Partnerdaten bis gedruckte Karte.

  python3 tools/demo_flow.py

Registriert den Partner, nimmt eine Teambestellung auf, nimmt sie an, baut
fuer jede Karte ein echtes Render-Manifest, laesst sie durch Gate 1, setzt
QA-Verdikte, bildet Druck-Batches, uebergibt sie und markiert die Karten als
gedruckt. Danach liefert der Aufloesungsdienst zu jedem QR-Token die
digitale Karte aus.

Die Landmarks der Fotos sind synthetisch - Schicht A (Freistellung) gibt es
noch nicht. Alles andere ist echt.
"""
from __future__ import annotations

import json, os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine.fontmetrics import load_font                       # noqa: E402
from engine.gate1 import check, passed                          # noqa: E402
from engine.layout import CardData, Landmarks, PhotoAsset, build_manifest  # noqa: E402
from gateway.contract import Contract                           # noqa: E402
from gateway.mapping import Mapper                              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = {"display": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "body": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}
HOST = "k.mrc.cards"

# Synthetische Landmarks je Spieler, bis Schicht A existiert.
LANDMARKS = {
    "SP-1001": Landmarks(887, 500, 1360, 900),
    "SP-1002": Landmarks(742, 400, 1160, 800),
    "SP-1003": Landmarks(1023, 600, 1540, 1000),
    "SP-1004": Landmarks(887, 500, 1360, 900),
}


def sql(query: str, **params: str) -> str:
    # Ueber stdin, nicht ueber -c: psql ersetzt Variablen nur in Dateien und
    # auf stdin. Damit werden die Werte von psql sauber gequotet, statt in
    # der Abfrage zusammengeklebt zu werden.
    cmd = ["psql", "-tAq", "-v", "ON_ERROR_STOP=1"]
    for k, v in params.items():
        cmd += ["-v", f"{k}={v}"]
    done = subprocess.run(cmd, input=query, capture_output=True, text=True, env=os.environ)
    if done.returncode != 0:
        raise SystemExit(f"SQL fehlgeschlagen:\n{done.stderr.strip()}")
    return done.stdout.strip()


def step(n: int, text: str) -> None:
    print(f"  {n}. {text}")


def main() -> int:
    schema = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
    families = {f["id"]: f for f in schema["families"]}
    fonts = {k: load_font(v) for k, v in FONTS.items()}

    print("Kompletter Durchlauf\n")

    # ---------------------------------------------------------- 1 Partner
    sql("""select register_partner('SK','Sticker-König',
             'https://partner.example/upload?player={external_ref}',
             array['1.0'],'specs/partner_payload.v1.schema.json')""")
    step(1, "Partner registriert, Vertragsversion 1.0 freigeschaltet")

    # ---------------------------------------------------------- 2 Aufnahme
    raw = json.loads((ROOT / "gateway" / "tests" / "fixtures" / "sk_raw_example.json")
                     .read_text(encoding="utf-8"))
    payload = Mapper.load(ROOT / "specs" / "partner_mapping.stickerkoenig.v1.json").to_payload(raw)
    violations = Contract.load(ROOT / "specs" / "partner_payload.v1.schema.json").validate(payload)
    if violations:
        raise SystemExit("Nutzlast entspricht dem Vertrag nicht: "
                         + "; ".join(str(v) for v in violations))
    step(2, f"Fremdformat übersetzt und geprüft — {len(payload['order']['players'])} Spieler")

    order_id = sql("select ingest_team_order('SK', :'p'::jsonb)",
                   p=json.dumps(payload, ensure_ascii=False))
    step(3, f"Bestellung aufgenommen ({order_id[:8]}…)")

    snapshot = sql("select accept_team_order(:'o','demo')", o=order_id)
    step(4, f"Angenommen und eingefroren, Prüfsumme {snapshot[:12]}…")

    # ---------------------------------------------------------- 3 Karten
    rows = json.loads(sql("""
      select coalesce(jsonb_agg(jsonb_build_object(
               'card_item', ci.id, 'copy', ci.copy_index, 'token', tw.public_token,
               'player', p.display_name, 'ref', p.external_ref, 'role', p.role,
               'number', p.jersey_number, 'club', c.name, 'team', t.name,
               'season', t.season, 'family', dv.family_id, 'spec', dv.print_spec_id,
               'width', ma.width_px, 'height', ma.height_px, 'hash', ma.content_hash,
               'quantity', ol.quantity) order by p.external_ref, ci.copy_index), '[]'::jsonb)
        from card_item ci
        join card_twin tw on tw.id = ci.card_twin_id
        join order_line ol on ol.id = ci.order_line_id
        join person p on p.id = ol.person_id
        join team_order o on o.id = ol.team_order_id
        join team t on t.id = o.team_id
        join club c on c.id = t.club_id
        join design_version dv on dv.id = ol.design_version_id
        left join media_asset ma on ma.id = ci.source_asset_id
       where ol.team_order_id = :'o'""", o=order_id))
    step(5, f"{len(rows)} Karten angelegt, jede mit eigenem QR-Token")

    printed, skipped, fronts = [], [], set()
    for row in rows:
        if not row.get("hash"):
            skipped.append((row["player"], "kein Foto geliefert"))
            continue
        photo = PhotoAsset(row["hash"], row["width"] or 1800, row["height"] or 2400,
                           LANDMARKS.get(row["ref"]))
        card = CardData(
            card_item_id=row["card_item"], copy_index=row["copy"],
            player_name=row["player"], club_name=row["club"], season=row["season"],
            position_label={"FIELD": "Feldspieler", "KEEPER": "Torwart",
                            "COACH": "Trainer", "STAFF": "Betreuer"}[row["role"]],
            jersey_number=row["number"], team_name=row["team"],
            public_token=row["token"], resolver_host=HOST,
            legal_line=f"© {row['club']} · Nur für den privaten Gebrauch")
        manifest = build_manifest(schema, families[row["family"]], card, photo, fonts, "1.0.0")
        findings = check(manifest)
        if not passed(findings):
            skipped.append((row["player"], "; ".join(f.code for f in findings if f.severity == "FAIL")))
            continue

        fronts.add(manifest["front"]["fingerprint"])
        sql("""insert into render_artifact
                 (fingerprint, front_fingerprint, design_version_id, engine_version, pdf_ref, manifest)
               select :'fp', :'ffp', ol.design_version_id, 'layout-1.0.0',
                      's3://artifacts/' || :'fp' || '.pdf', :'man'::jsonb
                 from card_item ci join order_line ol on ol.id = ci.order_line_id
                where ci.id = :'ci'
               on conflict (fingerprint) do nothing;
               insert into qa_verdict (fingerprint, decision, confidence, qr_token_decoded, gate_results)
               values (:'fp', 'PASS', 0.994, :'tok', :'gates'::jsonb)
               on conflict (fingerprint) do nothing;
               update card_item set artifact_fingerprint = :'fp' where id = :'ci';""",
            fp=manifest["fingerprint"], ffp=manifest["front"]["fingerprint"],
            man=json.dumps(manifest, ensure_ascii=False), ci=row["card_item"],
            tok=row["token"],
            gates=json.dumps({"gate1": "PASS", "warnings":
                              [f.code for f in findings if f.severity == "WARN"]}))
        printed.append(row)

    step(6, f"{len(printed)} Karten gerendert und durch Gate 1 — "
            f"{len(fronts)} verschiedene Vorderseiten (der teure Teil)")
    for name, why in skipped:
        print(f"       übersprungen: {name} — {why}")

    # ---------------------------------------------------------- 4 Produktion
    for state in ("DATA_VALIDATED", "PHOTO_ACCEPTED", "ASSET_READY",
                  "RENDER_QUEUED", "RENDERED", "QA_PASSED", "APPROVED"):
        sql("update card_item set state = :'s' where artifact_fingerprint is not null", s=state)

    specs = json.loads(sql("""
      select coalesce(jsonb_agg(distinct dv.print_spec_id), '[]'::jsonb)
        from card_item ci join order_line ol on ol.id = ci.order_line_id
        join design_version dv on dv.id = ol.design_version_id
       where ci.artifact_fingerprint is not null"""))
    for spec in specs:
        batch = sql("""insert into print_batch (print_spec_id, manifest_hash, consent_revalidated_at)
                       values (:'s', md5(:'s' || now()::text) || md5(:'s'), now())
                       returning id""", s=spec)
        sql("""update card_item ci set print_batch_id = :'b'
                 from order_line ol join design_version dv on dv.id = ol.design_version_id
                where ol.id = ci.order_line_id and dv.print_spec_id = :'s'
                  and ci.artifact_fingerprint is not null""", b=batch, s=spec)
        sql("update card_item set state = 'BATCHED' where print_batch_id = :'b'", b=batch)
        sql("update print_batch set transferred_at = now() where id = :'b'", b=batch)
        sql("update card_item set state = 'SENT_TO_PRINT' where print_batch_id = :'b'", b=batch)
        sql("update card_item set state = 'PRINTED' where print_batch_id = :'b'", b=batch)
    step(7, f"{len(specs)} Druck-Batches gebildet, übergeben und gedruckt "
            f"({', '.join(specs)})")

    health = json.loads(sql("select row_to_json(v) from v_twin_health v"))
    step(8, f"Digitale Karten veröffentlicht: {health['veroeffentlicht']} von {health['twins_gesamt']}")

    print("\nDiese Codes stehen jetzt auf den gedruckten Karten:\n")
    tokens = json.loads(sql("""
      select coalesce(jsonb_agg(jsonb_build_object(
               'token', tw.public_token, 'player', p.display_name,
               'copy', ci.copy_index, 'of', ol.quantity) order by p.display_name, ci.copy_index), '[]'::jsonb)
        from card_twin tw join card_item ci on ci.card_twin_id = tw.id
        join order_line ol on ol.id = tw.order_line_id
        join person p on p.id = ol.person_id
       where tw.published_at is not null"""))
    for t in tokens:
        suffix = f"  (Karte {t['copy']} von {t['of']})" if t["of"] > 1 else ""
        print(f"    /k/{t['token']}   {t['player']}{suffix}")
    print(f"\n  {len(tokens)} abrufbare Karten. Nicht gedruckte Karten liefern "
          f"dieselbe Antwort wie unbekannte Codes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
