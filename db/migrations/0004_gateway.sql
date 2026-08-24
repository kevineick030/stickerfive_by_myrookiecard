-- =====================================================================
-- Trading-Card-Engine · 0004 · Partner-Gateway, Outbox, Ausbaufaehigkeit
--
-- Baut die Schicht, an der der Vertrag mit dem Partner haengt - und
-- schliesst drei Luecken, die spaeter teuer werden:
--   * doppelt an die Druckerei gesendete Auftraege (Outbox)
--   * stille Aenderungen an bereits angenommenen Auftraegen
--   * ein QR-Token, den ein anderes System vergibt
-- =====================================================================

-- --------------------------------------------------- 300 dpi als Untergrenze
-- Vorgabe des Auftraggebers. Als Constraint, damit sie niemand versehentlich
-- unterschreitet - auch nicht in zwei Jahren bei einem neuen Format.
alter table print_spec add constraint min_dpi_at_least_300 check (min_dpi >= 300);

-- --------------------------------------------------- Token von aussen
-- Falls der Partner (oder ein spaeteres Sammelalbum) die Kartenkennung
-- vergibt, wird sie uebernommen statt selbst erzeugt. Der Rest des Systems
-- merkt keinen Unterschied.
alter table card_twin
  add column token_source text not null default 'INTERNAL'
      check (token_source in ('INTERNAL', 'PARTNER')),
  add column external_token_ref text;

create unique index card_twin_external_ref
  on card_twin (external_token_ref) where external_token_ref is not null;

-- Ein fremd vergebener Token hat nicht unser Format. Die Formatpruefung gilt
-- deshalb nur fuer selbst erzeugte Token; fremde muessen lediglich URL-sicher
-- und in vernuenftiger Laenge sein. Ob der Code am Ende noch gross genug
-- gedruckt werden kann, entscheidet ohnehin die QR-Rechnung in Gate 1 -
-- ein sehr langer Token verkleinert die Module und faellt dort auf.
alter table card_twin drop constraint token_is_base58_22;
alter table card_twin add constraint token_format check (
  case token_source
    when 'INTERNAL' then public_token ~ '^[1-9A-HJ-NP-Za-km-z]{22}$'
    when 'PARTNER'  then public_token ~ '^[A-Za-z0-9_.-]{12,48}$'
  end
);

-- Ist beim Anlegen schon ein Twin gesetzt, wird keiner erzeugt.
create or replace function card_item_mint_twin() returns trigger
language plpgsql as $$
declare
  v_token_per_copy boolean;
  v_quantity       int;
  v_scope_copy     int;
  v_twin           uuid;
begin
  if new.card_twin_id is not null then
    return new;                      -- Token kam von aussen
  end if;

  select df.token_per_copy, ol.quantity
    into v_token_per_copy, v_quantity
    from order_line ol
    join design_version dv on dv.id = ol.design_version_id
    join design_family  df on df.id = dv.family_id
   where ol.id = new.order_line_id;

  if v_quantity is null then
    raise exception 'card_item: order_line % existiert nicht', new.order_line_id;
  end if;
  if new.copy_index > v_quantity then
    raise exception 'card_item: copy_index % ueberschreitet die bestellte Menge %',
      new.copy_index, v_quantity using errcode = 'check_violation';
  end if;

  v_scope_copy := case when v_token_per_copy then new.copy_index else null end;

  select id into v_twin from card_twin
   where order_line_id = new.order_line_id
     and coalesce(copy_index, -1) = coalesce(v_scope_copy, -1);

  if v_twin is null then
    insert into card_twin (public_token, order_line_id, copy_index)
    values (gen_twin_token(), new.order_line_id, v_scope_copy)
    returning id into v_twin;
  end if;

  new.card_twin_id := v_twin;
  return new;
end $$;

-- --------------------------------------------------- Outbox
-- Alles, was das System nach aussen schickt, geht hierueber. Ohne diese
-- Tabelle fuehrt ein Netzwerk-Timeout beim Transfer dazu, dass derselbe
-- Druckauftrag zweimal in der Druckerei landet - und Papier kostet Geld.
create type outbox_channel as enum ('PRINTER', 'PARTNER', 'MESSAGE', 'WEBHOOK');
create type outbox_state   as enum ('PENDING', 'IN_FLIGHT', 'SENT', 'FAILED', 'ABANDONED');

create table outbox (
  id              bigint generated always as identity primary key,
  channel         outbox_channel not null,
  -- Fachlicher Schluessel des Vorgangs. Zweimal dasselbe einstellen ist
  -- ein No-op, kein zweiter Versand.
  dedupe_key      text not null unique,
  subject_type    text not null,
  subject_id      uuid,
  payload         jsonb not null,
  state           outbox_state not null default 'PENDING',
  attempts        int not null default 0,
  max_attempts    int not null default 8,
  next_attempt_at timestamptz not null default now(),
  claimed_at      timestamptz,
  last_error      text,
  correlation_id  uuid not null,
  created_at      timestamptz not null default now(),
  sent_at         timestamptz
);
create index outbox_due on outbox (channel, next_attempt_at)
  where state in ('PENDING', 'FAILED');
create index outbox_stuck on outbox (claimed_at) where state = 'IN_FLIGHT';

