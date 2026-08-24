-- =====================================================================
-- Trading-Card-Engine · Gateway-Test
-- Prueft die Aufnahme von Partnerdaten Ende zu Ende, in einer
-- zurueckgerollten Transaktion.
-- =====================================================================
\set ON_ERROR_STOP on
begin;

create or replace function must_fail(p_sql text, p_label text) returns void
language plpgsql as $$
declare v_failed boolean := false; v_msg text;
begin
  begin execute p_sql; exception when others then v_failed := true; v_msg := sqlerrm; end;
  if not v_failed then
    raise exception 'TEST FEHLGESCHLAGEN: "%" haette abgelehnt werden muessen', p_label;
  end if;
  raise notice '  verriegelt: % (%)', p_label, left(v_msg, 74);
end $$;

select register_partner('SK', 'Sticker-König',
       'https://partner.example/upload?player={external_ref}',
       array['1.0'], 'specs/partner_payload.v1.schema.json') as partner_id \gset

-- Vertragsversion, die niemand freigeschaltet hat, wird laut abgelehnt.
select must_fail($$
  select ingest_team_order('SK', '{"payload_version":"9.9","order":{"external_ref":"X"}}'::jsonb)
$$, 'nicht freigeschaltete Vertragsversion');

select must_fail($$
  select ingest_team_order('UNBEKANNT', '{"payload_version":"1.0","order":{"external_ref":"X"}}'::jsonb)
$$, 'unbekannter Partner');

-- ------------------------------------------------------------ Aufnahme
\set payload '{"payload_version":"1.0","order":{"external_ref":"SK-2026-0042","fulfillment_policy":"PARTIAL_WITH_HOLD","club":{"external_ref":"V-4711","name":"TSV Musterstadt e.V."},"team":{"external_ref":"M-88","name":"D-Jugend","season":"25/26","sport":"Fussball","age_group":"D"},"ordering_contact":{"name":"Andrea Wolters","email":"trainerin@tsv-musterstadt.example"},"players":[{"external_ref":"SP-1001","display_name":"Lukas Meier","role":"FIELD","jersey_number":"7","is_minor":true,"guardian_contact_email":"s.meier@example.org","quantity":3,"consent":{"consent_id":"EW-1001","text_version":"einwilligung-2026-03","subject_type":"GUARDIAN","granted_at":"2026-08-01T10:14:00Z"},"photo":{"content_hash":"aa11bb22cc33dd44ee55ff6677889900aa11bb22cc33dd44ee55ff6677889900","storage_ref":"https://partner.example/m/1","mime_type":"image/jpeg","width_px":1800,"height_px":2400}},{"external_ref":"SP-1002","display_name":"Tim Klein","role":"KEEPER","jersey_number":"1","is_minor":true,"guardian_contact_email":"j.klein@example.org","consent":{"consent_id":"EW-1002","text_version":"einwilligung-2026-03","subject_type":"GUARDIAN","granted_at":"2026-08-01T10:20:00Z"},"photo":{"content_hash":"bb22cc33dd44ee55ff6677889900aa11bb22cc33dd44ee55ff6677889900aa11","storage_ref":"https://partner.example/m/2","mime_type":"image/jpeg","width_px":1600,"height_px":2000}},{"external_ref":"SP-1003","display_name":"Đorđe Đorđević","role":"COACH","is_minor":false,"contact_email":"dj@example.org","consent":{"consent_id":"EW-1003","text_version":"einwilligung-2026-03","subject_type":"SELF","granted_at":"2026-08-02T08:00:00Z"}}]}}'

select ingest_team_order('SK', :'payload'::jsonb) as order_id \gset

select (select count(*) from team_order)                                as auftraege,
       (select count(*) from order_line where team_order_id = :'order_id') as zeilen,
       (select count(*) from card_item ci join order_line ol on ol.id = ci.order_line_id
         where ol.team_order_id = :'order_id')                          as karten,
       (select count(*) from consent_assertion)                         as einwilligungen,
       (select count(*) from media_asset)                               as fotos;

-- Design nach Rolle, ohne dass es im Payload stand.
select p.display_name, p.role, dv.family_id as design, ol.quantity
  from order_line ol join person p on p.id = ol.person_id
  join design_version dv on dv.id = ol.design_version_id
 where ol.team_order_id = :'order_id' order by p.external_ref;

