-- =====================================================================
-- Trading-Card-Engine · 0001 · Kernschema
-- PostgreSQL 14+ (getestet auf 16). Laeuft unveraendert auf Supabase.
--
-- Leitprinzipien (siehe docs/architecture/trading-card-engine.md):
--   * order_line traegt die MENGE, card_item traegt den ZUSTAND
--   * render_artifact ist content-addressed -> drei Kopien teilen ein Rendering
--   * card_twin.public_token ist stabil und wird gedruckt;
--     render_artifact.fingerprint aendert sich bei jeder Korrektur
--   * consent_assertion ist eingefroren; die Einwilligung selbst liegt beim Partner
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- enums

create type card_item_state as enum (
  'DRAFT','DATA_VALIDATED','PHOTO_ACCEPTED','ASSET_READY','RENDER_QUEUED',
  'RENDERED','QA_PASSED','QA_FAILED','APPROVED','BATCHED','SENT_TO_PRINT',
  'PRINTED','PACKED','SHIPPED','DELIVERED',
  'BLOCKED','CANCELLED','REPRINT_REQUESTED'
);

-- Nur der kommandierte Lebenszyklus. Der Produktionsstatus wird ABGELEITET,
-- siehe view v_team_order_production_status in 0003_views.sql.
create type team_order_lifecycle as enum (
  'RECEIVED','VALIDATING','ACCEPTED','ON_HOLD','CLOSED','CANCELLED'
);

create type fulfillment_policy   as enum ('ALL_OR_NOTHING','PARTIAL_WITH_HOLD','PARTIAL_SHIP_IMMEDIATELY');
create type shipment_policy      as enum ('CONSOLIDATE','SHIP_PER_WAVE');
create type line_type            as enum ('BASE_PACK','EXTRA_COPY','UPGRADE');
create type person_role          as enum ('FIELD','KEEPER','COACH','STAFF');
create type quality_class        as enum ('A','B','C');
create type retention_class      as enum ('RAW_UPLOAD','CUTOUT_DERIVATIVE','PRINT_ARTIFACT','DIGITAL_TWIN');
create type asset_origin         as enum ('PARTNER_API','DERIVED','INTERNAL');
create type blocker_severity     as enum ('HARD','SOFT');
create type blocker_owner        as enum ('PARTNER','CLUB','CUSTOMER','INTERNAL');
create type qa_decision          as enum ('PASS','FAIL','REVIEW');
create type print_batch_state    as enum ('OPEN','SEALED','TRANSFERRED','ACKNOWLEDGED','PRINTED','CANCELLED');
create type message_channel      as enum ('EMAIL','SMS');
create type delivery_status      as enum ('QUEUED','SENT','DELIVERED','BOUNCED','FAILED');
create type image_fit_mode       as enum ('ANCHOR','COVER');

create type blocker_reason as enum (
  -- HARD: rechtlich, niemals umgehbar
  'CONSENT_MISSING','CONSENT_REVOKED','GUARDIAN_CONSENT_MISSING','CONSENT_REVALIDATION_FAILED',
  -- SOFT: behebbar
  'PHOTO_MISSING','PHOTO_REJECTED','CUTOUT_FAILED','QA_FAILED',
  'MASTERDATA_INCOMPLETE','CONTACT_UNREACHABLE'
);

-- ------------------------------------------------------- Mandant / Partner

create table partner (
  id                uuid primary key default gen_random_uuid(),
  code              text        not null unique,
  name              text        not null,
  api_config        jsonb       not null default '{}'::jsonb,
  -- Vertragsgegenstand: spielerscharfer Deep-Link in die Upload-Maske.
  -- Ohne {external_ref} landet der Kunde auf einer Startseite -> Abbruch.
  deeplink_template text,
  created_at        timestamptz not null default now(),
  constraint deeplink_addresses_one_player
    check (deeplink_template is null or deeplink_template like '%{external_ref}%')
);

