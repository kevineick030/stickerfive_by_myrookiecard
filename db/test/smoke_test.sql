-- =====================================================================
-- Trading-Card-Engine · Smoke-Test
-- Prueft, dass die Verriegelungen wirklich halten. Laeuft in einer
-- Transaktion und wird am Ende zurueckgerollt.
--   psql -f db/test/smoke_test.sql
-- =====================================================================
\set ON_ERROR_STOP on
begin;

create or replace function must_fail(p_sql text, p_label text) returns void
language plpgsql as $$
declare v_failed boolean := false; v_msg text;
begin
  begin
    execute p_sql;
  exception when others then
    v_failed := true; v_msg := sqlerrm;
  end;
  if not v_failed then
    raise exception 'TEST FEHLGESCHLAGEN: "%" haette abgelehnt werden muessen', p_label;
  end if;
  raise notice '  verriegelt: % (%)', p_label, left(v_msg, 78);
end $$;

-- ------------------------------------------------------------ Stammdaten
insert into partner (id, code, name, deeplink_template) values
  ('11111111-1111-1111-1111-111111111111','SK','Sticker-König',
   'https://partner.example/upload?player={external_ref}');

insert into club (id, partner_id, external_ref, name) values
  ('22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111','C-1','TSV Musterstadt');

insert into team (id, club_id, external_ref, name, season, sport, age_group) values
  ('33333333-3333-3333-3333-333333333333','22222222-2222-2222-2222-222222222222','T-1','D-Jugend','25/26','Fussball','D');

insert into person (id, partner_id, external_ref, team_id, display_name, role, jersey_number, is_minor, guardian_contact_email) values
  ('44444444-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','P-1','33333333-3333-3333-3333-333333333333','Lukas Meier','FIELD','7',  true,'eltern.meier@example.org'),
  ('44444444-0000-0000-0000-000000000002','11111111-1111-1111-1111-111111111111','P-2','33333333-3333-3333-3333-333333333333','Tim Klein',  'KEEPER','1', true,'eltern.klein@example.org'),
  ('44444444-0000-0000-0000-000000000003','11111111-1111-1111-1111-111111111111','P-3','33333333-3333-3333-3333-333333333333','Đorđe Đorđević','COACH',null,false,null);

insert into consent_assertion (person_id, partner_consent_id, text_version, subject_type, granted_at, assertion_hash)
select id, 'SK-C-'||external_ref, 'einwilligung-2026-03', case when is_minor then 'GUARDIAN' else 'SELF' end,
       now() - interval '5 days', md5(external_ref)||md5(external_ref)
from person;

-- Trainer hat keine Kontaktangabe und ist volljaehrig -> erlaubt.
-- Ein Minderjaehriger ohne jede Kontaktangabe darf NICHT angelegt werden:
select must_fail($$
  insert into person (partner_id, external_ref, display_name, is_minor)
  values ('11111111-1111-1111-1111-111111111111','P-X','Ohne Kontakt', true)
$$, 'Minderjaehriger ohne erreichbaren Kontakt');

select must_fail($$
  update partner set deeplink_template = 'https://partner.example/login'
   where code = 'SK'
$$, 'Deep-Link ohne Spielerbezug');

-- ------------------------------------------------------------ Auftrag
insert into team_order (id, partner_id, team_id, external_ref, snapshot, snapshot_hash, accepted_at, promised_delivery_at)
values ('55555555-5555-5555-5555-555555555555','11111111-1111-1111-1111-111111111111',
        '33333333-3333-3333-3333-333333333333','SK-ORDER-1',
        '{"frozen":true}'::jsonb, repeat('f',64), now(), now() + interval '15 days');

select must_fail($$
  insert into team_order (partner_id, team_id, external_ref, accepted_at)
  values ('11111111-1111-1111-1111-111111111111','33333333-3333-3333-3333-333333333333','SK-ORDER-2', now())
$$, 'Auftragsannahme ohne eingefrorenen Snapshot');

-- Zeilen: Meier will 3 Karten, Torwart und Trainer je eine (anderes Design).
insert into order_line (id, team_order_id, person_id, design_version_id, quantity, line_type, recipient_group_key, design_resolved_by)
select '66666666-0000-0000-0000-000000000001','55555555-5555-5555-5555-555555555555',
       '44444444-0000-0000-0000-000000000001', dv.id, 3, 'BASE_PACK','meier','RULE'
  from design_version dv where dv.family_id = 'DESIGN-1';
insert into order_line (id, team_order_id, person_id, design_version_id, quantity, line_type, recipient_group_key, design_resolved_by)
select '66666666-0000-0000-0000-000000000002','55555555-5555-5555-5555-555555555555',
       '44444444-0000-0000-0000-000000000002', dv.id, 1, 'BASE_PACK','klein','RULE'
  from design_version dv where dv.family_id = 'DESIGN-2';
