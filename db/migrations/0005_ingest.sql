-- =====================================================================
-- Trading-Card-Engine · 0005 · Aufnahme von Partnerdaten
--
-- Die Uebersetzung vom Fremdschema in unser Modell. Bewusst in der
-- Datenbank, weil sie in einer Transaktion laufen muss: entweder ist eine
-- Bestellung vollstaendig aufgenommen oder gar nicht.
--
-- Erwartet die NORMALISIERTE Form (siehe specs/partner_payload.v1.schema.json).
-- Das Uebersetzen der partnerspezifischen Rohform macht gateway/mapping.py -
-- so bleibt das Fremdschema ausserhalb des Kernmodells.
-- =====================================================================

-- Welches Design bekommt ein Spieler? Einmal bei Aufnahme aufgeloest und in
-- die Zeile geschrieben, nie lazy beim Rendern - sonst kann spaeter niemand
-- mehr erklaeren, warum diese Karte dieses Design hat.
create or replace function resolve_design_version(
  p_order uuid, p_role person_role, p_override text default null)
returns uuid language plpgsql stable as $$
declare v_id uuid;
begin
  if p_override is not null then
    select dv.id into v_id from design_version dv
     where dv.family_id = p_override order by dv.version desc limit 1;
    if v_id is null then
      raise exception 'Unbekannte Design-Familie "%" im Payload', p_override
        using errcode = 'check_violation';
    end if;
    return v_id;
  end if;

  select dr.design_version_id into v_id
    from design_rule dr where dr.team_order_id = p_order and dr.match_role = p_role;
  if v_id is not null then return v_id; end if;

  select dv.id into v_id
    from design_version dv join design_family df on df.id = dv.family_id
   where df.applies_to_role = p_role
   order by dv.version desc limit 1;
  if v_id is not null then return v_id; end if;

  select o.default_design_version_id into v_id from team_order o where o.id = p_order;
  if v_id is null then
    raise exception 'Kein Design fuer Rolle % und kein Vorgabewert am Auftrag', p_role
      using errcode = 'check_violation';
  end if;
  return v_id;
end $$;


create or replace function ingest_team_order(
  p_partner_code text,
  p_payload      jsonb,
  p_kind         text default 'WEBHOOK',
  p_correlation  uuid default null)
returns uuid language plpgsql as $$
declare
  v_partner    uuid;
  v_corr       uuid := coalesce(p_correlation, gen_random_uuid());
  v_version    text := p_payload ->> 'payload_version';
  v_order_json jsonb := p_payload -> 'order';
  v_ext_ref    text  := v_order_json ->> 'external_ref';
  v_raw_hash   char(64);
  v_club       uuid;
  v_team       uuid;
  v_contact    uuid;
  v_order      uuid;
  v_accepted   timestamptz;
  v_player     jsonb;
  v_person     uuid;
  v_asset      uuid;
  v_line       uuid;
  v_design     uuid;
  v_role       person_role;
  v_changes    int := 0;
  v_rows       int := 0;
  v_new_order  boolean := false;
