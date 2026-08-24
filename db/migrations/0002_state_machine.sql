-- =====================================================================
-- Trading-Card-Engine · 0002 · Zustandsautomat und Verriegelungen
--
-- Alles hier ist DB-seitig erzwungen, nicht nur in der Anwendungsschicht.
-- Wenn in zwei Jahren jemand ein Bulk-Update schreibt, haelt die Datenbank.
-- =====================================================================

-- ------------------------------------------------- erlaubte Uebergaenge
-- Der Zustandsautomat ist Daten, nicht Code: nachlesbar, testbar, aenderbar.
create table card_item_transition (
  from_state card_item_state not null,
  to_state   card_item_state not null,
  note       text,
  primary key (from_state, to_state)
);

insert into card_item_transition (from_state, to_state, note) values
  ('DRAFT','DATA_VALIDATED',        'Stammdaten vollstaendig'),
  ('DATA_VALIDATED','PHOTO_ACCEPTED','Foto Klasse A oder B'),
  ('PHOTO_ACCEPTED','ASSET_READY',  'Freistellung erfolgreich'),
  ('ASSET_READY','RENDER_QUEUED',   null),
  ('RENDER_QUEUED','RENDERED',      null),
  ('RENDERED','QA_PASSED',          'alle Gates bestanden'),
  ('RENDERED','QA_FAILED',          null),
  ('QA_FAILED','RENDER_QUEUED',     'Neu-Rendering nach Review'),
  ('QA_FAILED','QA_PASSED',         'manuelle Freigabe in der Quarantaene'),
  ('QA_PASSED','APPROVED',          null),
  ('APPROVED','BATCHED',            'VERRIEGELT - siehe card_item_guard()'),
  ('BATCHED','SENT_TO_PRINT',       null),
  ('BATCHED','APPROVED',            'Batch aufgeloest, Karte zurueck in den Pool'),
  ('SENT_TO_PRINT','PRINTED',       null),
  ('PRINTED','PACKED',              null),
  ('PACKED','SHIPPED',              null),
  ('SHIPPED','DELIVERED',           null),
  ('DELIVERED','REPRINT_REQUESTED', 'Reklamation'),
  ('REPRINT_REQUESTED','RENDER_QUEUED', null);

-- Blockieren ist aus jedem Zustand vor dem Transfer moeglich, Entblocken
-- fuehrt an die Austrittsstelle zurueck.
insert into card_item_transition (from_state, to_state, note)
select s, 'BLOCKED', 'Blocker aufgetreten'
from unnest(enum_range(null::card_item_state)) s
where s not in ('BLOCKED','CANCELLED','SENT_TO_PRINT','PRINTED','PACKED','SHIPPED','DELIVERED');

insert into card_item_transition (from_state, to_state, note)
select 'BLOCKED', s, 'Blocker geloest, Rueckkehr an die Austrittsstelle'
from unnest(enum_range(null::card_item_state)) s
where s not in ('BLOCKED','CANCELLED');

-- Stornieren ist bis zum Transfer moeglich. Danach ist Papier im Spiel.
insert into card_item_transition (from_state, to_state, note)
select s, 'CANCELLED', 'Storno vor dem Transfer'
from unnest(enum_range(null::card_item_state)) s
where s not in ('CANCELLED','SENT_TO_PRINT','PRINTED','PACKED','SHIPPED','DELIVERED');

-- ------------------------------------------------- Token-Erzeugung

-- 22 Zeichen Base58 aus kryptografisch zufaelligen Bytes (~128 Bit).
-- Bewusst NICHT aus IDs abgeleitet und nicht aufzaehlbar - der Token steht
-- auf einer Karte, die verloren gehen kann.
create or replace function gen_twin_token() returns text
language plpgsql volatile as $$
declare
  alphabet constant text := '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  b bytea := gen_random_bytes(22);
  out text := '';
  i int;
begin
  for i in 1..22 loop
    out := out || substr(alphabet, 1 + (get_byte(b, i-1) % 58), 1);
  end loop;
  return out;
end $$;

-- ------------------------------------------------- Twin-Vergabe beim Anlegen

-- Der Token muss VOR dem ersten Rendering feststehen, sonst kann er nicht
-- in das Artefakt eingebettet werden.
create or replace function card_item_mint_twin() returns trigger
language plpgsql as $$
declare
  v_token_per_copy boolean;
  v_quantity       int;
  v_scope_copy     int;
  v_twin           uuid;
begin
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

  select id into v_twin
    from card_twin
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

create trigger card_item_mint_twin_trg
  before insert on card_item
  for each row execute function card_item_mint_twin();

