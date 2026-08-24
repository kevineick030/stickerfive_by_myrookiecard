-- =====================================================================
-- Trading-Card-Engine · 0003 · Abgeleitete Sichten und Cockpit
--
-- Der Produktionsstatus einer Teambestellung wird ABGELEITET, nie gepflegt.
-- Ein separat gefuehrtes Statusfeld laeuft garantiert irgendwann auseinander.
-- =====================================================================

-- Basissicht: eine Zeile je physischer Karte, mit allem, was das Cockpit braucht.
create or replace view v_card_item as
select
  ci.id                       as card_item_id,
  ci.state,
  ci.copy_index,
  ci.artifact_fingerprint,
  ci.sheet_position,
  tw.public_token             as qr_token,
  tw.revoked_at               as twin_revoked_at,
  ol.id                       as order_line_id,
  ol.line_type,
  ol.quantity,
  ol.recipient_group_key,
  o.id                        as team_order_id,
  o.external_ref              as order_ref,
  o.correlation_id,
  o.hold_until,
  o.promised_delivery_at,
  o.fulfillment_policy,
  t.id                        as team_id,
  t.name                      as team_name,
  t.season,
  c.name                      as club_name,
  p.id                        as person_id,
  p.display_name              as player_name,
  p.role                      as player_role,
  p.is_minor,
  df.id                       as design_family,
  dv.version                  as design_version,
  dv.print_spec_id,
  ci.print_batch_id,
  ci.wave_id,
  a.quality_class             as photo_quality_class,
  exists (select 1 from blocker b
           where b.card_item_id = ci.id and b.resolved_at is null and b.severity = 'HARD')
                              as has_hard_blocker,
  exists (select 1 from blocker b
           where b.card_item_id = ci.id and b.resolved_at is null)
                              as has_open_blocker,
  (select min(b.opened_at) from blocker b
     where b.card_item_id = ci.id and b.resolved_at is null)
                              as oldest_blocker_opened_at
from card_item ci
join order_line     ol on ol.id = ci.order_line_id
join team_order     o  on o.id  = ol.team_order_id
join team           t  on t.id  = o.team_id
join club           c  on c.id  = t.club_id
join person         p  on p.id  = ol.person_id
join design_version dv on dv.id = ol.design_version_id
join design_family  df on df.id = dv.family_id
left join card_twin   tw on tw.id = ci.card_twin_id
left join media_asset a  on a.id  = ci.source_asset_id;

-- Der abgeleitete Produktionsstatus. Dies ist die DEFINITION, nicht ein Cache.
create or replace view v_team_order_production_status as
with items as (
  select ol.team_order_id, ci.id, ci.state,
         exists (select 1 from blocker b
                  where b.card_item_id = ci.id and b.resolved_at is null and b.severity = 'HARD') as hard_blocked,
         exists (select 1 from blocker b
                  where b.card_item_id = ci.id and b.resolved_at is null) as blocked
  from order_line ol
  join card_item ci on ci.order_line_id = ol.id
),
agg as (
  select team_order_id,
         count(*)                                                     as items_total,
         count(*) filter (where state = 'DELIVERED')                  as items_delivered,
         count(*) filter (where state = 'SHIPPED')                    as items_shipped,
         count(*) filter (where state = 'CANCELLED')                  as items_cancelled,
         count(*) filter (where state = 'BLOCKED')                    as items_blocked_state,
         count(*) filter (where blocked)                              as items_with_blocker,
         count(*) filter (where hard_blocked)                         as items_hard_blocked,
         count(*) filter (where state in ('DRAFT','DATA_VALIDATED'))  as items_not_started,
         count(*) filter (where state in ('SENT_TO_PRINT','PRINTED','PACKED','SHIPPED','DELIVERED')) as items_in_print_or_later
  from items group by team_order_id
)
select
  o.id as team_order_id,
  o.external_ref,
  o.lifecycle_state,
  coalesce(a.items_total, 0)          as items_total,
  coalesce(a.items_delivered, 0)      as items_delivered,
  coalesce(a.items_cancelled, 0)      as items_cancelled,
  coalesce(a.items_with_blocker, 0)   as items_with_blocker,
  coalesce(a.items_hard_blocked, 0)   as items_hard_blocked,
  case
    when o.lifecycle_state in ('CANCELLED','CLOSED','ON_HOLD') then o.lifecycle_state::text
    when coalesce(a.items_total, 0) = 0                        then 'RECEIVED'
    when a.items_delivered + a.items_cancelled = a.items_total then 'COMPLETE'
    when a.items_in_print_or_later > 0
     and a.items_in_print_or_later + a.items_cancelled < a.items_total then 'PARTIALLY_COMPLETE'
    when a.items_not_started < a.items_total                   then 'IN_PRODUCTION'
    else 'VALIDATING'
  end as derived_status,
  -- Terminrisiko: verbleibende Pufferzeit bis zur Zusage
  o.promised_delivery_at,
  o.promised_delivery_at - now() as time_to_promise
