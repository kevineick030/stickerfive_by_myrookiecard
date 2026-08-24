"""Schicht B - deterministische Komposition.

Nimmt Slot-Schema, Kartendaten und die von Schicht A vermessenen Landmarks
und berechnet daraus das Render-Manifest: jede Platzierung mit Position,
Skalierung, tatsaechlicher Schriftgroesse nach Autofit und QR-Geometrie.

Reine Funktion: gleicher Input -> gleiches Manifest -> gleicher Fingerprint.
Keine Zufallswerte, keine Uhrzeit, keine Modellaufrufe.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any

from .fontmetrics import Font, MM_PER_PT

ENGINE_VERSION = "layout-1.0.0"

# QR Byte-Modus, Fehlerkorrektur Q: (Version, Modulkantenlaenge, Nutzlast in Byte)
QR_CAPACITY_ECC_Q: list[tuple[int, int, int]] = [
    (1, 21, 11), (2, 25, 20), (3, 29, 32), (4, 33, 46), (5, 37, 60),
    (6, 41, 74), (7, 45, 86), (8, 49, 108), (9, 53, 130), (10, 57, 151),
]


@dataclass
class Landmarks:
    """Von Schicht A gemessen, in Pixeln des Quellbilds."""
    eye_line_y: float
    head_top_y: float
    chin_y: float
    center_x: float

    @property
    def head_height(self) -> float:
        return self.chin_y - self.head_top_y


@dataclass
class PhotoAsset:
    content_hash: str
    width_px: int
    height_px: int
    landmarks: Landmarks | None = None      # None bei Gruppenfotos (fit_mode COVER)


@dataclass
class CardData:
    card_item_id: str
    copy_index: int
    player_name: str
    club_name: str
    season: str
    position_label: str
    public_token: str
    resolver_host: str
    jersey_number: str | None = None
    team_name: str | None = None
    stats: list[tuple[str, str]] = field(default_factory=list)
    legal_line: str = ""


class LayoutError(ValueError):
    """Das Layout laesst sich nicht deterministisch aufloesen."""


# --------------------------------------------------------------- Hilfsmittel

def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _round(value: float, digits: int = 4) -> float:
    """Auf feste Stellen runden, damit der Fingerprint plattformstabil bleibt."""
    return round(value + 0.0, digits)


def _apply_overrides(slot: dict, overrides: dict) -> dict:
    merged = dict(slot)
    merged.update(overrides.get(slot["id"], {}))
    return merged


def _transform_text(text: str, transform: str | None) -> str:
    return text.upper() if transform == "uppercase" else text


# --------------------------------------------------------------- Textsatz

def _wrap(text: str, font: Font, size_pt: float, width_mm: float,
          spacing: float, max_lines: int) -> list[str] | None:
    """Greedy-Umbruch. None, wenn der Text bei dieser Groesse nicht passt."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.text_width_mm(candidate, size_pt, spacing) <= width_mm:
            current = candidate
            continue
        if current:
            lines.append(current)
        # Ein einzelnes Wort, das allein schon zu breit ist, kann kein
        # Umbruch retten - nur eine kleinere Schrift.
        if font.text_width_mm(word, size_pt, spacing) > width_mm:
            return None
        current = word
        if len(lines) >= max_lines:
            return None
    lines.append(current)
    return lines if len(lines) <= max_lines else None


def _fit_text(text: str, font: Font, slot: dict) -> dict:
    """Sucht die groesste Schriftgroesse, bei der der Text in die Box passt."""
    box = slot["box"]
    size = float(slot["size_pt"])
    min_size = float(slot.get("min_size_pt", size))
    spacing = float(slot.get("letter_spacing_em", 0.0))
    max_lines = int(slot.get("max_lines", 1))
    line_height = 1.16

    step = 0.25
    while size >= min_size - 1e-9:
        lines = _wrap(text, font, size, box["w"], spacing, max_lines)
        if lines is not None:
            block_h = len(lines) * size * MM_PER_PT * line_height
            if block_h <= box["h"] + 1e-9:
                return {
                    "lines": lines,
                    "size_pt": _round(size, 2),
                    "autofit_applied": size < float(slot["size_pt"]) - 1e-9,
                    "measured_width_mm": _round(
                        max(font.text_width_mm(l, size, spacing) for l in lines)),
                    "block_height_mm": _round(block_h),
                }
        size -= step

    # Auch bei min_size_pt passt es nicht: Gate 1 muss das sehen, nicht der Drucker.
    lines = _wrap(text, font, min_size, box["w"], spacing, max_lines) or [text]
    return {
        "lines": lines,
        "size_pt": _round(min_size, 2),
        "autofit_applied": True,
        "overflow": True,
        "measured_width_mm": _round(
            max(font.text_width_mm(l, min_size, spacing) for l in lines)),
        "block_height_mm": _round(len(lines) * min_size * MM_PER_PT * line_height),
    }