-- ------------------------------------------------- Die zentrale Verriegelung

create or replace function card_item_guard() returns trigger
language plpgsql as $$
declare
  v_person       uuid;
  v_batch_spec   text;
  v_design_spec  text;
begin
  if new.state is distinct from old.state then

    if not exists (select 1 from card_item_transition t
                    where t.from_state = old.state and t.to_state = new.state) then
      raise exception 'card_item %: unzulaessiger Zustandsuebergang % -> %',
        new.id, old.state, new.state using errcode = 'check_violation';
    end if;

    if new.state = 'BLOCKED' and old.state <> 'BLOCKED' then
      new.state_before_block := old.state;
    end if;

    -- ---- APPROVED -> BATCHED: ab hier wird Papier verbraucht ----
    if new.state = 'BATCHED' then

      if new.artifact_fingerprint is null then
        raise exception 'card_item %: BATCHED ohne Artefakt', new.id
          using errcode = 'check_violation';
      end if;

      if new.print_batch_id is null then
        raise exception 'card_item %: BATCHED ohne print_batch_id', new.id
          using errcode = 'check_violation';
      end if;

      -- 1. bestandene QA, und zwar fuer GENAU dieses Artefakt
      if not exists (select 1 from qa_verdict q
                      where q.fingerprint = new.artifact_fingerprint
                        and q.decision = 'PASS') then
        raise exception 'card_item %: keine bestandene QA fuer fingerprint %',
          new.id, new.artifact_fingerprint using errcode = 'check_violation';
      end if;

      -- 2. der aus dem PDF zurueckgelesene QR-Token gehoert zu diesem Twin
      if not exists (select 1
                       from qa_verdict q
                       join card_twin  tw on tw.id = new.card_twin_id
                      where q.fingerprint = new.artifact_fingerprint
                        and q.qr_token_decoded = tw.public_token) then
        raise exception 'card_item %: gedruckter QR-Token stimmt nicht mit dem Twin ueberein',
          new.id using errcode = 'check_violation';
      end if;

      -- 3. kein offener HARD-Blocker
      if exists (select 1 from blocker b
                  where b.card_item_id = new.id
                    and b.resolved_at is null
                    and b.severity = 'HARD') then
        raise exception 'card_item %: offener HARD-Blocker', new.id
          using errcode = 'check_violation';
      end if;

      -- 4. gueltige Einwilligungs-Assertion
      select ol.person_id into v_person from order_line ol where ol.id = new.order_line_id;
      if not exists (select 1 from consent_assertion c
                      where c.person_id = v_person and c.revoked_at is null) then
        raise exception 'card_item %: keine gueltige Einwilligungs-Assertion', new.id
          using errcode = 'check_violation';
      end if;

      -- 5. Twin nicht widerrufen
      if exists (select 1 from card_twin tw
                  where tw.id = new.card_twin_id and tw.revoked_at is not null) then
        raise exception 'card_item %: die digitale Karte ist widerrufen', new.id
          using errcode = 'check_violation';
      end if;

      -- 6. Batch und Design muessen dieselbe Druckspezifikation haben.
      --    Gold-Folie darf nicht auf den Standardbogen.
      select pb.print_spec_id into v_batch_spec from print_batch pb where pb.id = new.print_batch_id;
      select dv.print_spec_id into v_design_spec
        from order_line ol join design_version dv on dv.id = ol.design_version_id
       where ol.id = new.order_line_id;
      if v_batch_spec is distinct from v_design_spec then
        raise exception 'card_item %: Druckspezifikation passt nicht (Batch %, Design %)',
          new.id, v_batch_spec, v_design_spec using errcode = 'check_violation';
      end if;
    end if;
  end if;

  new.updated_at := now();
  return new;
end $$;

create trigger card_item_guard_trg
  before update on card_item
  for each row execute function card_item_guard();

-- ------------------------------------------------- Transfer an die Druckerei

create or replace function print_batch_guard() returns trigger
language plpgsql as $$
declare
  v_open int;
  v_total int;
  v_max_age interval;
begin
  if new.transferred_at is not null and old.transferred_at is null then

    if new.manifest_hash is null then
      raise exception 'print_batch %: Transfer ohne Manifest-Hash', new.id
        using errcode = 'check_violation';
    end if;

    -- Revalidierung der Einwilligung unmittelbar vor dem Transfer.
    -- Das Sicherheitsnetz fuer den Fall, dass der Widerrufs-Webhook ausfaellt.
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

create trigger print_batch_guard_trg
  before update on print_batch
  for each row execute function print_batch_guard();