-- Rohdaten-Archiv + Idempotenzschluessel des Anti-Corruption Layers.
create table partner_payload (
  id              uuid        primary key default gen_random_uuid(),
  partner_id      uuid        not null references partner(id),
  external_ref    text        not null,
  payload_version text        not null,
  raw             jsonb       not null,
  raw_hash        char(64)    not null,
  correlation_id  uuid        not null,
  received_at     timestamptz not null default now(),
  unique (partner_id, external_ref, payload_version)
);

-- ------------------------------------------------------- Vereine / Personen

create table club (
  id           uuid primary key default gen_random_uuid(),
  partner_id   uuid not null references partner(id),
  external_ref text not null,
  name         text not null,
  created_at   timestamptz not null default now(),
  unique (partner_id, external_ref)
);

create table team (
  id           uuid primary key default gen_random_uuid(),
  club_id      uuid not null references club(id),
  external_ref text not null,
  name         text not null,
  season       text not null,
  sport        text,
  age_group    text,
  created_at   timestamptz not null default now(),
  unique (club_id, external_ref, season)
);

-- Betroffene Person. Bewusst getrennt vom Besteller.
create table person (
  id                     uuid primary key default gen_random_uuid(),
  partner_id             uuid not null references partner(id),
  external_ref           text not null,
  team_id                uuid references team(id),
  display_name           text not null,
  first_name             text,
  last_name              text,
  role                   person_role not null default 'FIELD',
  jersey_number          text,
  is_minor               boolean not null default false,
  contact_email          text,
  guardian_name          text,
  guardian_contact_email text,
  created_at             timestamptz not null default now(),
  unique (partner_id, external_ref),
  -- Bei Minderjaehrigen brauchen wir einen erreichbaren Erziehungsberechtigten,
  -- sonst laeuft jede Nachforderung ins Leere.
  constraint minor_needs_guardian_contact
    check (not is_minor or guardian_contact_email is not null or contact_email is not null)
);

-- Besteller / Rechnungsempfaenger. Nicht die betroffene Person.
create table ordering_contact (
  id         uuid primary key default gen_random_uuid(),
  club_id    uuid not null references club(id),
  name       text not null,
  email      text not null,
  phone      text,
  created_at timestamptz not null default now()
);

-- Die Einwilligung selbst liegt bei Sticker-Koenig. Wir speichern eine
-- eingefrorene AUSSAGE darueber. Aenderungen sind per Trigger gesperrt
-- (siehe 0002_state_machine.sql), nur Widerruf und Revalidierung sind erlaubt.
create table consent_assertion (
  id                  uuid     primary key default gen_random_uuid(),
  person_id           uuid     not null references person(id),
  partner_consent_id  text     not null,
  text_version        text     not null,
  subject_type        text     not null check (subject_type in ('SELF','GUARDIAN')),
  granted_at          timestamptz not null,
  evidence_ref        text,
  assertion_hash      char(64) not null,
  asserted_at         timestamptz not null default now(),
  last_revalidated_at timestamptz,
  revoked_at          timestamptz,
  unique (person_id, partner_consent_id)
);
create index consent_assertion_person_active on consent_assertion (person_id) where revoked_at is null;

-- ------------------------------------------------------- Fotos / Assets

-- Eine Quelle fuer Erklaerstrecke, Precheck und Gate 0.
create table photo_spec (
  version      text primary key,
  rules        jsonb not null,
  is_active    boolean not null default false,
  published_at timestamptz not null default now()
);
create unique index photo_spec_single_active on photo_spec (is_active) where is_active;

create table media_asset (
  id                 uuid primary key default gen_random_uuid(),
  partner_id         uuid not null references partner(id),
  person_id          uuid references person(id),
  parent_asset_id    uuid references media_asset(id),
  origin             asset_origin not null,
  content_hash       char(64) not null,
  storage_ref        text not null,
  mime_type          text not null,
  width_px           int,
  height_px          int,
  color_profile      text,
  processing_version text,
  quality_class      quality_class,
  landmarks          jsonb,          -- Augenlinie, Kopfhoehe, Schulterlinie (Schicht A)
  retention_class    retention_class not null,
  delete_after       timestamptz,
  deleted_at         timestamptz,
  created_at         timestamptz not null default now(),
  -- Abgeleitete Assets haben immer einen Vorfahren, Originale nie.
  constraint derived_has_parent check ((origin = 'DERIVED') = (parent_asset_id is not null))
);
create index media_asset_person   on media_asset (person_id);
create index media_asset_hash     on media_asset (content_hash);
create index media_asset_purge    on media_asset (delete_after) where deleted_at is null and delete_after is not null;

