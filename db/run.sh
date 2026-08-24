#!/usr/bin/env bash
# Spielt Migrationen, Seed und optional die Tests ein.
#   ./db/run.sh                 -> Migrationen + Seed
#   ./db/run.sh --with-test     -> zusaetzlich die SQL-Tests
# Verbindung ueber die ueblichen PG*-Umgebungsvariablen (PGHOST, PGPORT, ...).
#
# Bereits angewandte Migrationen werden uebersprungen: die Datei
# schema_migrations haelt fest, was schon eingespielt ist. Ein zweiter Lauf
# ist damit folgenlos, und ein bestehender Bestand bekommt nur das Neue.
set -euo pipefail
cd "$(dirname "$0")/.."

psql -v ON_ERROR_STOP=1 -q -c "
  create table if not exists schema_migrations (
    filename   text primary key,
    applied_at timestamptz not null default now()
  )"

echo "== Spezifikationen -> Seed generieren"
python3 tools/gen_spec_seed.py

for f in db/migrations/*.sql; do
  name=$(basename "$f")
  if [ "$(psql -tAc "select 1 from schema_migrations where filename = '$name'")" = "1" ]; then
    echo "== bereits angewandt $name"
    continue
  fi
  echo "== migration $name"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
  psql -v ON_ERROR_STOP=1 -q -c "insert into schema_migrations (filename) values ('$name')"
done

# Referenzdaten sind idempotent und laufen bei jedem Aufruf mit, damit
# geaenderte Spezifikationen ankommen.
for f in db/seed/*.sql; do
  echo "== seed $(basename "$f")"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
done

if [[ "${1:-}" == "--with-test" ]]; then
  for t in db/test/*.sql; do
    echo "== test $(basename "$t")"
    psql -v ON_ERROR_STOP=1 -f "$t"
  done
fi
echo "== fertig"
