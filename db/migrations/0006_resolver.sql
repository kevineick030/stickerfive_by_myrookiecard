-- =====================================================================
-- Trading-Card-Engine · 0006 · Aufloesungsdienst hinter dem QR-Code
--
-- Der gedruckte Code ist unveraenderlich. Alles, was sich aendern koennen
-- muss, liegt deshalb HINTER dem Token: welcher Inhalt ausgeliefert wird,
-- ob ueberhaupt ausgeliefert wird, und wo die Datei liegt.
-- =====================================================================

-- Beim Druck wird die digitale Karte veroeffentlicht: ab jetzt existiert
-- die physische Karte, also muss der Code funktionieren.
create or replace function card_item_publish_twin() returns trigger
language plpgsql as $$
begin
  if new.state = 'PRINTED' and old.state is distinct from 'PRINTED' then
    update card_twin
       set published_fingerprint = new.artifact_fingerprint,
           published_at = coalesce(published_at, now())
     where id = new.card_twin_id
       and revoked_at is null;
  end if;

  -- Nachdruck mit korrigiertem Inhalt: derselbe Token zeigt danach auf die
  -- neue Fassung. Der Code auf der alten Karte funktioniert weiter.
  if new.state = 'PRINTED' and new.artifact_fingerprint is distinct from old.artifact_fingerprint then
    update card_twin set published_fingerprint = new.artifact_fingerprint
     where id = new.card_twin_id and revoked_at is null;
  end if;

  return new;
end $$;

create trigger card_item_publish_twin_trg
  after update on card_item
  for each row execute function card_item_publish_twin();

-- --------------------------------------------------- Zaehlung
-- Bewusst nur Tagessummen je Karte: keine IP, kein Geraet, keine Uhrzeit.
-- Fuer "wie oft wird gescannt" reicht das, und es entsteht kein
-- Bewegungsprofil von Kindern.
create table twin_scan_daily (
  twin_id uuid not null references card_twin(id) on delete cascade,
  day     date not null default current_date,
  scans   int  not null default 0,
  primary key (twin_id, day)
);

create or replace function record_twin_scan(p_twin uuid) returns void
language plpgsql as $$
begin
  insert into twin_scan_daily (twin_id, day, scans) values (p_twin, current_date, 1)
  on conflict (twin_id, day) do update set scans = twin_scan_daily.scans + 1;
end $$;

-- --------------------------------------------------- Aufloesung
-- Gibt fuer JEDEN nicht auslieferbaren Fall dieselbe Antwort zurueck -
-- unbekannt, widerrufen oder noch nicht gedruckt sehen von aussen gleich
-- aus. Sonst waere der Dienst ein Orakel, mit dem sich pruefen laesst,
-- welche Token existieren.
create or replace function resolve_twin(p_token text)
returns jsonb language plpgsql as $$
declare v jsonb; v_twin uuid;
begin
  select tw.id,
         jsonb_build_object(
           'status',        'OK',
           'token',         tw.public_token,
           'player_name',   p.display_name,
           'club_name',     c.name,
           'team_name',     t.name,
           'season',        t.season,
           'role',          p.role,
           'jersey_number', p.jersey_number,
           'design_family', dv.family_id,
           'card_number',   ci.copy_index,
           'card_total',    ol.quantity,
           'fingerprint',   tw.published_fingerprint,
           'published_at',  tw.published_at)
    into v_twin, v
    from card_twin tw
    join order_line     ol on ol.id = tw.order_line_id
    join person         p  on p.id  = ol.person_id
    join team_order     o  on o.id  = ol.team_order_id
    join team           t  on t.id  = o.team_id
    join club           c  on c.id  = t.club_id
    join design_version dv on dv.id = ol.design_version_id
    left join card_item ci on ci.card_twin_id = tw.id
   where tw.public_token = p_token
     and tw.revoked_at is null
     and tw.published_at is not null
   limit 1;

  if v is null then
    -- Eine einzige, nichtssagende Antwort fuer alle Fehlschlaege.
    return jsonb_build_object('status', 'GONE');
  end if;

  perform record_twin_scan(v_twin);
  return v;
end $$;

-- --------------------------------------------------- Betriebssicht
create or replace view v_twin_health as
select count(*)                                                as twins_gesamt,
       count(*) filter (where published_at is not null)         as veroeffentlicht,
       count(*) filter (where revoked_at is not null)           as widerrufen,
       count(*) filter (where token_source = 'PARTNER')         as fremd_vergeben,
       (select coalesce(sum(scans), 0) from twin_scan_daily
         where day > current_date - 30)                         as scans_30_tage
from card_twin;