# --------------------------------------------------------------- Bildanker

def coverage_scale(slot: dict, photo: PhotoAsset) -> float:
    """Kleinste Skalierung, bei der das Bild den Slot noch vollstaendig deckt.

    Haengt nicht nur von der Bildgroesse ab, sondern auch davon, wie viel
    Bild links, rechts, ueber und unter dem Kopf liegt - denn die Anker
    legen fest, WO der Kopf landet.
    """
    lm, box, a = photo.landmarks, slot["box"], slot["anchors"]
    cx, eye = lm.center_x, lm.eye_line_y
    return max(
        a["center_x_ratio"] * box["w"] / max(cx, 1e-9),                             # links
        box["w"] * (1 - a["center_x_ratio"]) / max(photo.width_px - cx, 1e-9),      # rechts
        a["eye_line_ratio"] * box["h"] / max(eye, 1e-9),                            # oben
        box["h"] * (1 - a["eye_line_ratio"]) / max(photo.height_px - eye, 1e-9),    # unten
    )


def _place_photo_anchor(slot: dict, photo: PhotoAsset) -> dict:
    """Die Ankerregel: Augenlinie und Kopfhoehe bestimmen Skalierung und Versatz.

    Der Grund, warum 60 unterschiedlich geschnittene Handyfotos wie ein Set
    aussehen und nicht wie 60 Zufaelle.

    Deckt das Bild bei der Anker-Skalierung den Slot nicht ab - weil zu eng
    um den Kopf herum fotografiert wurde -, wird so weit aufskaliert, dass es
    deckt. Der Kopf wird dadurch etwas groesser als das Ziel; wie weit das
    gehen darf, steht als coverage_scale_tolerance im Slot. Die Augenlinie
    bleibt in jedem Fall exakt auf ihrem Anker, damit das Set zusammenhaelt.
    """
    lm = photo.landmarks
    if lm is None:
        raise LayoutError("fit_mode ANCHOR ohne Landmarks aus Schicht A")
    if lm.head_height <= 0:
        raise LayoutError("unplausible Landmarks: Kinn liegt nicht unter der Kopfoberkante")

    box, anchors = slot["box"], slot["anchors"]
    tolerance = float(slot.get("coverage_scale_tolerance", 0.15))

    scale_anchor = (anchors["head_height_ratio"] * box["h"]) / lm.head_height
    scale_needed = coverage_scale(slot, photo)
    adjusted = scale_needed > scale_anchor * (1 + 1e-9)
    scale = max(scale_anchor, scale_needed)

    dx = box["x"] + anchors["center_x_ratio"] * box["w"] - lm.center_x * scale
    dy = box["y"] + anchors["eye_line_ratio"] * box["h"] - lm.eye_line_y * scale

    img_w, img_h = photo.width_px * scale, photo.height_px * scale
    head_ratio = lm.head_height * scale / box["h"]
    deviation = head_ratio / anchors["head_height_ratio"] - 1.0

    return {
        "fit_mode": "ANCHOR",
        "asset_hash": photo.content_hash,
        "source_px": [photo.width_px, photo.height_px],
        "landmarks_px": asdict(lm),
        "scale_mm_per_px": _round(scale, 6),
        "scale_from_anchor": _round(scale_anchor, 6),
        "scale_adjusted_for_coverage": adjusted,
        "head_ratio_deviation": _round(deviation, 4),
        "coverage_scale_tolerance": tolerance,
        "offset_mm": [_round(dx), _round(dy)],
        "placed_size_mm": [_round(img_w), _round(img_h)],
        # Skalieren nach unten erhoeht die effektive Aufloesung, nach oben senkt sie sie.
        "effective_dpi": _round(25.4 / scale, 1),
        "covers_slot": True,
        "head_top_mm": _round(dy + lm.head_top_y * scale),
        "chin_mm": _round(dy + lm.chin_y * scale),
        "resulting_eye_line_ratio": _round(
            (dy + lm.eye_line_y * scale - box["y"]) / box["h"]),
        "resulting_head_height_ratio": _round(head_ratio),
    }


