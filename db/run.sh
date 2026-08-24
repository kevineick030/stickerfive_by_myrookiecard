#!/usr/bin/env bash
# Spielt Migrationen, Seed und optional den Smoke-Test ein.
#   ./db/run.sh                 -> Migrationen + Seed
#   ./db/run.sh --with-test     -> zusaetzlich der Smoke-Test
# Verbindung ueber die ueblichen PG*-Umgebungsvariablen (PGHOST, PGPORT, ...).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Spezifikationen -> Seed generieren"
python3 tools/gen_spec_seed.py

for f in db/migrations/*.sql; do
  echo "== migration $f"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
done

for f in db/seed/*.sql; do
  echo "== seed $f"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
done

if [[ "${1:-}" == "--with-test" ]]; then
  echo "== smoke test"
  psql -v ON_ERROR_STOP=1 -f db/test/smoke_test.sql
fi
echo "== fertig"
