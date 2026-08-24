-- =====================================================================
-- Trading-Card-Engine · Seed 0001 · Referenzdaten
-- Idempotent: kann beliebig oft eingespielt werden.
-- =====================================================================

-- ---------------------------------------------------- Blocker-Katalog
-- Schwere und Zustaendigkeit haengen am GRUND, nicht am Einzelfall.
insert into blocker_catalog (reason, severity, default_owner, auto_remediation, label_de) values
  ('CONSENT_MISSING',            'HARD','PARTNER', null,                          'Einwilligung fehlt'),
  ('CONSENT_REVOKED',            'HARD','PARTNER', null,                          'Einwilligung widerrufen'),
  ('GUARDIAN_CONSENT_MISSING',   'HARD','PARTNER', null,                          'Minderjährig ohne Nachweis der Erziehungsberechtigten'),
  ('CONSENT_REVALIDATION_FAILED','HARD','PARTNER', null,                          'Revalidierung vor Transfer fehlgeschlagen'),
  ('PHOTO_MISSING',              'SOFT','CUSTOMER','notify_customer',             'Foto fehlt'),
  ('PHOTO_REJECTED',             'SOFT','CUSTOMER','notify_customer_with_reason', 'Foto abgelehnt (Klasse C)'),
  ('CUTOUT_FAILED',              'SOFT','INTERNAL','retry_ladder',                'Freistellung fehlgeschlagen'),
  ('QA_FAILED',                  'SOFT','INTERNAL','rerender_then_review',        'QA nicht bestanden'),
  ('MASTERDATA_INCOMPLETE',      'SOFT','PARTNER', 'notify_partner',              'Stammdaten unvollständig'),
  ('CONTACT_UNREACHABLE',        'SOFT','CLUB',    'escalate_to_coach',           'Kontakt nicht erreichbar (Bounce)')
on conflict (reason) do update
  set severity = excluded.severity,
      default_owner = excluded.default_owner,
      auto_remediation = excluded.auto_remediation,
      label_de = excluded.label_de;

-- ---------------------------------------------------- Druckspezifikationen
insert into print_spec
  (id, name, trim_width_mm, trim_height_mm, bleed_mm, safe_margin_mm, substrate, finishing, color_profile, min_dpi, min_batch_size)
values
  ('PS-STD',  'Standardbogen',  63.0, 88.0, 2.0, 4.0, '300 g Chromokarton', 'matt laminiert 4/4',            'ISO Coated v2 (ECI)', 300, 250),
  ('PS-GOLD', 'Goldveredelung', 63.0, 88.0, 2.0, 4.0, '300 g Chromokarton', 'Heissfolienpraegung gold, 4/4', 'ISO Coated v2 (ECI)', 300, 250)
on conflict (id) do update
  set name = excluded.name, substrate = excluded.substrate,
      finishing = excluded.finishing, min_batch_size = excluded.min_batch_size;

-- ---------------------------------------------------- Betriebsparameter
-- Keiner dieser Werte gehoert in den Code. is_placeholder = true heisst:
-- fachlich NICHT bestaetigt, darf keine Vertragszusage begruenden.
insert into system_config (key, value, unit, is_placeholder, affects_customer_promise, description_de) values
  ('print.min_batch_size',                 '250',  'Karten',   true,  true,  'Mindestlosgröße der Druckerei — offen'),
  ('print.lead_time_days',                 '10',   'Werktage', true,  true,  'Vorlaufzeit der Druckerei — offen'),
  ('order.promised_lead_time_days',        '15',   'Werktage', true,  true,  'Zugesagte Lieferzeit gegenüber dem Verein — offen'),
  ('order.hold_until_days',                '14',   'Tage',     true,  true,  'Karenzfrist vor dem automatischen Wellen-Split'),
  ('order.max_consolidation_wait_days',    '7',    'Tage',     true,  false, 'Maximale Wartezeit für die konsolidierte Lieferung'),
  ('order.wave_split_cost_threshold',      '40',   'Karten',   true,  false, 'Unterhalb dieser Menge sammelt sich eine Welle mit anderen Aufträgen'),
  ('comm.reminder_cadence_days',           '3,7,10','Tage',    false, false, 'Eskalationsleiter der Nachforderungen'),
  ('comm.quiet_hours',                     '21-08','Uhr',      false, false, 'Keine Nachrichten in diesem Fenster'),
  ('consent.revalidation_max_age_minutes', '30',   'Minuten',  false, false, 'Maximales Alter der Revalidierung beim Transfer'),
  ('photo.spec_version',                   '1.0.0', null,      false, false, 'Aktive photo_spec'),
  ('qa.auto_pass_target',                  '99.0', '%',        false, false, 'Zielwert Auto-Pass-Rate'),
  ('qa.ocr_levenshtein_max',               '1',    null,       false, false, 'Maximale Editierdistanz bei Namen über 6 Zeichen'),
  ('qa.image_similarity_min',              '0.82', null,       true,  false, 'Schwelle Bildidentität Quelle ↔ Rendering'),
  ('qa.vision_sample_rate',                '2',    '%',        false, false, 'Stichprobenrate für das Vision-Modell'),
  ('qa.canary_cards_per_design_version',   '20',   'Karten',   false, false, 'Menschliche Freigabe für neue Template-Versionen'),
  ('retention.raw_upload_days',            '90',   'Tage',     true,  false, 'Rohfoto nach Auslieferung — juristisch zu bestätigen'),
  ('retention.cutout_months',              '24',   'Monate',   true,  false, 'Freisteller, ermöglicht Nachdruck ohne neues Foto'),
  ('retention.print_artifact_months',      '24',   'Monate',   true,  false, 'Druck-PDF für Reklamation und Nachdruck'),
  ('twin.availability_commitment_years',   '10',   'Jahre',    true,  true,  'Verfügbarkeitszusage digitale Karte — AGB, zu entscheiden'),
  ('twin.resolver_host',                   'k.mrc.cards', null, true, false, 'Domain der digitalen Karte. Budget 74 Byte — kurz ist besser (größere QR-Module), aber nicht zwingend'),
  ('design.template_count',                '4',    null,       false, false, 'Anzahl der Templates zum Start')
on conflict (key) do update
  set value = excluded.value, unit = excluded.unit,
      is_placeholder = excluded.is_placeholder,
      affects_customer_promise = excluded.affects_customer_promise,
      description_de = excluded.description_de;

-- ---------------------------------------------------- Design-Familien
-- ENTSCHIEDEN: token_per_copy = true. Jede physische Karte traegt einen
-- eigenen QR-Token und ist damit einzeln identifizierbar - Voraussetzung
-- fuer eine spaetere Tausch- oder Echtheitsfunktion.
-- Kostenfolge: drei Kopien = drei Rueckseiten. Die Vorderseite wird ueber
-- render_artifact.front_fingerprint wiederverwendet, ebenso die teuren
-- QA-Gates. Siehe docs/architecture/datenmodell.md.
--
-- Die Namen sind Platzhalter, bis der Zuschnitt feststeht.
insert into design_family (id, name, applies_to_role, token_per_copy, is_placeholder) values
  ('DESIGN-1', 'Design 1', 'FIELD',  true, true),
  ('DESIGN-2', 'Design 2', 'KEEPER', true, true),
  ('DESIGN-3', 'Design 3', 'COACH',  true, true),
  ('DESIGN-4', 'Design 4', null,     true, true)
on conflict (id) do update
  set name = excluded.name,
      applies_to_role = excluded.applies_to_role,
      token_per_copy = excluded.token_per_copy;