create table photo_assessment (
  id            uuid primary key default gen_random_uuid(),
  asset_id      uuid not null references media_asset(id) on delete cascade,
  spec_version  text not null references photo_spec(version),
  quality_class quality_class not null,
  reason_codes  text[] not null default '{}',
  metrics       jsonb  not null default '{}',
  source        text   not null check (source in ('PRECHECK','GATE0')),
  assessed_at   timestamptz not null default now()
);
create index photo_assessment_asset on photo_assessment (asset_id, assessed_at desc);
create index photo_assessment_class on photo_assessment (assessed_at, quality_class) where source = 'GATE0';

-- ------------------------------------------------------- Design / Templates

create table print_spec (
  id              text primary key,
  name            text not null,
  trim_width_mm   numeric(6,2) not null,
  trim_height_mm  numeric(6,2) not null,
  bleed_mm        numeric(4,2) not null,
  safe_margin_mm  numeric(4,2) not null,
  substrate       text not null,
  finishing       text,
  color_profile   text not null,
  min_dpi         int  not null default 300,
  min_batch_size  int
);

-- Alle vier Templates teilen dasselbe Slot-Schema: ein Renderer, ein
-- QA-Regelsatz, ein Golden Set.
create table slot_schema (
  id           text primary key,
  version      text not null,
  definition   jsonb not null,
  published_at timestamptz not null default now()
);

create table design_family (
  id              text primary key,
  name            text not null,
  applies_to_role person_role,
  -- Diese Entscheidung wird GEDRUCKT und ist danach nicht korrigierbar:
  -- false = ein QR-Token je Karteninhalt, true = eines je physischer Kopie.
  token_per_copy  boolean not null default false,
  is_placeholder  boolean not null default true
);

create table design_version (
  id              uuid primary key default gen_random_uuid(),
  family_id       text not null references design_family(id),
  version         text not null,
  slot_schema_id  text not null references slot_schema(id),
  print_spec_id   text not null references print_spec(id),
  assets          jsonb not null default '{}'::jsonb,
  published_at    timestamptz,
  -- Canary: die ersten n Karten einer neuen Version gehen in die
  -- menschliche Freigabe, bevor sie vollautomatisch laufen.
  canary_remaining int not null default 20 check (canary_remaining >= 0),
  unique (family_id, version)
);

create table team_design_context (
  id                 uuid primary key default gen_random_uuid(),
  team_id            uuid not null references team(id),
  club_logo_asset_id uuid references media_asset(id),
  sponsor_asset_id   uuid references media_asset(id),
  season             text not null,
  palette            jsonb not null default '{}'::jsonb,
  unique (team_id, season)
);

-- ------------------------------------------------------- Auftrag

create table team_order (
  id                        uuid primary key default gen_random_uuid(),
  partner_id                uuid not null references partner(id),
  team_id                   uuid not null references team(id),
  ordering_contact_id       uuid references ordering_contact(id),
  design_context_id         uuid references team_design_context(id),
  external_ref              text not null,
  default_design_version_id uuid references design_version(id),
  fulfillment_policy        fulfillment_policy not null default 'PARTIAL_WITH_HOLD',
  shipment_policy           shipment_policy    not null default 'CONSOLIDATE',
  hold_until                timestamptz,
  promised_delivery_at      timestamptz,
  snapshot                  jsonb,
  snapshot_hash             char(64),
  accepted_at               timestamptz,
  lifecycle_state           team_order_lifecycle not null default 'RECEIVED',
  correlation_id            uuid not null default gen_random_uuid(),
  created_at                timestamptz not null default now(),
  unique (partner_id, external_ref),
  -- Ohne eingefrorenen Snapshot laesst sich nach einer Reklamation nicht
  -- rekonstruieren, was gedruckt wurde.
  constraint accepted_needs_snapshot
    check (accepted_at is null or (snapshot is not null and snapshot_hash is not null))
);
create index team_order_hold on team_order (hold_until) where hold_until is not null;

