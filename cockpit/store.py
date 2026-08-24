"""Datenzugriff des Cockpits.

Liest ausschliesslich aus den Sichten in db/migrations - die Oberflaeche
enthaelt keine Fachlogik. Schreibend gibt es genau eine Funktion: den
Not-Aus. Alles andere entscheidet die Datenbank.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{12,48}$")


class CockpitStore:
    def __init__(self, psql: str = "psql"):
        self.psql = psql

    # ------------------------------------------------------------------
    def _run(self, sql: str, **params: str) -> str:
        cmd = [self.psql, "-tAq", "-v", "ON_ERROR_STOP=1"]
        for key, value in params.items():
            cmd += ["-v", f"{key}={value}"]
        done = subprocess.run(cmd, input=sql, capture_output=True, text=True,
                              env=os.environ, timeout=20)
        if done.returncode != 0:
            raise RuntimeError(done.stderr.strip()[:500])
        return done.stdout.strip()

    def rows(self, select: str, **params: str) -> list[dict]:
        raw = self._run(f"select coalesce(json_agg(t), '[]'::json) from ({select}) t", **params)
        return json.loads(raw) if raw else []

    def row(self, select: str, **params: str) -> dict | None:
        found = self.rows(select, **params)
        return found[0] if found else None

    # ------------------------------------------------------------------
    def tiles(self) -> dict:
        return self.row("select * from v_cockpit_tiles") or {}

    def photo_trend(self) -> list[dict]:
        return self.rows("select * from v_cockpit_photo_trend")

    def qa_sparkline(self) -> list[dict]:
        return self.rows("""
          select d::date as day,
                 round(100.0 * count(*) filter (where q.decision = 'PASS' and q.decided_by = 'SYSTEM')
                       / nullif(count(q.*), 0), 1) as pct
            from generate_series(current_date - 13, current_date, interval '1 day') d
            left join qa_verdict q on q.decided_at::date = d::date
           group by d order by d""")

    def blocker_queue(self) -> list[dict]:
        return self.rows("select * from v_cockpit_blocker_queue")

    def orders(self) -> list[dict]:
        return self.rows("select * from v_cockpit_orders")

    def outbox(self) -> list[dict]:
        return self.rows("select * from v_cockpit_outbox")

    def changes(self) -> list[dict]:
        return self.rows("""
          select cr.field, cr.old_value, cr.new_value, cr.detected_at,
                 p.display_name, o.external_ref
            from partner_change_request cr
            join team_order o on o.id = cr.team_order_id
            left join person p on p.id = cr.person_id
           where cr.state = 'OPEN' order by cr.detected_at desc limit 20""")

    def batches(self) -> list[dict]:
        return self.rows("select * from v_cockpit_print_batches limit 12")

    def board(self, order_id: str) -> list[dict]:
        if not UUID_RE.match(order_id):
            return []
        return self.rows("select * from v_team_board where team_order_id = :'o'", o=order_id)

    def order_head(self, order_id: str) -> dict | None:
        if not UUID_RE.match(order_id):
            return None
        return self.row("select * from v_cockpit_orders where team_order_id = :'o'", o=order_id)

    def card(self, card_id: str) -> dict | None:
        if not UUID_RE.match(card_id):
            return None
        return self.row("select * from v_card_item where card_item_id = :'c'", c=card_id)

    def card_blockers(self, card_id: str) -> list[dict]:
        if not UUID_RE.match(card_id):
            return []
        return self.rows("""
          select b.reason, bc.label_de, b.severity, b.owner, b.opened_at, b.resolved_at
            from blocker b join blocker_catalog bc on bc.reason = b.reason
           where b.card_item_id = :'c' order by b.opened_at desc""", c=card_id)

    def card_events(self, correlation: str) -> list[dict]:
        if not UUID_RE.match(correlation):
            return []
        return self.rows("""
          select event_type, actor, occurred_at, payload
            from domain_event where correlation_id = :'k'
           order by id desc limit 25""", k=correlation)

    def search(self, term: str) -> list[dict]:
        term = (term or "").strip()[:80]
        if len(term) < 2:
            return []
        return self.rows("""
          select card_item_id, player_name, club_name, team_name, order_ref,
                 state, qr_token, team_order_id, design_family, copy_index
            from v_card_item
           where player_name ilike '%' || :'q' || '%'
              or order_ref   ilike '%' || :'q' || '%'
              or qr_token = :'q'
           order by player_name, copy_index limit 60""", q=term)

    # ------------------------------------------------------------------
    def set_transfers_paused(self, paused: bool, actor: str) -> None:
        self._run("select set_config_value('ops.transfers_paused', :'v', :'a')",
                  v="true" if paused else "false", a=actor[:40])