from team_order o
left join agg a on a.team_order_id = o.id;

-- ------------------------------------------------- Cockpit

-- Fotoqualitaet als Fruehindikator: kippt die Verteilung, steigt die
-- Retusche-Last drei Tage spaeter.
create or replace view v_cockpit_photo_quality as
select date_trunc('day', assessed_at)::date            as day,
       count(*)                                        as assessed,
       count(*) filter (where quality_class = 'A')     as class_a,
       count(*) filter (where quality_class = 'B')     as class_b,
       count(*) filter (where quality_class = 'C')     as class_c,
       round(100.0 * count(*) filter (where quality_class = 'C')
             / nullif(count(*), 0), 1)                 as class_c_pct
from photo_assessment
where source = 'GATE0' and assessed_at > now() - interval '30 days'
group by 1 order by 1 desc;

-- Alter schlaegt Tiefe: eine tiefe, schnell abfliessende Queue ist gesund,
-- ein alter Eintrag in einer flachen Queue heisst, es haengt.
create or replace view v_cockpit_blocker_queue as
select b.reason,
       bc.label_de,
       b.severity,
       b.owner,
       count(*)                        as open_count,
       min(b.opened_at)                as oldest_opened_at,
       now() - min(b.opened_at)        as oldest_age
from blocker b
join blocker_catalog bc on bc.reason = b.reason
where b.resolved_at is null
group by b.reason, bc.label_de, b.severity, b.owner
order by b.severity, oldest_opened_at;

create or replace view v_cockpit_qa as
select count(*)                                                          as verdicts,
       count(*) filter (where decision = 'PASS' and decided_by = 'SYSTEM') as auto_passed,
       count(*) filter (where decision = 'REVIEW')                        as in_review,
       count(*) filter (where decision = 'FAIL')                          as failed,
       round(100.0 * count(*) filter (where decision = 'PASS' and decided_by = 'SYSTEM')
             / nullif(count(*), 0), 2)                                    as auto_pass_rate_pct
from qa_verdict
where decided_at > now() - interval '24 hours';

-- Unquittierte Batches sind ein Vorfall, kein Zustand.
create or replace view v_cockpit_print_batches as
select pb.id, pb.print_spec_id, pb.state,
       count(ci.id)                as cards,
       pb.transferred_at,
       pb.acknowledged_at,
       case when pb.transferred_at is not null and pb.acknowledged_at is null
            then now() - pb.transferred_at end as unacknowledged_for
from print_batch pb
left join card_item ci on ci.print_batch_id = pb.id
group by pb.id
order by pb.created_at desc;

-- Das Team-Board: eine Zeile je Karte, farbcodierbar.
create or replace view v_team_board as
select team_order_id, order_ref, team_name, club_name,
       card_item_id, player_name, player_role, design_family,
       -- Kopie x von y: y ist die Menge DIESER Bestellzeile, nicht die Zahl
       -- gleichnamiger Personen. Zwei Kinder koennen gleich heissen.
       copy_index, quantity,
       state, qr_token, photo_quality_class,
       case when state = 'CANCELLED'   then 'CANCELLED'
            when has_hard_blocker       then 'HARD'
            when has_open_blocker       then 'SOFT'
            when state = 'DELIVERED'    then 'DONE'
            else 'OK' end as board_status,
       oldest_blocker_opened_at
from v_card_item
order by team_order_id, player_name, copy_index;

-- Aufbewahrung: zwei Uhren, die getrennt laufen. Rohbild kurz, Freisteller
-- und Druckartefakt mittel, digitale Karte dauerhaft.
create or replace view v_retention_due as
select id as asset_id, person_id, retention_class, delete_after, created_at
from media_asset
where deleted_at is null and delete_after is not null and delete_after <= now()
order by delete_after;