begin
  select id into v_partner from partner where code = p_partner_code;
  if v_partner is null then
    raise exception 'Unbekannter Partner "%"', p_partner_code using errcode = 'check_violation';
  end if;
  if v_version is null or v_ext_ref is null then
    raise exception 'Payload ohne payload_version oder order.external_ref'
      using errcode = 'check_violation';
  end if;

  -- Unbekannte Vertragsversion: laut ablehnen statt still falsch mappen.
  perform assert_supported_version(v_partner, v_version);

  v_raw_hash := encode(sha256(p_payload::text::bytea), 'hex');

  -- Rohdaten-Archiv und Idempotenz in einem: derselbe Payload zweimal
  -- erzeugt keinen zweiten Auftrag.
  insert into partner_payload (partner_id, external_ref, payload_version, raw, raw_hash, correlation_id)
  values (v_partner, v_ext_ref, v_version, p_payload, v_raw_hash, v_corr)
  on conflict (partner_id, external_ref, payload_version, raw_hash) do nothing;

  -- ---------------------------------------------------------- Verein / Team
  insert into club (partner_id, external_ref, name)
  values (v_partner, v_order_json -> 'club' ->> 'external_ref', v_order_json -> 'club' ->> 'name')
  on conflict (partner_id, external_ref) do update set name = excluded.name
  returning id into v_club;

  insert into team (club_id, external_ref, name, season, sport, age_group)
  values (v_club,
          v_order_json -> 'team' ->> 'external_ref',
          v_order_json -> 'team' ->> 'name',
          v_order_json -> 'team' ->> 'season',
          v_order_json -> 'team' ->> 'sport',
          v_order_json -> 'team' ->> 'age_group')
  on conflict (club_id, external_ref, season) do update
    set name = excluded.name, sport = excluded.sport, age_group = excluded.age_group
  returning id into v_team;

  if v_order_json ? 'ordering_contact' then
    insert into ordering_contact (club_id, name, email, phone)
    values (v_club,
            v_order_json -> 'ordering_contact' ->> 'name',
            v_order_json -> 'ordering_contact' ->> 'email',
            v_order_json -> 'ordering_contact' ->> 'phone')
    returning id into v_contact;
  end if;

  -- ---------------------------------------------------------- Auftrag
  select id, accepted_at into v_order, v_accepted
    from team_order where partner_id = v_partner and external_ref = v_ext_ref;

  if v_order is null then
    insert into team_order (partner_id, team_id, ordering_contact_id, external_ref,
                            fulfillment_policy, shipment_policy, correlation_id)
    values (v_partner, v_team, v_contact, v_ext_ref,
            coalesce((v_order_json ->> 'fulfillment_policy')::fulfillment_policy, 'PARTIAL_WITH_HOLD'),
            coalesce((v_order_json ->> 'shipment_policy')::shipment_policy, 'CONSOLIDATE'),
            v_corr)
    returning id into v_order;
    v_new_order := true;
  end if;

  -- ---------------------------------------------------------- Spieler
  for v_player in select * from jsonb_array_elements(v_order_json -> 'players') loop
    v_role := coalesce((v_player ->> 'role')::person_role, 'FIELD');

    insert into person (partner_id, external_ref, team_id, display_name, first_name, last_name,
                        role, jersey_number, is_minor, contact_email,
                        guardian_name, guardian_contact_email)
    values (v_partner, v_player ->> 'external_ref', v_team,
            v_player ->> 'display_name', v_player ->> 'first_name', v_player ->> 'last_name',
            v_role, v_player ->> 'jersey_number',
            coalesce((v_player ->> 'is_minor')::boolean, false),
            v_player ->> 'contact_email',
            v_player ->> 'guardian_name', v_player ->> 'guardian_contact_email')
    on conflict (partner_id, external_ref) do update
      set team_id = excluded.team_id, role = excluded.role,
          jersey_number = excluded.jersey_number, is_minor = excluded.is_minor,
          contact_email = excluded.contact_email,
          guardian_name = excluded.guardian_name,
          guardian_contact_email = excluded.guardian_contact_email
    returning id into v_person;

    -- Ein bereits ANGENOMMENER Auftrag wird nicht mehr veraendert. Weicht der
    -- Name ab, entsteht ein Aenderungsantrag statt einer stillen Korrektur -
    -- sonst weicht das Gedruckte vom Freigegebenen ab.
    if v_accepted is not null then
      insert into partner_change_request (team_order_id, person_id, field, old_value, new_value, correlation_id)
      select v_order, v_person, 'display_name', p.display_name, v_player ->> 'display_name', v_corr
        from person p
       where p.id = v_person and p.display_name is distinct from (v_player ->> 'display_name')
      on conflict do nothing;
      get diagnostics v_rows = row_count;
      v_changes := v_changes + v_rows;
    else
      update person set display_name = v_player ->> 'display_name' where id = v_person;
    end if;

    -- Einwilligung: eingefrorene Aussage, nie ueberschrieben.
    if v_player ? 'consent' then
      insert into consent_assertion (person_id, partner_consent_id, text_version, subject_type,
                                     granted_at, evidence_ref, assertion_hash)
      values (v_person,
              v_player -> 'consent' ->> 'consent_id',
              v_player -> 'consent' ->> 'text_version',
              coalesce(v_player -> 'consent' ->> 'subject_type', 'SELF'),
              (v_player -> 'consent' ->> 'granted_at')::timestamptz,
              v_player -> 'consent' ->> 'evidence_ref',
              coalesce(v_player -> 'consent' ->> 'hash',
                       encode(sha256((v_player -> 'consent')::text::bytea), 'hex')))
      on conflict (person_id, partner_consent_id) do update
        set last_revalidated_at = now();
    end if;

    -- Foto. Jede neue Fassung ist ein eigenes Asset - das Original bleibt.
    if v_player ? 'photo' then
      insert into media_asset (partner_id, person_id, origin, content_hash, storage_ref,
                               mime_type, width_px, height_px, retention_class, delete_after)
      values (v_partner, v_person, 'PARTNER_API',
              v_player -> 'photo' ->> 'content_hash',
              v_player -> 'photo' ->> 'storage_ref',
              coalesce(v_player -> 'photo' ->> 'mime_type', 'image/jpeg'),
              (v_player -> 'photo' ->> 'width_px')::int,
              (v_player -> 'photo' ->> 'height_px')::int,
              'RAW_UPLOAD',
              now() + ((select value from system_config
                         where key = 'retention.raw_upload_days') || ' days')::interval)
      returning id into v_asset;
    end if;

    -- Zeilen und Karten nur, solange der Auftrag nicht angenommen ist.
    if v_accepted is null then
      v_design := resolve_design_version(v_order, v_role, v_player ->> 'design_family');

      insert into order_line (team_order_id, person_id, design_version_id, quantity,
                              line_type, recipient_group_key, design_resolved_by)
      values (v_order, v_person, v_design,
              coalesce((v_player ->> 'quantity')::int, 1),
              'BASE_PACK', v_player ->> 'external_ref',
              case when v_player ? 'design_family' then 'MANUAL' else 'RULE' end)
      on conflict (team_order_id, person_id, design_version_id, line_type) do update
        set quantity = excluded.quantity
      returning id into v_line;

      perform expand_order_line(v_line);

      if v_asset is not null then
        update card_item set source_asset_id = v_asset
         where order_line_id = v_line and source_asset_id is null;
      end if;
    end if;

    v_asset := null;
  end loop;

  insert into domain_event (correlation_id, subject_type, subject_id, event_type, payload, actor)
  values (v_corr, 'team_order', v_order,
          case when v_new_order then 'order.ingested' else 'order.refreshed' end,
          jsonb_build_object('external_ref', v_ext_ref,
                             'payload_version', v_version,
                             'raw_hash', v_raw_hash,
                             'players', jsonb_array_length(v_order_json -> 'players'),
                             'change_requests', v_changes,
                             'kind', p_kind),
          'partner-gateway');

  return v_order;