def _place_photo_cover(slot: dict, photo: PhotoAsset) -> dict:
    """Fuer Gruppenfotos: fuellt den Slot, ohne Kopfgeometrie."""
    box = slot["box"]
    scale = max(box["w"] / photo.width_px, box["h"] / photo.height_px)
    img_w, img_h = photo.width_px * scale, photo.height_px * scale
    dx = box["x"] + (box["w"] - img_w) / 2
    dy = box["y"] + (box["h"] - img_h) / 2
    return {
        "fit_mode": "COVER",
        "asset_hash": photo.content_hash,
        "source_px": [photo.width_px, photo.height_px],
        "scale_mm_per_px": _round(scale, 6),
        "offset_mm": [_round(dx), _round(dy)],
        "placed_size_mm": [_round(img_w), _round(img_h)],
        "effective_dpi": _round(25.4 / scale, 1),
        "covers_slot": True,
    }


# --------------------------------------------------------------- QR

def qr_plan(payload: str, slot: dict) -> dict:
    """Waehlt die kleinste QR-Version, die die Nutzlast traegt, und rechnet
    die Modulgroesse aus. Das entscheidet, wie lang der Resolver-Host sein darf.
    """
    payload_bytes = len(payload.encode("utf-8"))
    box = slot["box"]
    side_mm = min(box["w"], box["h"])
    quiet = int(slot.get("quiet_zone_modules", 4))
    min_module = float(slot.get("min_module_mm", 0.40))

    chosen = None
    for version, modules, capacity in QR_CAPACITY_ECC_Q:
        if payload_bytes > capacity:
            continue
        module_mm = side_mm / (modules + 2 * quiet)
        chosen = {
            "version": version, "modules": modules, "capacity_bytes": capacity,
            "module_mm": _round(module_mm, 4),
            "module_ok": module_mm >= min_module,
        }
        break

    # Groesste Nutzlast, die bei dieser Boxgroesse noch gross genug gedruckt wird
    budget = 0
    for version, modules, capacity in QR_CAPACITY_ECC_Q:
        if side_mm / (modules + 2 * quiet) >= min_module:
            budget = capacity
    return {
        "payload": payload,
        "payload_bytes": payload_bytes,
        "ecc": slot.get("error_correction", "Q"),
        "box_mm": box,
        "quiet_zone_modules": quiet,
        "min_module_mm": min_module,
        "payload_budget_bytes": budget,
        **(chosen or {"version": None, "modules": None, "module_ok": False,
                      "capacity_bytes": 0, "module_mm": None}),
    }


# --------------------------------------------------------------- Manifest