insert into order_line (id, team_order_id, person_id, design_version_id, quantity, line_type, recipient_group_key, design_resolved_by)
select '66666666-0000-0000-0000-000000000003','55555555-5555-5555-5555-555555555555',
       '44444444-0000-0000-0000-000000000003', dv.id, 1, 'BASE_PACK','roth','RULE'
  from design_version dv where dv.family_id = 'DESIGN-3';

select expand_order_line('66666666-0000-0000-0000-000000000001') as meier_karten,
       expand_order_line('66666666-0000-0000-0000-000000000002') as klein_karten,
       expand_order_line('66666666-0000-0000-0000-000000000003') as roth_karten;

select must_fail($$
  insert into card_item (order_line_id, copy_index)
  values ('66666666-0000-0000-0000-000000000002', 2)
$$, 'copy_index ueber der bestellten Menge');

-- Kernbehauptung bei token_per_copy = true:
-- drei Kopien -> drei eigene Token, also drei Artefakte.
select count(*) as meier_items, count(distinct card_twin_id) as meier_token
  from card_item where order_line_id = '66666666-0000-0000-0000-000000000001';

-- ------------------------------------------------------------ Rendering + QA
-- Je Kopie ein Artefakt, aber alle mit derselben Vorderseite: nur die
-- Rueckseite unterscheidet sich (anderer QR-Token).
insert into render_artifact (fingerprint, front_fingerprint, design_version_id, engine_version, pdf_ref, manifest)
select md5('front-a'||ci.id::text) || md5('back-a'||ci.id::text),
       repeat('a',64), dv.id, 'renderer-1.0.0', 's3://art/'||ci.id||'.pdf', '{"slots":{}}'::jsonb
  from card_item ci
  join order_line     ol on ol.id = ci.order_line_id
  join design_version dv on dv.id = ol.design_version_id
 where ci.order_line_id = '66666666-0000-0000-0000-000000000001';

update card_item ci
   set artifact_fingerprint = md5('front-a'||ci.id::text) || md5('back-a'||ci.id::text)
 where ci.order_line_id = '66666666-0000-0000-0000-000000000001';

-- Die teure Vorderseite wird genau einmal gerendert.
select count(*) as meier_artefakte, count(distinct ra.front_fingerprint) as gemeinsame_vorderseiten
  from card_item ci join render_artifact ra on ra.fingerprint = ci.artifact_fingerprint
 where ci.order_line_id = '66666666-0000-0000-0000-000000000001';

-- Zustandsautomat: Spruenge sind nicht erlaubt.
select must_fail($$
  update card_item set state = 'APPROVED'
   where order_line_id = '66666666-0000-0000-0000-000000000001' and copy_index = 1
$$, 'Sprung DRAFT -> APPROVED');

do $$
declare s text;
begin
  foreach s in array array['DATA_VALIDATED','PHOTO_ACCEPTED','ASSET_READY','RENDER_QUEUED','RENDERED','QA_PASSED','APPROVED'] loop
    update card_item set state = s::card_item_state
     where order_line_id = '66666666-0000-0000-0000-000000000001';
  end loop;
end $$;

insert into print_batch (id, print_spec_id, manifest_hash) values
  ('77777777-0000-0000-0000-00000000000a','PS-STD',  repeat('b',64)),
  ('77777777-0000-0000-0000-00000000000b','PS-GOLD', repeat('c',64));

-- Ohne QA-Verdikt kommt nichts in den Druck.
select must_fail($$
  update card_item set state = 'BATCHED', print_batch_id = '77777777-0000-0000-0000-00000000000a'
   where order_line_id = '66666666-0000-0000-0000-000000000001' and copy_index = 1
$$, 'BATCHED ohne bestandene QA');

-- Verdikte mit FALSCHEM zurueckgelesenem QR-Token.
insert into qa_verdict (fingerprint, decision, confidence, qr_token_decoded)
select ci.artifact_fingerprint, 'PASS', 0.991, 'FalscherToken1234567xy'
  from card_item ci where ci.order_line_id = '66666666-0000-0000-0000-000000000001';

select must_fail($$
  update card_item set state = 'BATCHED', print_batch_id = '77777777-0000-0000-0000-00000000000a'
   where order_line_id = '66666666-0000-0000-0000-000000000001' and copy_index = 1
$$, 'gedruckter QR-Token passt nicht zum Twin');

-- Korrekte Token aus Gate 3d - je Kopie der ihre.
update qa_verdict q set qr_token_decoded = tw.public_token
  from card_item ci join card_twin tw on tw.id = ci.card_twin_id
 where q.fingerprint = ci.artifact_fingerprint
   and ci.order_line_id = '66666666-0000-0000-0000-000000000001';

-- Offener HARD-Blocker haelt die Karte auf.
insert into blocker (card_item_id, reason, detail)
select id, 'CONSENT_REVOKED', 'Testfall'
  from card_item where order_line_id = '66666666-0000-0000-0000-000000000001' and copy_index = 1;

select must_fail($$
  update card_item set state = 'BATCHED', print_batch_id = '77777777-0000-0000-0000-00000000000a'
   where order_line_id = '66666666-0000-0000-0000-000000000001' and copy_index = 1
$$, 'offener HARD-Blocker');

