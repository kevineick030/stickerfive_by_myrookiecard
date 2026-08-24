-- =====================================================================
-- Trading-Card-Engine · 0007 · Cockpit und Not-Aus
-- =====================================================================

-- --------------------------------------------------- Not-Aus
-- Ab dem Transfer kostet jeder Fehler Papier und Zeit. Dieser Schalter ist
-- die billigste Versicherung im ganzen System - und er wirkt in der
-- Datenbank, nicht in der Oberflaeche, damit ihn auch ein Hintergrunddienst
-- nicht umgehen kann.
insert into system_config (key, value, unit, is_placeholder, description_de)
values ('ops.transfers_paused', 'false', null, false,
        'Not-Aus: hält alle Übertragungen an die Druckerei an')
on conflict (key) do nothing;

create or replace function transfers_paused() returns boolean
language sql stable as $$
  select coalesce((select value from system_config where key = 'ops.transfers_paused'), 'false') = 'true'
$$;

create or replace function print_batch_guard() returns trigger
language plpgsql as $$
declare v_open int; v_total int; v_max_age interval;
begin
  if new.transferred_at is not null and old.transferred_at is null then

    if transfers_paused() then
      raise exception 'print_batch %: Not-Aus aktiv — keine Übertragung an die Druckerei', new.id
        using errcode = 'check_violation';
    end if;

    if new.manifest_hash is null then
      raise exception 'print_batch %: Transfer ohne Manifest-Hash', new.id
        using errcode = 'check_violation';
    end if;

    v_max_age := (coalesce((select value from system_config
                             where key = 'consent.revalidation_max_age_minutes'), '30')
                  || ' minutes')::interval;
    if new.consent_revalidated_at is null
       or new.consent_revalidated_at < now() - v_max_age then
      raise exception 'print_batch %: Einwilligungen nicht frisch revalidiert (max %)',
        new.id, v_max_age using errcode = 'check_violation';
    end if;

    select count(*), count(*) filter (where ci.state <> 'BATCHED')
      into v_total, v_open
      from card_item ci where ci.print_batch_id = new.id;

    if v_total = 0 then
      raise exception 'print_batch %: leerer Batch', new.id using errcode = 'check_violation';
    end if;
    if v_open > 0 then
      raise exception 'print_batch %: % von % Karten sind nicht im Zustand BATCHED',
        new.id, v_open, v_total using errcode = 'check_violation';
    end if;

    new.state := 'TRANSFERRED';
  end if;
  return new;
end $$;

create or replace function set_config_value(p_key text, p_value text, p_actor text)
returns void language plpgsql as $$
begin
  update system_config set value = p_value, changed_by = p_actor, changed_at = now()
   where key = p_key;
  if not found then
    raise exception 'Unbekannter Konfigurationsschlüssel %', p_key using errcode = 'check_violation';
  end if;
  insert into domain_event (correlation_id, subject_type, event_type, payload, actor)
  values (gen_random_uuid(), 'system_config', 'config.changed',
          jsonb_build_object('key', p_key, 'value', p_value), p_actor);
end $$;

-- --------------------------------------------------- Kennzahlen
-- Eine Zeile mit allem, was die Statusleiste braucht.
create or replace view v_cockpit_tiles as
with items as (select ci.*, ol.team_order_id from card_item ci
                 join order_line ol on ol.id = ci.order_line_id),
qa as (select * from v_cockpit_qa),
photo as (select count(*) filter (where quality_class = 'C')::numeric
                 / nullif(count(*), 0) * 100 as class_c_pct,
                 count(*) as assessed
            from photo_assessment
           where source = 'GATE0' and assessed_at > now() - interval '7 days')
select
  (select auto_pass_rate_pct from qa)                                        as auto_pass_rate_pct,
  (select verdicts from qa)                                                  as qa_verdicts_24h,
  (select in_review from qa)                                                 as qa_in_review,
  (select round(class_c_pct, 1) from photo)                                  as photo_class_c_pct,
  (select assessed from photo)                                               as photo_assessed_7d,
  (select count(*) from items where state not in ('DELIVERED','CANCELLED'))  as cards_open,
  (select count(*) from items where state = 'PRINTED')                       as cards_printed,
  (select count(*) from blocker where resolved_at is null and severity = 'HARD') as blockers_hard,
  (select count(*) from blocker where resolved_at is null and severity = 'SOFT') as blockers_soft,
  (select count(*) from items i
     where i.state in ('DRAFT','DATA_VALIDATED') and i.source_asset_id is null) as photos_pending,
  (select extract(epoch from now() - min(updated_at))::int from items
     where state in ('RENDER_QUEUED','ASSET_READY','RENDERED'))              as oldest_working_seconds,
  (select count(*) from print_batch
     where transferred_at is not null and acknowledged_at is null)           as batches_unacknowledged,
  (select count(*) from print_batch where state = 'OPEN')                    as batches_open,
  (select count(*) from outbox where state in ('FAILED','ABANDONED'))        as outbox_failed,
  (select count(*) from outbox where state = 'PENDING')                      as outbox_pending,
  (select count(*) from partner_change_request where state = 'OPEN')         as changes_open,
  (select count(*) from team_order o
     where o.promised_delivery_at is not null
       and o.promised_delivery_at < now() + interval '3 days'
       and o.lifecycle_state not in ('CLOSED','CANCELLED'))                  as orders_at_risk,
  transfers_paused()                                                          as transfers_paused;

-- Tagesreihe fuer den Fruehindikator. Der Betreiber fragt nicht nach der
-- Verteilung, sondern ob der Ausschuss steigt - deshalb eine Reihe, kein Stapel.
create or replace view v_cockpit_photo_trend as
select d::date                                                       as day,
       count(pa.*)                                                   as assessed,
       count(*) filter (where pa.quality_class = 'A')                as class_a,
       count(*) filter (where pa.quality_class = 'B')                as class_b,
       count(*) filter (where pa.quality_class = 'C')                as class_c,
       round(100.0 * count(*) filter (where pa.quality_class = 'C')
             / nullif(count(pa.*), 0), 1)                            as class_c_pct
from generate_series(current_date - 13, current_date, interval '1 day') d
left join photo_assessment pa
       on pa.source = 'GATE0' and pa.assessed_at::date = d::date
group by d order by d;

create or replace view v_cockpit_orders as
select s.team_order_id, s.external_ref, s.derived_status, s.items_total,
       s.items_delivered, s.items_with_blocker, s.items_hard_blocked,
       c.name as club_name, t.name as team_name, t.season,
       o.promised_delivery_at, o.hold_until, o.fulfillment_policy,
       o.promised_delivery_at - now() as puffer
from v_team_order_production_status s
join team_order o on o.id = s.team_order_id
join team t on t.id = o.team_id
join club c on c.id = t.club_id
order by o.promised_delivery_at nulls last;

create or replace view v_cockpit_outbox as
select channel, state, count(*) as eintraege,
       min(next_attempt_at) as naechster_versuch,
       max(attempts) as meiste_versuche,
       (array_agg(left(last_error, 80) order by id desc)
          filter (where last_error is not null))[1] as letzter_fehler
from outbox group by channel, state order by channel, state;