def build_manifest(schema: dict, family: dict, card: CardData,
                   photo: PhotoAsset, fonts: dict[str, Font],
                   design_version: str) -> dict:
    overrides = family.get("slot_overrides", {})
    geo = schema["geometry"]

    sources: dict[str, str] = {
        "person.display_name": card.player_name,
        "person.jersey_number": card.jersey_number or "",
        "person.role_label": card.position_label,
        "club.name": card.club_name,
        "team.season": card.season,
        "team.name": card.team_name or card.club_name,
        "club.name + ' · ' + team.season": f"{card.club_name} · {card.season}",
        "config.legal_line": card.legal_line,
    }

    def place_side(side: str) -> list[dict]:
        out: list[dict] = []
        for raw in schema[side]["slots"]:
            slot = _apply_overrides(raw, overrides)
            if slot.get("hidden"):
                continue
            kind, sid = slot["type"], slot["id"]

            if kind == "image":
                if sid == "photo":
                    placed = (_place_photo_anchor(slot, photo)
                              if slot.get("fit_mode", "ANCHOR") == "ANCHOR"
                              else _place_photo_cover(slot, photo))
                    out.append({"slot": sid, "type": "image", "box_mm": slot["box"],
                                "required": slot.get("required", False), **placed})
                continue    # Logo und Sponsor kommen aus dem Vereinskontext

            if kind == "qr":
                host = card.resolver_host
                payload = slot["url_pattern"].format(resolver_host=host, token=card.public_token)
                out.append({"slot": sid, "type": "qr",
                            "required": slot.get("required", False),
                            **qr_plan(payload, slot)})
                continue

            if kind == "keyvalue":
                rows = card.stats[: int(slot.get("max_rows", 4))]
                if not rows and not slot.get("required", False):
                    continue
                out.append({"slot": sid, "type": "keyvalue", "box_mm": slot["box"],
                            "rows": [list(r) for r in rows],
                            "size_pt": slot["size_pt"],
                            "required": slot.get("required", False)})
                continue

            # Text
            text = slot.get("static_text_de") or sources.get(slot.get("source", ""), "")
            text = _transform_text(text, slot.get("transform"))
            if not text:
                if slot.get("required", False):
                    out.append({"slot": sid, "type": "text", "box_mm": slot["box"],
                                "text": "", "required": True, "empty": True,
                                "size_pt": slot["size_pt"], "lines": [],
                                "min_size_pt": slot.get("min_size_pt", slot["size_pt"])})
                continue

            font = fonts[slot.get("font", "body")]
            fitted = _fit_text(text, font, slot)
            # Grundlinien und Ausrichtungspunkt mitgeben, damit Vorschau und
            # Produktionsrenderer denselben Satz erzeugen und nicht jeder seinen.
            size_mm = fitted["size_pt"] * MM_PER_PT
            box = slot["box"]
            align = slot.get("align", "left")
            fitted["baselines_mm"] = [
                _round(box["y"] + size_mm * 0.80 + i * size_mm * 1.16)
                for i in range(len(fitted["lines"]))]
            fitted["anchor_x_mm"] = _round(
                box["x"] if align == "left"
                else box["x"] + box["w"] if align == "right"
                else box["x"] + box["w"] / 2)
            out.append({
                "slot": sid, "type": "text", "box_mm": slot["box"], "text": text,
                "font": slot.get("font", "body"),
                "align": slot.get("align", "left"),
                "letter_spacing_em": slot.get("letter_spacing_em", 0.0),
                "min_size_pt": slot.get("min_size_pt", slot["size_pt"]),
                "declared_size_pt": slot["size_pt"],
                "qa_region": slot.get("qa_region", False),
                "required": slot.get("required", False),
                "missing_glyphs": font.missing_glyphs(text),
                **fitted,
            })
        return out

    front = place_side("front")
    back = place_side("back")

    front_fp = _sha256(_canonical({"design_version": design_version,
                                   "schema": f'{schema["id"]}@{schema["version"]}',
                                   "engine": ENGINE_VERSION, "placements": front}))
    back_fp = _sha256(_canonical({"design_version": design_version,
                                  "engine": ENGINE_VERSION, "placements": back}))

    return {
        "manifest_version": "1.0.0",
        "engine_version": ENGINE_VERSION,
        "card": {
            "card_item_id": card.card_item_id,
            "copy_index": card.copy_index,
            "design_family": family["id"],
            "design_version": design_version,
            "slot_schema": f'{schema["id"]}@{schema["version"]}',
            "print_spec": family["print_spec"],
            "public_token": card.public_token,
        },
        "geometry": geo,
        # Die Vorderseite ist bei allen Kopien identisch - nur die Rueckseite
        # traegt den kopieeigenen QR-Token. Deshalb zwei getrennte Fingerprints:
        # der teure Teil wird genau einmal gerendert und einmal geprueft.
        "front": {"fingerprint": front_fp, "placements": front},
        "back": {"fingerprint": back_fp, "placements": back},
        "fingerprint": _sha256(front_fp + back_fp),
    }