-- Regeln werden EINMAL bei Auftragsannahme ausgewertet und in die Zeile
-- geschrieben. Nie lazy beim Rendern aufloesen.
create table design_rule (
  id                uuid primary key default gen_random_uuid(),
  team_order_id     uuid not null references team_order(id) on delete cascade,
  match_role        person_role not null,
  design_version_id uuid not null references design_version(id),
  unique (team_order_id, match_role)
);

create table order_line (
  id                 uuid primary key default gen_random_uuid(),
  team_order_id      uuid not null references team_order(id) on delete cascade,
  person_id          uuid not null references person(id),
  design_version_id  uuid not null references design_version(id),
  quantity           int  not null check (quantity between 1 and 50),
  line_type          line_type not null default 'BASE_PACK',
  unit_price_cents   int  not null default 0 check (unit_price_cents >= 0),
  currency           char(3) not null default 'EUR',
  -- Steuert die Konfektionierung: Zusatzkarten gehoeren in das Tuetchen
  -- DIESES Spielers, nicht lose in den Karton.
  recipient_group_key text not null,
  design_resolved_by  text not null default 'RULE'
                      check (design_resolved_by in ('RULE','DEFAULT','MANUAL')),
  created_at          timestamptz not null default now(),
  unique (team_order_id, person_id, design_version_id, line_type)
);
create index order_line_order on order_line (team_order_id);

-- ------------------------------------------------------- Produktion

create table production_wave (
  id            uuid primary key default gen_random_uuid(),
  team_order_id uuid not null references team_order(id) on delete cascade,
  sequence      int  not null check (sequence >= 1),
  reason        text,
  released_at   timestamptz,
  created_at    timestamptz not null default now(),
  unique (team_order_id, sequence)
);

create table print_batch (
  id                     uuid primary key default gen_random_uuid(),
  print_spec_id          text not null references print_spec(id),
  state                  print_batch_state not null default 'OPEN',
  external_job_ref       text,
  manifest_hash          char(64),
  sealed_at              timestamptz,
  consent_revalidated_at timestamptz,
  transferred_at         timestamptz,
  acknowledged_at        timestamptz,
  created_at             timestamptz not null default now()
);
create index print_batch_open        on print_batch (print_spec_id) where state = 'OPEN';
create index print_batch_unacked     on print_batch (transferred_at)
                                     where transferred_at is not null and acknowledged_at is null;

create table shipment (
  id            uuid primary key default gen_random_uuid(),
  team_order_id uuid not null references team_order(id),
  carrier_ref   text,
  shipped_at    timestamptz,
  delivered_at  timestamptz,
  created_at    timestamptz not null default now()
);

-- Content-addressed: gleicher Input -> gleicher Fingerprint -> ein Rendering
-- fuer alle identischen Kopien.
create table render_artifact (
  fingerprint       char(64) primary key,
  design_version_id uuid not null references design_version(id),
  engine_version    text not null,
  pdf_ref           text not null,
  preview_ref       text,
  manifest          jsonb not null,
  retention_class   retention_class not null default 'PRINT_ARTIFACT',
  delete_after      timestamptz,
  created_at        timestamptz not null default now()
);

-- Ein aktuelles Verdikt je Artefakt. Die Historie liegt im domain_event.
create table qa_verdict (
  fingerprint      char(64) primary key references render_artifact(fingerprint) on delete cascade,
  decision         qa_decision not null,
  confidence       numeric(4,3) check (confidence is null or confidence between 0 and 1),
  gate_results     jsonb not null default '{}'::jsonb,
  -- Gate 3d: der aus dem gerasterten PDF ZURUECKGELESENE Token.
  qr_token_decoded text,
  attempt          int not null default 1,
  decided_by       text not null default 'SYSTEM',
  decided_at       timestamptz not null default now(),
  constraint pass_requires_decoded_qr
    check (decision <> 'PASS' or qr_token_decoded is not null)
);

