#!/usr/bin/env python3
import signal, sys as _s
try: signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except Exception: pass
"""Leitet die Fotoanforderungen aus der Slot-Geometrie ab.

Die Zahlen in photo_spec sind keine Schaetzung: Sie folgen aus Bild-Slot,
Ankerregel und Ziel-dpi. Aendert sich das Template, aendern sie sich mit -
deshalb wird hier gerechnet und nicht getippt.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
schema = json.loads((ROOT / "specs" / "slot_schema.v1.json").read_text(encoding="utf-8"))
photo = next(s for s in schema["front"]["slots"] if s["id"] == "photo")
box, anchors = photo["box"], photo["anchors"]
dpi = schema["geometry"]["min_dpi"]
mm_per_px = 25.4 / dpi

head_mm = anchors["head_height_ratio"] * box["h"]
min_head_px = head_mm / mm_per_px

print(f"Bild-Slot          {box['w']} × {box['h']} mm")
print(f"Kopfhöhe auf Karte {head_mm:.2f} mm ({anchors['head_height_ratio']:.0%} der Slot-Höhe)")
print(f"Ziel               {dpi} dpi")
print(f"→ Mindest-Kopfhöhe im Quellbild: {min_head_px:.0f} px\n")

print("Daraus folgende Mindesthöhe des Gesamtbilds, je nach Bildausschnitt:")
for ratio in (0.35, 0.40, 0.45, 0.55):
    print(f"   Kopf = {ratio:.0%} der Bildhöhe  →  Bild mindestens {min_head_px/ratio:>6.0f} px hoch")

print("\nEffektive Auflösung bei gegebener Kopfhöhe im Quellbild:")
for head_px in (300, 391, 500, 700, 960):
    scale = head_mm / head_px
    eff = 25.4 / scale
    mark = "OK " if eff >= dpi - 0.5 else "ZU WENIG"
    print(f"   {head_px:>4} px Kopf  →  {eff:>6.0f} dpi   {mark}")
sys.exit(0)
