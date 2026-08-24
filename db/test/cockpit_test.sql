-- =====================================================================
-- Trading-Card-Engine · Cockpit-Test
-- Prueft den Not-Aus und die Kennzahlen-Sichten. Baut sich seine Daten
-- selbst auf, damit er auf einer frischen Datenbank laeuft.
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
  raise notice '  verriegelt: % (%)', p_label, left(v_msg, 70);
end $$;

-- ------------------------------------------------------------ eigener Aufbau
select register_partner('OPS', 'Testpartner', 'https://t.example/u?p={external_ref}',
                        array['1.0'], 'test') as partner \gset

insert into club (partner_id, external_ref, name)
values (:'partner', 'C-OPS', 'SV Testheim') returning id as club \gset
insert into team (club_id, external_ref, name, season)
values (:'club', 'T-OPS', 'A-Jugend', '25/26') returning id as team \gset
insert into person (partner_id, external_ref, team_id, display_name, role, is_minor)
values (:'partner', 'P-OPS', :'team', 'Ops Tester', 'FIELD', false) returning id as person \gset
insert into consent_assertion (person_id, partner_consent_id, text_version, subject_type,
                               granted_at, assertion_hash)
values (:'person', 'EW-OPS', 'v1', 'SELF', now(), repeat('1',64));

insert into team_order (partner_id, team_id, external_ref, snapshot, snapshot_hash, accepted_at)
values (:'partner', :'team', 'OPS-1', '{}'::jsonb, repeat('2',64), now())
returning id as ord \gset

insert into order_line (team_order_id, person_id, design_version_id, quantity, recipient_group_key)
select :'ord', :'person', dv.id, 1, 'P-OPS' from design_version dv
 where dv.family_id = 'DESIGN-1' limit 1
returning id as line \gset

select expand_order_line(:'line');
select ci.id as card, tw.public_token as token
  from card_item ci join card_twin tw on tw.id = ci.card_twin_id
 where ci.order_line_id = :'line' \gset
select dv.id as design, dv.print_spec_id as spec from design_version dv
 where dv.family_id = 'DESIGN-1' limit 1 \gset

insert into render_artifact (fingerprint, front_fingerprint, design_version_id,
                             engine_version, pdf_ref, manifest)
values (repeat('9',64), repeat('8',64), :'design', 'test', 's3://t.pdf', '{}'::jsonb);
insert into qa_verdict (fingerprint, decision, qr_token_decoded)
values (repeat('9',64), 'PASS', :'token');
update card_item set artifact_fingerprint = repeat('9',64) where id = :'card';

insert into print_batch (print_spec_id, manifest_hash, consent_revalidated_at)
values (:'spec', repeat('7',64), now()) returning id as batch \gset

update card_item set state = 'DATA_VALIDATED' where id = :'card';
update card_item set state = 'PHOTO_ACCEPTED' where id = :'card';
update card_item set state = 'ASSET_READY'    where id = :'card';
update card_item set state = 'RENDER_QUEUED'  where id = :'card';
update card_item set state = 'RENDERED'       where id = :'card';
update card_item set state = 'QA_PASSED'      where id = :'card';
update card_item set state = 'APPROVED'       where id = :'card';
update card_item set state = 'BATCHED', print_batch_id = :'batch' where id = :'card';

-- ------------------------------------------------------------ Not-Aus
select set_config_value('ops.transfers_paused', 'true', 'test');
select transfers_paused() as notaus_aktiv;
select must_fail(format('update print_batch set transferred_at = now() where id = %L', :'batch'),
                 'Transfer bei aktivem Not-Aus');

select set_config_value('ops.transfers_paused', 'false', 'test');
update print_batch set transferred_at = now() where id = :'batch';
select state as transfer_nach_freigabe from print_batch where id = :'batch';

select must_fail($$ select set_config_value('gibt.es.nicht', 'x', 'test') $$,
                 'unbekannter Konfigurationsschlüssel');

select count(*) as konfigurationsaenderungen_protokolliert
  from domain_event where event_type = 'config.changed';

-- Die Veroeffentlichung der digitalen Karte haengt am Druck.
update card_item set state = 'SENT_TO_PRINT' where id = :'card';
select published_at is null as vor_dem_druck_nicht_abrufbar from card_twin where id = (
  select card_twin_id from card_item where id = :'card');
update card_item set state = 'PRINTED' where id = :'card';
select published_at is not null as nach_dem_druck_abrufbar,
       published_fingerprint = repeat('9',64) as zeigt_auf_das_gedruckte
  from card_twin where id = (select card_twin_id from card_item where id = :'card');

-- ------------------------------------------------------------ Kennzahlen
select count(*) as kachelzeilen from v_cockpit_tiles;
select count(*) as trendtage from v_cockpit_photo_trend;
select auto_pass_rate_pct is not null as auto_pass_vorhanden,
       blockers_hard >= 0 as blocker_gezaehlt,
       transfers_paused = false as notaus_aus,
       cards_open >= 0 as karten_gezaehlt
  from v_cockpit_tiles;
select count(*) >= 1 as board_liefert_zeilen from v_team_board where team_order_id = :'ord';
select quantity is not null as board_kennt_die_menge from v_team_board where team_order_id = :'ord' limit 1;

rollback;
