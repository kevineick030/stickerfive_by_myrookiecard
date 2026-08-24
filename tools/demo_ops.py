#!/usr/bin/env python3
"""Legt Betriebsdaten an, damit das Cockpit einen echten Tag zeigt.

  python3 tools/demo_flow.py && python3 tools/demo_ops.py

Drei weitere Teambestellungen in verschiedenen Zuständen, Blocker, eine
Fotoqualitätsreihe über 14 Tage mit steigendem Ausschuss, Outbox-Einträge
und ein Änderungsantrag nach Auftragsannahme.
"""
from __future__ import annotations

import json, os, pathlib, random, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from gateway.contract import Contract     # noqa: E402
from gateway.mapping import Mapper        # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
random.seed(20260824)

VORNAMEN = ["Ben", "Emil", "Noah", "Luis", "Finn", "Jonas", "Paul", "Elias", "Leon", "Theo",
            "Mila", "Emma", "Lina", "Ida", "Marie", "Lea", "Nele", "Frieda", "Ella", "Anna",
            "Jakob", "Anton", "Karl", "Moritz"]
NACHNAMEN = ["Berger", "Hofmann", "Krüger", "Lange", "Vogel", "Sommer", "Winkler", "Böhm",
             "Reuter", "Kraus", "Seidel", "Fuchs", "Arnold", "Hartmann", "Ziegler", "Peters",
             "Kuhn", "Beck", "Roth", "Schuster", "Bauer", "Weiß", "Dietrich", "Nowak"]

TEAMS = [
    dict(ref="SK-2026-0043", club=("V-5120", "SV Grünberg"), team=("M-91", "E-Jugend", "25/26"),
         players=18, no_photo=0, kontakt=("Marcus Reindl", "vorstand@sv-gruenberg.example"),
         profil="DELIVERED"),
    dict(ref="SK-2026-0044", club=("V-6033", "FC Talblick"), team=("M-104", "C-Jugend", "25/26"),
         players=22, no_photo=3, kontakt=("Yasemin Öztürk", "jugend@fc-talblick.example"),
         profil="AT_RISK"),
    dict(ref="SK-2026-0045", club=("V-7781", "TuS Hafen"), team=("M-77", "D-Jugend", "25/26"),
         players=14, no_photo=1, kontakt=("Sven Kolbe", "kontakt@tus-hafen.example"),
         profil="IN_PRODUCTION"),
]


def sql(query: str, **params: str) -> str:
    cmd = ["psql", "-tAq", "-v", "ON_ERROR_STOP=1"]
    for k, v in params.items():
        cmd += ["-v", f"{k}={v}"]
    done = subprocess.run(cmd, input=query, capture_output=True, text=True, env=os.environ)
    if done.returncode != 0:
        raise SystemExit(f"SQL fehlgeschlagen:\n{done.stderr.strip()}")
    return done.stdout.strip()


def raw_order(spec: dict) -> dict:
    """Baut die Rohform des Partners - so laeuft auch der Uebersetzer mit."""
    spieler = []
    for i in range(spec["players"]):
        vor, nach = random.choice(VORNAMEN), random.choice(NACHNAMEN)
        pos = "Torwart" if i == 0 else ("Trainer" if i == 1 else "Feldspieler")
        eintrag = {
            "id": f"{spec['ref']}-P{i+1:03d}",
            "vorname": vor, "nachname": nach, "position": pos,
            "rueckennummer": i + 1, "minderjaehrig": "nein" if pos == "Trainer" else "ja",
            "erziehungsberechtigter": {"name": f"{nach}, Familie",
                                       "email": f"familie.{nach.lower()}@example.org"},
            "anzahl_karten": random.choice([1, 1, 1, 1, 2, 3]),
            "einwilligung": {"id": f"EW-{spec['ref']}-{i+1:03d}",
                             "textversion": "einwilligung-2026-03",
                             "erteilt_von": "selbst" if pos == "Trainer" else "Eltern",
                             "zeitpunkt": "2026-08-05T09:00:00Z"},
        }
        if i >= spec["no_photo"]:
            eintrag["foto"] = {
                "sha256": f"{random.getrandbits(256):064x}",
                "url": f"https://partner.example/media/{spec['ref']}-{i+1}",
                "typ": random.choice(["image/jpeg", "image/jpeg", "image/heic"]),
                "breite": random.choice([1600, 1800, 2000, 2400]),
                "hoehe": random.choice([2000, 2400, 2600, 3000]),
            }
        spieler.append(eintrag)
    return {
        "verein": {"id": spec["club"][0], "name": spec["club"][1]},
        "mannschaft": {"id": spec["team"][0], "name": spec["team"][1],
                       "saison": spec["team"][2], "altersklasse": spec["team"][1][0]},
        "auftrag": {"nummer": spec["ref"],
                    "besteller": {"name": spec["kontakt"][0], "email": spec["kontakt"][1]},
                    "spieler": spieler},
    }


