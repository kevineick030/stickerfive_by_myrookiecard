#!/usr/bin/env python3
"""Startet den Aufloesungsdienst oertlich.

  PGHOST=… PGDATABASE=… python3 tools/run_resolver.py --port 8088

Verbindet ueber PsqlStore mit der Datenbank. Danach liefert
http://127.0.0.1:8088/k/<token> die digitale Karte aus.
"""
from __future__ import annotations

import argparse, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from resolver.app import serve            # noqa: E402
from resolver.store import PsqlStore      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    args = ap.parse_args()

    httpd = serve(PsqlStore(), args.host, args.port)
    print(f"Auflösungsdienst auf http://{args.host}:{args.port}/k/<token>", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