-- ------------------------------------------------- Blocker: Schwere aus dem Katalog

create or replace function blocker_apply_catalog() returns trigger
language plpgsql as $$
declare
  v_sev   blocker_severity;
  v_owner blocker_owner;
begin
  select severity, default_owner into v_sev, v_owner
    from blocker_catalog where reason = new.reason;
  if v_sev is null then
    raise exception 'blocker: Grund % steht nicht im Katalog', new.reason;
  end if;
  -- Die Schwere kann NICHT ueberschrieben werden. Sonst legt irgendwann
  -- jemand einen SOFT-Blocker fuer eine fehlende Einwilligung an.
  new.severity := v_sev;
  new.owner    := coalesce(new.owner, v_owner);
  return new;
end $$;

create trigger blocker_apply_catalog_trg
  before insert on blocker
  for each row execute function blocker_apply_catalog();

-- ------------------------------------------------- Unveraenderlichkeit

create or replace function forbid_mutation() returns trigger
language plpgsql as $$
begin
  raise exception '% ist append-only', tg_table_name using errcode = 'check_violation';
end $$;

create trigger domain_event_immutable
  before update or delete on domain_event
  for each row execute function forbid_mutation();

create trigger partner_payload_immutable
  before update or delete on partner_payload
  for each row execute function forbid_mutation();

-- Die Assertion ist eingefroren. Nur Widerruf und Revalidierung sind erlaubt,
-- und ein Widerruf laesst sich nicht zurueckdrehen.
create or replace function consent_assertion_guard() returns trigger
language plpgsql as $$
begin
  if (new.person_id, new.partner_consent_id, new.text_version,
      new.subject_type, new.granted_at, new.assertion_hash)
     is distinct from
     (old.person_id, old.partner_consent_id, old.text_version,
      old.subject_type, old.granted_at, old.assertion_hash) then
    raise exception 'consent_assertion ist eingefroren; nur revoked_at und last_revalidated_at sind aenderbar'
      using errcode = 'check_violation';
  end if;
  if old.revoked_at is not null and new.revoked_at is null then
    raise exception 'ein Widerruf kann nicht zurueckgenommen werden'
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

create trigger consent_assertion_guard_trg
  before update on consent_assertion
  for each row execute function consent_assertion_guard();

-- Ein veroeffentlichtes Template wird nie geaendert, nur neu versioniert.
create or replace function design_version_guard() returns trigger
language plpgsql as $$
begin
  if old.published_at is not null
     and (new.slot_schema_id, new.print_spec_id, new.assets, new.version)
         is distinct from
         (old.slot_schema_id, old.print_spec_id, old.assets, old.version) then
    raise exception 'design_version %: veroeffentlichte Versionen sind unveraenderlich', old.id
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

create trigger design_version_guard_trg
  before update on design_version
  for each row execute function design_version_guard();

-- ------------------------------------------------- Hilfsfunktionen

-- Expandiert eine Bestellzeile in ihre physischen Karten.
-- Menge lebt auf der Zeile, Zustand lebt auf dem Item.
create or replace function expand_order_line(p_line uuid) returns int
language plpgsql as $$
declare v_created int;
begin
  insert into card_item (order_line_id, copy_index)
  select p_line, g
    from generate_series(1, (select quantity from order_line where id = p_line)) g
  on conflict (order_line_id, copy_index) do nothing;
  get diagnostics v_created = row_count;
  return v_created;
end $$;

-- Widerruf: die gedruckte Karte erreichen wir nicht mehr, alles andere schon.
create or replace function revoke_card_twin(p_token text, p_actor text default 'SYSTEM')
returns void language plpgsql as $$
declare v_twin uuid; v_corr uuid;
begin
  select id into v_twin from card_twin where public_token = p_token;
  if v_twin is null then
    raise exception 'card_twin %: unbekannter Token', p_token;
  end if;

  update card_twin set revoked_at = now() where id = v_twin and revoked_at is null;

  -- Noch nicht gedruckte Karten werden storniert.
  update card_item
     set state = 'CANCELLED'
   where card_twin_id = v_twin
     and state not in ('SENT_TO_PRINT','PRINTED','PACKED','SHIPPED','DELIVERED','CANCELLED');

  select o.correlation_id into v_corr
    from card_twin tw
    join order_line ol on ol.id = tw.order_line_id
    join team_order o  on o.id = ol.team_order_id
   where tw.id = v_twin;

  insert into domain_event (correlation_id, subject_type, subject_id, event_type, payload, actor)
  values (v_corr, 'card_twin', v_twin, 'twin.revoked',
          jsonb_build_object('token', p_token), p_actor);
end $$;
