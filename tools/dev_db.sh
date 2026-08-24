#!/usr/bin/env bash
# Startet eine oertliche PostgreSQL-Instanz fuer die Entwicklung und legt die
# Datenbank frisch an. Mit --demo zusaetzlich Beispieldaten.
#   ./tools/dev_db.sh --demo && export PGHOST=/tmp/pgs PGPORT=5433 PGUSER=tce PGDATABASE=tce
set -euo pipefail
cd "$(dirname "$0")/.."

PGBIN=${PGBIN:-/usr/lib/postgresql/16/bin}
DATA=${PGDEVDATA:-/tmp/pgtce/data}
SOCK=${PGDEVSOCK:-/tmp/pgs}
PORT=${PGDEVPORT:-5433}

mkdir -p "$SOCK"
id postgres >/dev/null 2>&1 && chown -R postgres "$SOCK" 2>/dev/null || true

if [ ! -f "$DATA/PG_VERSION" ]; then
  rm -rf "$(dirname "$DATA")"; mkdir -p "$DATA"
  chown -R postgres "$(dirname "$DATA")" 2>/dev/null || true
  su postgres -c "$PGBIN/initdb -D $DATA -U tce --auth=trust -E UTF8 --locale=C" >/dev/null
fi

su postgres -c "$PGBIN/pg_ctl -D $DATA status" >/dev/null 2>&1 || \
  su postgres -c "$PGBIN/pg_ctl -D $DATA -o '-k $SOCK -p $PORT -c listen_addresses=' \
     -l $(dirname "$DATA")/pg.log start" >/dev/null

export PGHOST="$SOCK" PGPORT="$PORT" PGUSER=tce PGDATABASE=postgres
for _ in $(seq 1 20); do psql -tAc "select 1" >/dev/null 2>&1 && break; sleep 0.3; done

psql -q -c "drop database if exists tce"
psql -q -c "create database tce"
export PGDATABASE=tce
./db/run.sh >/dev/null

if [ "${1:-}" = "--demo" ]; then
  python3 tools/demo_flow.py | tail -12
  python3 tools/demo_ops.py  | tail -12
fi
echo "Datenbank bereit: PGHOST=$SOCK PGPORT=$PORT PGUSER=tce PGDATABASE=tce"
