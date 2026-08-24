#!/usr/bin/env python3
"""Startet das Cockpit örtlich.

  PGDATABASE=tce python3 tools/run_cockpit.py --port 8099
"""
from __future__ import annotations

import argparse, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from cockpit.app import serve            # noqa: E402
from cockpit.store import CockpitStore   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    httpd = serve(CockpitStore(), args.host, args.port)
    print(f"Cockpit auf http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
