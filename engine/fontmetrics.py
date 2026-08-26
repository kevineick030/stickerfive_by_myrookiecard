"""Minimale TrueType-Metriken - ohne externe Abhaengigkeiten.

Gebraucht werden nur zwei Dinge, beide fuer Gate 1 unverzichtbar:

  * echte Vorschubbreiten, damit Autofit eine Messung ist und keine Schaetzung
  * Glyphabdeckung, damit ein fehlendes Zeichen (das klassische .notdef bei
    Namen wie "Dorde Dordevic" mit Đ und ć) VOR dem Druck auffaellt

Absichtlich kein Kerning und kein Shaping: der Renderer der Produktion setzt
den Text, diese Messung ist die konservative Obergrenze fuer die Pruefung.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MM_PER_PT = 25.4 / 72.0


@dataclass(frozen=True)
class Font:
    path: str
    units_per_em: int
    advances: dict[int, int]     # glyph id -> Vorschub in Font-Einheiten
    cmap: dict[int, int]         # codepoint -> glyph id
    default_advance: int
    # Versalhoehe aus OS/2 sCapHeight. Sie ist das Mass, an dem ein Setzer
    # ausrichtet - nicht die Em-Hoehe. Bei Versalsatz stehen sonst 27 %
    # leerer Oberlaengenraum ueber dem Text und alles sitzt zu tief.
    cap_height: int = 0

    def cap_height_mm(self, size_pt: float) -> float:
        ratio = (self.cap_height / self.units_per_em) if self.cap_height else 0.70
        return ratio * size_pt * MM_PER_PT

    def has_glyph(self, ch: str) -> bool:
        return ord(ch) in self.cmap

    def missing_glyphs(self, text: str) -> list[str]:
        """Zeichen ohne Glyph, in Reihenfolge und ohne Dubletten."""
        seen: dict[str, None] = {}
        for ch in text:
            if ch in ("\n", "\r"):
                continue
            if not self.has_glyph(ch):
                seen.setdefault(ch, None)
        return list(seen)

    def advance_em(self, ch: str) -> float:
        gid = self.cmap.get(ord(ch))
        adv = self.advances.get(gid, self.default_advance) if gid is not None else self.default_advance
        return adv / self.units_per_em

    def text_width_mm(self, text: str, size_pt: float, letter_spacing_em: float = 0.0) -> float:
        if not text:
            return 0.0
        em = sum(self.advance_em(c) for c in text)
        em += letter_spacing_em * max(len(text) - 1, 0)
        return em * size_pt * MM_PER_PT


def _tables(data: bytes) -> dict[str, tuple[int, int]]:
    if data[:4] == b"ttcf":
        offset = struct.unpack_from(">I", data, 12)[0]
    else:
        offset = 0
    num_tables = struct.unpack_from(">H", data, offset + 4)[0]
    out: dict[str, tuple[int, int]] = {}
    for i in range(num_tables):
        rec = offset + 12 + i * 16
        tag = data[rec:rec + 4].decode("latin-1")
        off, length = struct.unpack_from(">II", data, rec + 8)
        out[tag] = (off, length)
    return out


def _parse_cmap(data: bytes, offset: int) -> dict[int, int]:
    """Bevorzugt Format 12 (voller Unicode-Bereich), sonst Format 4 (BMP)."""
    num = struct.unpack_from(">H", data, offset + 2)[0]
    best: tuple[int, int] | None = None   # (rang, subtable-offset)
    for i in range(num):
        pid, eid, sub = struct.unpack_from(">HHI", data, offset + 4 + i * 8)
        rank = {(3, 10): 0, (0, 4): 0, (0, 6): 0,
                (3, 1): 1, (0, 3): 1, (0, 2): 1, (0, 1): 1}.get((pid, eid))
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, offset + sub)
    if best is None:
        return {}

    sub = best[1]
    fmt = struct.unpack_from(">H", data, sub)[0]
    cmap: dict[int, int] = {}

    if fmt == 4:
        seg_x2 = struct.unpack_from(">H", data, sub + 6)[0]
        seg = seg_x2 // 2
        ends = struct.unpack_from(f">{seg}H", data, sub + 14)
        starts = struct.unpack_from(f">{seg}H", data, sub + 16 + seg_x2)
        deltas = struct.unpack_from(f">{seg}h", data, sub + 16 + 2 * seg_x2)
        range_off_pos = sub + 16 + 3 * seg_x2
        range_offs = struct.unpack_from(f">{seg}H", data, range_off_pos)
        for i in range(seg):
            for cp in range(starts[i], min(ends[i], 0xFFFF) + 1):
                if range_offs[i] == 0:
                    gid = (cp + deltas[i]) & 0xFFFF
                else:
                    pos = range_off_pos + i * 2 + range_offs[i] + (cp - starts[i]) * 2
                    if pos + 2 > len(data):
                        continue
                    gid = struct.unpack_from(">H", data, pos)[0]
                    if gid:
                        gid = (gid + deltas[i]) & 0xFFFF
                if gid:
                    cmap[cp] = gid

    elif fmt == 12:
        n_groups = struct.unpack_from(">I", data, sub + 12)[0]
        for i in range(n_groups):
            start, end, start_gid = struct.unpack_from(">III", data, sub + 16 + i * 12)
            if end - start > 0x10000:      # unplausibel grosse Gruppe ueberspringen
                continue
            for cp in range(start, end + 1):
                cmap[cp] = start_gid + (cp - start)

    return cmap


def _cap_height(data: bytes, tabs: dict[str, tuple[int, int]]) -> int:
    """sCapHeight aus OS/2 Version 2 und hoeher; 0, wenn nicht vorhanden."""
    if "OS/2" not in tabs:
        return 0
    off, length = tabs["OS/2"]
    version = struct.unpack_from(">H", data, off)[0]
    if version < 2 or length < 90:
        return 0
    return struct.unpack_from(">h", data, off + 88)[0]


def load_font(path: str | Path) -> Font:
    data = Path(path).read_bytes()
    tabs = _tables(data)
    for required in ("head", "hhea", "hmtx", "cmap", "maxp"):
        if required not in tabs:
            raise ValueError(f"{path}: Tabelle {required} fehlt")

    units_per_em = struct.unpack_from(">H", data, tabs["head"][0] + 18)[0]
    num_h_metrics = struct.unpack_from(">H", data, tabs["hhea"][0] + 34)[0]
    num_glyphs = struct.unpack_from(">H", data, tabs["maxp"][0] + 4)[0]

    hmtx = tabs["hmtx"][0]
    advances: dict[int, int] = {}
    last = 0
    for gid in range(num_glyphs):
        if gid < num_h_metrics:
            last = struct.unpack_from(">H", data, hmtx + gid * 4)[0]
        advances[gid] = last

    return Font(
        path=str(path),
        units_per_em=units_per_em,
        advances=advances,
        cmap=_parse_cmap(data, tabs["cmap"][0]),
        default_advance=advances.get(0, units_per_em // 2),
        cap_height=_cap_height(data, tabs),
    )