-- Die Schwere kommt aus dem Katalog und laesst sich nicht herunterstufen.
select severity as consent_blocker_severity from blocker
 where reason = 'CONSENT_REVOKED' and resolved_at is null limit 1;

update blocker set resolved_at = now() where reason = 'CONSENT_REVOKED';

-- Goldkarte darf nicht auf den Standardbogen.
insert into render_artifact (fingerprint, front_fingerprint, design_version_id, engine_version, pdf_ref, manifest)
select repeat('d',64), repeat('e',64), dv.id, 'renderer-1.0.0', 's3://art/d.pdf', '{}'::jsonb
  from design_version dv where dv.family_id = 'DESIGN-3';
update card_item set artifact_fingerprint = repeat('d',64)
 where order_line_id = '66666666-0000-0000-0000-000000000003';
insert into qa_verdict (fingerprint, decision, qr_token_decoded)
select repeat('d',64), 'PASS', tw.public_token
  from card_item ci join card_twin tw on tw.id = ci.card_twin_id
 where ci.order_line_id = '66666666-0000-0000-0000-000000000003';
do $$
declare s text;
begin
  foreach s in array array['DATA_VALIDATED','PHOTO_ACCEPTED','ASSET_READY','RENDER_QUEUED','RENDERED','QA_PASSED','APPROVED'] loop
    update card_item set state = s::card_item_state where order_line_id = '66666666-0000-0000-0000-000000000003';
  end loop;
end $$;

select must_fail($$
  update card_item set state = 'BATCHED', print_batch_id = '77777777-0000-0000-0000-00000000000a'
   where order_line_id = '66666666-0000-0000-0000-000000000003'
$$, 'Goldveredelung im Standardbogen');

-- Jetzt der Happy Path.
update card_item set state = 'BATCHED', print_batch_id = '77777777-0000-0000-0000-00000000000a'
 where order_line_id = '66666666-0000-0000-0000-000000000001';
update card_item set state = 'BATCHED', print_batch_id = '77777777-0000-0000-0000-00000000000b'
 where order_line_id = '66666666-0000-0000-0000-000000000003';

-- ------------------------------------------------------------ Transfer
select must_fail($$
  update print_batch set transferred_at = now() where id = '77777777-0000-0000-0000-00000000000a'
$$, 'Transfer ohne frische Revalidierung der Einwilligungen');

update print_batch set consent_revalidated_at = now() - interval '4 hours'
 where id = '77777777-0000-0000-0000-00000000000a';
select must_fail($$
  update print_batch set transferred_at = now() where id = '77777777-0000-0000-0000-00000000000a'
$$, 'Revalidierung ist zu alt');

-- Ein nicht freigegebenes Item im Batch blockiert den ganzen Transfer.
update print_batch set consent_revalidated_at = now() where id = '77777777-0000-0000-0000-00000000000a';
update card_item set print_batch_id = '77777777-0000-0000-0000-00000000000a'
 where order_line_id = '66666666-0000-0000-0000-000000000002';
select must_fail($$
  update print_batch set transferred_at = now() where id = '77777777-0000-0000-0000-00000000000a'
$$, 'Batch enthaelt eine nicht freigegebene Karte');
update card_item set print_batch_id = null where order_line_id = '66666666-0000-0000-0000-000000000002';

update print_batch set transferred_at = now() where id = '77777777-0000-0000-0000-00000000000a';
select id, state as batch_state_after_transfer from print_batch where id = '77777777-0000-0000-0000-00000000000a';

-- ------------------------------------------------------------ Unveraenderlichkeit
insert into domain_event (correlation_id, subject_type, event_type)
values (gen_random_uuid(), 'test', 'test.created');
select must_fail($$ update domain_event set event_type = 'geaendert' $$, 'domain_event ist append-only');
select must_fail($$ delete from domain_event $$,                        'domain_event laesst sich nicht loeschen');
select must_fail($$
  update consent_assertion set text_version = 'manipuliert'
   where person_id = '44444444-0000-0000-0000-000000000001'
$$, 'consent_assertion ist eingefroren');

update consent_assertion set revoked_at = now() where person_id = '44444444-0000-0000-0000-000000000002';
select must_fail($$
  update consent_assertion set revoked_at = null where person_id = '44444444-0000-0000-0000-000000000002'
$$, 'Widerruf laesst sich nicht zuruecknehmen');

-- ------------------------------------------------------------ Widerruf der digitalen Karte
select revoke_card_twin((select tw.public_token from card_twin tw
                          where tw.order_line_id = '66666666-0000-0000-0000-000000000002'));
select state as klein_state_nach_widerruf
  from card_item where order_line_id = '66666666-0000-0000-0000-000000000002';

-- ------------------------------------------------------------ Ergebnis
select items_total, items_cancelled, derived_status
  from v_team_order_production_status where team_order_id = '55555555-5555-5555-5555-555555555555';

select player_name, design_family, copy_index, state, board_status, qr_token
  from v_team_board where team_order_id = '55555555-5555-5555-5555-555555555555';

rollback;
