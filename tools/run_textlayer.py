#!/usr/bin/env python3
"""Startet den Textlayer-Dienst.  python3 tools/run_textlayer.py --port 8081"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from textlayer.app import serve  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8081)
serve(ap.parse_args().port)