def main() -> int:
    mapper = Mapper.load(ROOT / "specs" / "partner_mapping.stickerkoenig.v1.json")
    contract = Contract.load(ROOT / "specs" / "partner_payload.v1.schema.json")
    print("Betriebsdaten\n")

    for spec in TEAMS:
        payload = mapper.to_payload(raw_order(spec))
        violations = contract.validate(payload)
        if violations:
            raise SystemExit("; ".join(str(v) for v in violations))
        order = sql("select ingest_team_order('SK', :'p'::jsonb)",
                    p=json.dumps(payload, ensure_ascii=False))
        sql("select accept_team_order(:'o','demo')", o=order)

        # Karten ohne Foto bekommen einen Blocker, alle anderen laufen weiter.
        sql("""insert into blocker (card_item_id, reason, detail)
               select ci.id, 'PHOTO_MISSING', 'vom Kunden noch nicht hochgeladen'
                 from card_item ci join order_line ol on ol.id = ci.order_line_id
                where ol.team_order_id = :'o' and ci.source_asset_id is null
               on conflict do nothing;
               update card_item ci set state = 'BLOCKED'
                 from order_line ol
                where ol.id = ci.order_line_id and ol.team_order_id = :'o'
                  and ci.source_asset_id is null;""", o=order)

        if spec["profil"] == "DELIVERED":
            for state in ("DATA_VALIDATED", "PHOTO_ACCEPTED", "ASSET_READY", "RENDER_QUEUED",
                          "RENDERED", "QA_PASSED", "APPROVED"):
                sql("""update card_item ci set state = :'s' from order_line ol
                        where ol.id = ci.order_line_id and ol.team_order_id = :'o'
                          and ci.state <> 'BLOCKED'""", s=state, o=order)
            sql("""update team_order set lifecycle_state = 'CLOSED',
                     promised_delivery_at = now() - interval '4 days' where id = :'o'""", o=order)
        elif spec["profil"] == "AT_RISK":
            for state in ("DATA_VALIDATED", "PHOTO_ACCEPTED", "ASSET_READY", "RENDER_QUEUED"):
                sql("""update card_item ci set state = :'s' from order_line ol
                        where ol.id = ci.order_line_id and ol.team_order_id = :'o'
                          and ci.state <> 'BLOCKED'""", s=state, o=order)
            sql("""update team_order set promised_delivery_at = now() + interval '31 hours',
                     hold_until = now() + interval '2 days' where id = :'o'""", o=order)
            # Eine Einwilligung ist widerrufen worden - harter Blocker.
            sql("""update consent_assertion set revoked_at = now()
                    where person_id = (select ol.person_id from order_line ol
                                        where ol.team_order_id = :'o' order by ol.id limit 1);
                   insert into blocker (card_item_id, reason, detail)
                   select ci.id, 'CONSENT_REVOKED', 'Widerruf über Partner-Webhook'
                     from card_item ci join order_line ol on ol.id = ci.order_line_id
                    where ol.team_order_id = :'o'
                      and ol.person_id = (select ol2.person_id from order_line ol2
                                           where ol2.team_order_id = :'o' order by ol2.id limit 1)
                   on conflict do nothing;
                   update card_item ci set state = 'BLOCKED' from order_line ol
                    where ol.id = ci.order_line_id and ol.team_order_id = :'o'
                      and ol.person_id = (select ol2.person_id from order_line ol2
                                           where ol2.team_order_id = :'o' order by ol2.id limit 1);""",
                o=order)
        else:
            for state in ("DATA_VALIDATED", "PHOTO_ACCEPTED", "ASSET_READY"):
                sql("""update card_item ci set state = :'s' from order_line ol
                        where ol.id = ci.order_line_id and ol.team_order_id = :'o'
                          and ci.state <> 'BLOCKED'""", s=state, o=order)
            sql("""update team_order set promised_delivery_at = now() + interval '9 days'
                    where id = :'o'""", o=order)

        cards = sql("""select count(*) from card_item ci join order_line ol
                        on ol.id = ci.order_line_id where ol.team_order_id = :'o'""", o=order)
        print(f"  {spec['club'][1]:16s} {spec['team'][1]:11s} "
              f"{spec['players']:>3} Spieler · {cards:>3} Karten · {spec['profil']}")

    # ---------------------------------------------------- Fotoqualität
    # Der Ausschuss steigt über zwei Wochen von 4 auf 11 Prozent - genau der
    # Frühindikator, den das Cockpit sichtbar machen soll.
    sql("""insert into media_asset (partner_id, person_id, origin, content_hash, storage_ref,
                                    mime_type, retention_class)
           select p.id, null, 'INTERNAL', md5(g::text)||md5(g::text||'x'),
                  'demo://trend/'||g, 'image/jpeg', 'RAW_UPLOAD'
             from generate_series(1, 40) g, partner p where p.code = 'SK'
           on conflict do nothing;""")
    for day in range(13, -1, -1):
        share = 4.0 + (13 - day) * 0.55
        total = random.randint(150, 260)
        c = max(1, round(total * share / 100))
        b = round(total * 0.21)
        sql("""insert into photo_assessment (asset_id, spec_version, quality_class, source, assessed_at)
               select a.id, '1.0.0',
                      (case when n <= :c then 'C' when n <= :c + :b then 'B' else 'A' end)::quality_class,
                      'GATE0', now() - (:d || ' days')::interval
                 from generate_series(1, :total) n
                 join lateral (select id from media_asset where origin = 'INTERNAL'
                                order by md5(id::text || n::text) limit 1) a on true;""",
            c=str(c), b=str(b), total=str(total), d=str(day))
    print(f"\n  Fotoqualität: 14 Tage, Ausschuss steigt von 4,0 auf "
          f"{4.0 + 13 * 0.55:.1f} Prozent")

    # ---------------------------------------------------- Outbox und Änderungen
    sql("""insert into outbox (channel, dedupe_key, subject_type, payload, correlation_id,
                               state, attempts, last_error, next_attempt_at)
           values ('PRINTER','batch:sk-0044-std','print_batch','{"cards":19}'::jsonb,
                   gen_random_uuid(),'FAILED',3,'Zeitüberschreitung beim Upload',
                   now() + interval '4 minutes'),
                  ('MESSAGE','notify:sk-0044-photos','team_order','{"empfaenger":3}'::jsonb,
                   gen_random_uuid(),'PENDING',0,null,now()),
                  ('MESSAGE','notify:sk-0045-photos','team_order','{"empfaenger":1}'::jsonb,
                   gen_random_uuid(),'PENDING',0,null,now()),
                  ('PARTNER','revalidate:sk-0043','team_order','{}'::jsonb,
                   gen_random_uuid(),'SENT',1,null,now())
           on conflict (dedupe_key) do nothing;""")

    sql("""insert into partner_change_request (team_order_id, person_id, field, old_value,
                                               new_value, correlation_id)
           select o.id, ol.person_id, 'display_name', p.display_name,
                  p.display_name || 'r', o.correlation_id
             from team_order o
             join order_line ol on ol.team_order_id = o.id
             join person p on p.id = ol.person_id
            where o.external_ref = 'SK-2026-0045'
            order by ol.id limit 1;""")

    tiles = json.loads(sql("select row_to_json(t) from v_cockpit_tiles t"))
    print(f"""
  Stand im Cockpit:
    Auto-Pass-Rate       {tiles['auto_pass_rate_pct']} %
    Ausschuss (7 Tage)   {tiles['photo_class_c_pct']} %
    Offene Karten        {tiles['cards_open']}
    Blocker              {tiles['blockers_hard']} hart · {tiles['blockers_soft']} weich
    Fotos ausstehend     {tiles['photos_pending']}
    Termin-Risiko        {tiles['orders_at_risk']} Aufträge
    Outbox               {tiles['outbox_pending']} offen · {tiles['outbox_failed']} fehlgeschlagen
    Änderungsanträge     {tiles['changes_open']}""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