-- Die digitale Karte hinter dem QR-Code.
-- public_token ist STABIL und wird gedruckt. published_fingerprint zeigt auf
-- den aktuell ausgelieferten Inhalt und darf sich beliebig oft aendern.
create table card_twin (
  id                    uuid primary key default gen_random_uuid(),
  public_token          text not null unique,
  order_line_id         uuid not null references order_line(id) on delete cascade,
  copy_index            int,                 -- null = gilt fuer alle Kopien der Zeile
  published_fingerprint char(64) references render_artifact(fingerprint),
  published_at          timestamptz,
  revoked_at            timestamptz,
  created_at            timestamptz not null default now(),
  constraint token_is_base58_22 check (public_token ~ '^[1-9A-HJ-NP-Za-km-z]{22}$')
);
create unique index card_twin_scope on card_twin (order_line_id, coalesce(copy_index, -1));

create table card_item (
  id                  uuid primary key default gen_random_uuid(),
  order_line_id       uuid not null references order_line(id) on delete cascade,
  copy_index          int  not null check (copy_index >= 1),
  state               card_item_state not null default 'DRAFT',
  state_before_block  card_item_state,
  artifact_fingerprint char(64) references render_artifact(fingerprint),
  source_asset_id     uuid references media_asset(id),
  card_twin_id        uuid references card_twin(id),
  wave_id             uuid references production_wave(id),
  print_batch_id      uuid references print_batch(id),
  sheet_position      int,
  shipment_id         uuid references shipment(id),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (order_line_id, copy_index)
);
create index card_item_state       on card_item (state);
create index card_item_batch       on card_item (print_batch_id) where print_batch_id is not null;
create index card_item_fingerprint on card_item (artifact_fingerprint);

-- Schwere und Zustaendigkeit gehoeren an den GRUND, nicht an den Einzelfall.
-- Sonst legt irgendwann jemand einen SOFT-Blocker fuer eine fehlende
-- Einwilligung an.
create table blocker_catalog (
  reason           blocker_reason primary key,
  severity         blocker_severity not null,
  default_owner    blocker_owner not null,
  auto_remediation text,
  label_de         text not null
);

create table blocker (
  id                  uuid primary key default gen_random_uuid(),
  card_item_id        uuid not null references card_item(id) on delete cascade,
  reason              blocker_reason not null references blocker_catalog(reason),
  severity            blocker_severity not null,
  owner               blocker_owner not null,
  detail              text,
  remediation_attempts int not null default 0,
  opened_at           timestamptz not null default now(),
  resolved_at         timestamptz
);
create unique index blocker_one_open_per_reason on blocker (card_item_id, reason) where resolved_at is null;
create index blocker_open on blocker (severity, opened_at) where resolved_at is null;

-- ------------------------------------------------------- Kommunikation

create table message (
  id              uuid primary key default gen_random_uuid(),
  team_order_id   uuid references team_order(id) on delete cascade,
  person_id       uuid references person(id),
  recipient_email text not null,
  channel         message_channel not null default 'EMAIL',
  template        text not null,
  -- Verhindert Doppelversaende ueber Retries und Neustarts hinweg.
  dedupe_key      text not null unique,
  payload         jsonb not null default '{}'::jsonb,
  delivery_status delivery_status not null default 'QUEUED',
  bounce_reason   text,
  sent_at         timestamptz,
  created_at      timestamptz not null default now()
);
create index message_bounced on message (created_at) where delivery_status = 'BOUNCED';

-- ------------------------------------------------------- Betrieb

create table system_config (
  key                      text primary key,
  value                    text not null,
  unit                     text,
  is_placeholder           boolean not null default false,
  affects_customer_promise boolean not null default false,
  description_de           text,
  changed_by               text,
  changed_at               timestamptz not null default now()
);

create table domain_event (
  id             bigint generated always as identity primary key,
  correlation_id uuid not null,
  subject_type   text not null,
  subject_id     uuid,
  event_type     text not null,
  payload        jsonb not null default '{}'::jsonb,
  actor          text,
  occurred_at    timestamptz not null default now()
);
create index domain_event_correlation on domain_event (correlation_id, id);
create index domain_event_subject     on domain_event (subject_type, subject_id, id);