-- Jede Kopie hat ihren eigenen QR-Token.
select count(*) as meier_karten, count(distinct ci.card_twin_id) as meier_token
  from card_item ci join order_line ol on ol.id = ci.order_line_id
  join person p on p.id = ol.person_id
 where p.external_ref = 'SP-1001';

-- ------------------------------------------------------------ Idempotenz
select ingest_team_order('SK', :'payload'::jsonb) as wieder \gset
select (select count(*) from team_order)          as auftraege_nach_wiederholung,
       (select count(*) from order_line where team_order_id = :'order_id') as zeilen_unveraendert,
       (select count(*) from partner_payload)     as archivzeilen,
       (:'wieder' = :'order_id')                  as gleicher_auftrag;

-- ------------------------------------------------------------ Annahme
select length(accept_team_order(:'order_id', 'test')) as snapshot_hash_laenge \gset
select lifecycle_state, snapshot_hash is not null as eingefroren,
       hold_until is not null as karenzfrist_gesetzt,
       promised_delivery_at is not null as termin_gesetzt,
       jsonb_array_length(snapshot -> 'lines') as zeilen_im_snapshot
  from team_order where id = :'order_id';

select must_fail(format('select accept_team_order(%L)', :'order_id'),
                 'zweimalige Annahme desselben Auftrags');

-- ------------------------------------------------------------ Aenderung danach
-- Der Partner korrigiert einen Namen NACH der Annahme. Das darf nicht still
-- in den laufenden Auftrag sickern.
select ingest_team_order('SK', replace(:'payload', 'Lukas Meier', 'Lukas Meyer')::jsonb);

select (select display_name from person where external_ref = 'SP-1001') as name_unveraendert,
       (select count(*) from partner_change_request where state = 'OPEN') as offene_aenderungen,
       (select new_value from partner_change_request where state = 'OPEN' limit 1) as vorgeschlagen;

-- ------------------------------------------------------------ Outbox
insert into outbox (channel, dedupe_key, subject_type, subject_id, payload, correlation_id)
values ('PRINTER', 'batch:demo-1', 'print_batch', gen_random_uuid(), '{"cards":60}'::jsonb, gen_random_uuid());

-- Derselbe Vorgang zweimal eingestellt: kein zweiter Versand.
insert into outbox (channel, dedupe_key, subject_type, payload, correlation_id)
values ('PRINTER', 'batch:demo-1', 'print_batch', '{"cards":60}'::jsonb, gen_random_uuid())
on conflict (dedupe_key) do nothing;
select count(*) as outbox_eintraege_nach_doppelter_einstellung from outbox;

select id as ob_id, state as ob_state, attempts as ob_attempts
  from outbox_claim('PRINTER') \gset
select :'ob_state' as zustand_nach_claim, :ob_attempts as versuche;

-- Zweiter Worker bekommt nichts mehr: der Eintrag ist gesperrt.
select count(*) as zweiter_worker_bekommt from outbox_claim('PRINTER');

select outbox_settle(:ob_id, false, 'Druckerei nicht erreichbar');
select state as nach_fehlschlag, attempts,
       next_attempt_at > now() as wartet_auf_wiederholung,
       left(last_error, 26) as fehler from outbox where id = :ob_id;

select outbox_settle(:ob_id, true);
select state as nach_erfolg, sent_at is not null as gesendet from outbox where id = :ob_id;

-- ------------------------------------------------------------ Token von aussen
insert into card_twin (public_token, order_line_id, copy_index, token_source, external_token_ref)
select 'SK-CARD-9999-a1b2c3', ol.id, 99, 'PARTNER', 'SK-CARD-9999'
  from order_line ol where ol.team_order_id = :'order_id' limit 1;
select token_source, public_token, external_token_ref from card_twin where copy_index = 99;

-- Unser eigenes Format bleibt streng: keine verwechselbaren Zeichen.
select must_fail($$
  insert into card_twin (public_token, order_line_id, copy_index)
  select 'O0Il-verwechselbar12', ol.id, 98 from order_line ol limit 1
$$, 'selbst erzeugter Token mit verwechselbaren Zeichen');

-- ------------------------------------------------------------ 300 dpi
select must_fail($$ update print_spec set min_dpi = 150 where id = 'PS-STD' $$,
                 'Druckqualitaet unter 300 dpi');

-- ------------------------------------------------------------ Abgleich
select external_ref, lines_here, players_in_payload, missing_here from v_reconcile_orders;

rollback;