end $$;


-- Auftragsannahme: ab hier ist die Datenlage eingefroren.
create or replace function accept_team_order(p_order uuid, p_actor text default 'SYSTEM')
returns char(64) language plpgsql as $$
declare v_snapshot jsonb; v_hash char(64); v_corr uuid;
begin
  select correlation_id into v_corr from team_order where id = p_order;
  if v_corr is null then
    raise exception 'Unbekannter Auftrag %', p_order using errcode = 'check_violation';
  end if;
  if exists (select 1 from team_order where id = p_order and accepted_at is not null) then
    raise exception 'Auftrag % ist bereits angenommen', p_order using errcode = 'check_violation';
  end if;

  -- Der Snapshot ist UNSERE Sicht, nicht die Rohform des Partners: genau das,
  -- was in die Produktion geht.
  select jsonb_build_object(
           'order_id', p_order,
           'lines', coalesce(jsonb_agg(jsonb_build_object(
             'person_external_ref', p.external_ref,
             'display_name',        p.display_name,
             'role',                p.role,
             'jersey_number',       p.jersey_number,
             'design_version',      dv.family_id || '@' || dv.version,
             'quantity',            ol.quantity,
             'consent_version',     ca.text_version,
             'photo_hash',          (select ma.content_hash from card_item ci
                                      join media_asset ma on ma.id = ci.source_asset_id
                                     where ci.order_line_id = ol.id limit 1)
           ) order by p.external_ref), '[]'::jsonb))
    into v_snapshot
    from order_line ol
    join person p on p.id = ol.person_id
    join design_version dv on dv.id = ol.design_version_id
    left join consent_assertion ca on ca.person_id = p.id and ca.revoked_at is null
   where ol.team_order_id = p_order;

  v_hash := encode(sha256(v_snapshot::text::bytea), 'hex');

  update team_order
     set snapshot = v_snapshot, snapshot_hash = v_hash,
         accepted_at = now(), lifecycle_state = 'ACCEPTED',
         hold_until = now() + ((select value from system_config
                                 where key = 'order.hold_until_days') || ' days')::interval,
         promised_delivery_at = now() + ((select value from system_config
                                 where key = 'order.promised_lead_time_days') || ' days')::interval
   where id = p_order;

  insert into domain_event (correlation_id, subject_type, subject_id, event_type, payload, actor)
  values (v_corr, 'team_order', p_order, 'order.accepted',
          jsonb_build_object('snapshot_hash', v_hash,
                             'lines', jsonb_array_length(v_snapshot -> 'lines')), p_actor);
  return v_hash;
end $$;