-- Holt faellige Eintraege und sperrt sie gegen parallele Worker.
create or replace function outbox_claim(p_channel outbox_channel, p_limit int default 20)
returns setof outbox language plpgsql as $$
begin
  return query
  with due as (
    select id from outbox
     where channel = p_channel
       and state in ('PENDING', 'FAILED')
       and next_attempt_at <= now()
       and attempts < max_attempts
     order by next_attempt_at
     limit p_limit
     for update skip locked
  )
  update outbox o
     set state = 'IN_FLIGHT', claimed_at = now(), attempts = o.attempts + 1
    from due
   where o.id = due.id
  returning o.*;
end $$;

create or replace function outbox_settle(p_id bigint, p_ok boolean, p_error text default null)
returns void language plpgsql as $$
begin
  update outbox
     set state = (case when p_ok then 'SENT'
                       when attempts >= max_attempts then 'ABANDONED'
                       else 'FAILED' end)::outbox_state,
         sent_at = case when p_ok then now() end,
         last_error = case when p_ok then null else p_error end,
         -- Exponentielles Backoff, gedeckelt bei einer Stunde
         next_attempt_at = case when p_ok then next_attempt_at
                                else now() + least(interval '1 hour',
                                                   (power(2, attempts)::int || ' seconds')::interval)
                           end,
         claimed_at = null
   where id = p_id;
end $$;

-- --------------------------------------------------- Aenderungen nach Annahme
-- Der Partner darf Spielerdaten jederzeit aendern. Nach der Auftragsannahme
-- duerfen diese Aenderungen aber NICHT still in einen laufenden Druckauftrag
-- sickern - sonst weicht das Gedruckte vom Freigegebenen ab. Sie landen hier
-- und werden im Cockpit entschieden.
create type change_state as enum ('OPEN', 'APPLIED', 'REJECTED');

create table partner_change_request (
  id             uuid primary key default gen_random_uuid(),
  team_order_id  uuid not null references team_order(id) on delete cascade,
  person_id      uuid references person(id),
  field          text not null,
  old_value      text,
  new_value      text,
  state          change_state not null default 'OPEN',
  detected_at    timestamptz not null default now(),
  decided_at     timestamptz,
  decided_by     text,
  correlation_id uuid not null
);
create index change_request_open on partner_change_request (team_order_id)
  where state = 'OPEN';

-- --------------------------------------------------- Ingest-Laeufe
create table ingest_run (
  id             uuid primary key default gen_random_uuid(),
  partner_id     uuid not null references partner(id),
  kind           text not null check (kind in ('WEBHOOK', 'PULL', 'RECONCILE')),
  correlation_id uuid not null,
  payloads       int not null default 0,
  created_orders int not null default 0,
  changes_found  int not null default 0,
  errors         int not null default 0,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz
);

-- --------------------------------------------------- Unterstuetzte Vertragsversionen
-- Eine unbekannte Version wird laut abgelehnt statt still falsch gemappt.
-- Das ist der Unterschied zwischen einem Alarm und 60 falschen Karten.
create table partner_contract_version (
  partner_id      uuid not null references partner(id),
  payload_version text not null,
  supported_since timestamptz not null default now(),
  deprecated_at   timestamptz,
  schema_ref      text not null,
  primary key (partner_id, payload_version)
);

create or replace function assert_supported_version(p_partner uuid, p_version text)
returns void language plpgsql as $$
begin
  if not exists (select 1 from partner_contract_version
                  where partner_id = p_partner
                    and payload_version = p_version
                    and deprecated_at is null) then
    raise exception 'Partner-Payload in Version % wird nicht unterstuetzt — '
                    'Mapping abgelehnt, damit nichts falsch uebersetzt wird', p_version
      using errcode = 'check_violation';
  end if;
end $$;

-- --------------------------------------------------- Abgleich mit dem Partner
-- Webhooks gehen verloren. Diese Sicht zeigt, was der Partner zuletzt
-- geliefert hat und was daraus bei uns geworden ist.
create or replace view v_reconcile_orders as
select distinct on (pp.partner_id, pp.external_ref)
       pp.partner_id,
       pp.external_ref,
       pp.payload_version,
       pp.received_at,
       o.id                       as team_order_id,
       o.lifecycle_state,
       o.accepted_at,
       (select count(*) from order_line ol where ol.team_order_id = o.id) as lines_here,
       jsonb_array_length(coalesce(pp.raw -> 'order' -> 'players', '[]'::jsonb)) as players_in_payload,
       o.id is null               as missing_here
from partner_payload pp
left join team_order o
       on o.partner_id = pp.partner_id and o.external_ref = pp.external_ref
order by pp.partner_id, pp.external_ref, pp.received_at desc;

-- --------------------------------------------------- Partner-Onboarding
-- Ein Partner ist erst nutzbar, wenn klar ist, welche Vertragsversionen
-- er sprechen darf. Sonst waere die Versionspruefung wirkungslos.
create or replace function register_partner(
  p_code text, p_name text, p_deeplink text, p_versions text[], p_schema_ref text
) returns uuid language plpgsql as $$
declare v_id uuid; v_version text;
begin
  insert into partner (code, name, deeplink_template)
  values (p_code, p_name, p_deeplink)
  on conflict (code) do update
    set name = excluded.name, deeplink_template = excluded.deeplink_template
  returning id into v_id;

  foreach v_version in array p_versions loop
    insert into partner_contract_version (partner_id, payload_version, schema_ref)
    values (v_id, v_version, p_schema_ref)
    on conflict (partner_id, payload_version) do update
      set deprecated_at = null, schema_ref = excluded.schema_ref;
  end loop;
  return v_id;
end $$;
