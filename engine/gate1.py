"""Gate 1 - deterministische Pruefung des Render-Manifests.

Faengt den Grossteil aller Fehler ab, ohne dass eine einzige KI-Anfrage
noetig waere. Alles hier ist rechenbar: Geometrie, Schriftmasse, Glyph-
abdeckung, Aufloesung, QR-Modulgroesse.

Was Gate 1 NICHT kann, ist zu sehen, ob der richtige Name auf dem richtigen
Foto steht - das ist Gate 3 auf den gerasterten Pixeln.
"""
from __future__ import annotations

from dataclasses import dataclass

SEVERITY_ORDER = {"FAIL": 0, "WARN": 1}


@dataclass(frozen=True)
class Finding:
    severity: str      # FAIL | WARN
    code: str
    slot: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code} · {self.slot}: {self.message}"


def check(manifest: dict, min_dpi: int | None = None) -> list[Finding]:
    geo = manifest["geometry"]
    min_dpi = min_dpi or geo.get("min_dpi", 300)
    bleed, safe = geo["bleed"], geo["safe_margin"]
    trim_w, trim_h = geo["trim_width"], geo["trim_height"]
    out: list[Finding] = []

    for side in ("front", "back"):
        boxes: list[tuple[str, dict]] = []

        for p in manifest[side]["placements"]:
            sid, kind = p["slot"], p["type"]
            box = p.get("box_mm")

            if p.get("required") and p.get("empty"):
                out.append(Finding("FAIL", "REQUIRED_SLOT_EMPTY", sid,
                                   "Pflicht-Slot ohne Inhalt"))
                continue

            if box:
                if (box["x"] < -bleed - 1e-6 or box["y"] < -bleed - 1e-6
                        or box["x"] + box["w"] > trim_w + bleed + 1e-6
                        or box["y"] + box["h"] > trim_h + bleed + 1e-6):
                    out.append(Finding("FAIL", "BOX_OUTSIDE_SHEET", sid,
                                       "Slot liegt ausserhalb von Endformat plus Anschnitt"))

            if kind == "text":
                if p.get("overflow"):
                    out.append(Finding(
                        "FAIL", "TEXT_OVERFLOW", sid,
                        f'"{p["text"]}" passt auch bei {p["min_size_pt"]} pt nicht in '
                        f'{p["box_mm"]["w"]} mm (gemessen {p["measured_width_mm"]} mm)'))
                elif p.get("autofit_applied"):
                    out.append(Finding(
                        "WARN", "TEXT_AUTOFIT", sid,
                        f'verkleinert von {p["declared_size_pt"]} auf {p["size_pt"]} pt'))

                if p.get("missing_glyphs"):
                    out.append(Finding(
                        "FAIL", "MISSING_GLYPH", sid,
                        "Schrift kennt diese Zeichen nicht: "
                        + " ".join(f'"{c}" (U+{ord(c):04X})' for c in p["missing_glyphs"])))

                # Textboxen im Anschnitt sind fast immer ein Layoutfehler.
                if box and (box["x"] < safe - 1e-6
                            or box["x"] + box["w"] > trim_w - safe + 1e-6
                            or box["y"] < safe - 1e-6
                            or box["y"] + box["h"] > trim_h - safe + 1e-6):
                    out.append(Finding("WARN", "TEXT_IN_SAFE_MARGIN", sid,
                                       "Textbox ragt in die Sicherheitszone"))
                if box:
                    boxes.append((sid, box))

            elif kind == "image":
                if p["effective_dpi"] < min_dpi:
                    out.append(Finding(
                        "FAIL", "LOW_EFFECTIVE_DPI", sid,
                        f'{p["effective_dpi"]} dpi nach der Ankerskalierung, '
                        f'gefordert {min_dpi} — das Foto war zu knapp'))
                if not p.get("covers_slot", True):
                    out.append(Finding("FAIL", "PHOTO_DOES_NOT_COVER", sid,
                                       "Das Bild fuellt den Slot nicht aus, es bliebe eine Luecke"))
                if p.get("scale_adjusted_for_coverage"):
                    dev, tol = p["head_ratio_deviation"], p["coverage_scale_tolerance"]
                    sev = "WARN" if abs(dev) <= tol else "FAIL"
                    out.append(Finding(
                        sev, "HEAD_RATIO_OFF_TARGET", sid,
                        f'zu eng um den Kopf fotografiert: hochskaliert, damit das Bild den '
                        f'Slot deckt. Kopf {dev:+.1%} gegenueber dem Zielmass '
                        f'(Toleranz {tol:.0%}) — die Karte faellt aus dem Set'))
                if p.get("cutout") and p.get("subject_bottom_mm") is not None:
                    luft = p["slot_bottom_mm"] - p["subject_bottom_mm"]
                    if luft > 3.0:
                        out.append(Finding(
                            "WARN" if luft <= 8.0 else "FAIL", "SUBJECT_FLOATS", sid,
                            f'der Oberkoerper endet {luft} mm ueber der Unterkante des '
                            f'Fotofensters — der Spieler schwebt, statt in der Karte zu stehen. '
                            f'Es fehlt Bild unterhalb des Kopfes'))
                if p.get("fit_mode") == "ANCHOR":
                    if p["head_top_mm"] < safe - 1e-6:
                        out.append(Finding(
                            "FAIL", "HEAD_IN_TRIM_ZONE", sid,
                            f'Kopfoberkante bei {p["head_top_mm"]} mm liegt in der '
                            f'Sicherheitszone von {safe} mm — der Kopf wuerde angeschnitten'))
                    if p["chin_mm"] > box["y"] + box["h"] + 1e-6:
                        out.append(Finding("FAIL", "CHIN_OUTSIDE_SLOT", sid,
                                           "Das Kinn liegt ausserhalb des Bild-Slots"))

            elif kind == "qr":
                if p["version"] is None:
                    out.append(Finding(
                        "FAIL", "QR_PAYLOAD_TOO_LONG", sid,
                        f'{p["payload_bytes"]} Byte passen in keine unterstuetzte Version'))
                elif not p["module_ok"]:
                    out.append(Finding(
                        "FAIL", "QR_MODULE_TOO_SMALL", sid,
                        f'{p["module_mm"]} mm je Modul bei Version {p["version"]}, '
                        f'Minimum {p["min_module_mm"]} mm — der Code waere im Druck '
                        f'nicht zuverlaessig lesbar'))
                elif p["payload_bytes"] > p["payload_budget_bytes"] * 0.85:
                    out.append(Finding(
                        "WARN", "QR_NEAR_BUDGET", sid,
                        f'{p["payload_bytes"]} von {p["payload_budget_bytes"]} Byte belegt — '
                        f'ein laengerer Host wuerde die Module verkleinern'))

        # Ueberlappende Textboxen: im PDF sieht das nach Absicht aus, im Druck nicht.
        for i, (sid_a, a) in enumerate(boxes):
            for sid_b, b in boxes[i + 1:]:
                if (a["x"] < b["x"] + b["w"] - 1e-6 and b["x"] < a["x"] + a["w"] - 1e-6
                        and a["y"] < b["y"] + b["h"] - 1e-6 and b["y"] < a["y"] + a["h"] - 1e-6):
                    out.append(Finding("WARN", "BOX_OVERLAP", f"{sid_a}+{sid_b}",
                                       "Textboxen ueberlappen sich"))

    # Gate 3a braucht mindestens ein Prueffeld, sonst laeuft das OCR ins Leere.
    if not any(p.get("qa_region") for side in ("front", "back")
               for p in manifest[side]["placements"]):
        out.append(Finding("FAIL", "NO_QA_REGION", "-",
                           "Kein Slot als qa_region markiert — Gate 3a haette nichts zu pruefen"))

    return sorted(out, key=lambda f: (SEVERITY_ORDER[f.severity], f.slot))


def passed(findings: list[Finding]) -> bool:
    return not any(f.severity == "FAIL" for f in findings)
