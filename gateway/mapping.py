"""Anti-Corruption Layer: Fremdformat -> unser Modell.

Deklarativ statt in Code. Ein zweiter Partner ist eine zweite
Mapping-Datei, keine Codeaenderung - und das Fremdschema erreicht das
Kernmodell nie.

Unterstuetzte Operationen je Zielfeld:
    path        Punktpfad in die Quelle ("verein.name")
    const       fester Wert
    concat/sep  mehrere Quellfelder zusammensetzen
    map         Wertetabelle (z. B. "torwart" -> "KEEPER")
    lowercase   vor dem Mappen kleinschreiben
    default     Ersatz, wenn die Quelle nichts liefert
    as          Typumwandlung: string | integer | boolean
    object      verschachteltes Zielobjekt
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

TRUE_WORDS = {"true", "1", "ja", "yes", "y", "wahr"}
FALSE_WORDS = {"false", "0", "nein", "no", "n", "falsch"}


class MappingError(ValueError):
    pass


def dig(src: Any, dotted: str) -> Any:
    cur = src
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _cast(value: Any, kind: str | None, path: str) -> Any:
    if value is None or kind is None:
        return value
    try:
        if kind == "string":
            return value if isinstance(value, str) else str(value)
        if kind == "integer":
            return int(str(value).strip())
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in TRUE_WORDS:
                return True
            if text in FALSE_WORDS:
                return False
            raise ValueError(text)
    except (TypeError, ValueError) as exc:
        raise MappingError(f"{path}: {value!r} laesst sich nicht als {kind} lesen") from exc
    raise MappingError(f"{path}: unbekannte Umwandlung {kind!r}")


def apply_rule(src: Any, rule: dict, path: str = "") -> Any:
    if "object" in rule:
        built = {k: apply_rule(src, v, f"{path}.{k}")
                 for k, v in rule["object"].items()}
        # Ein Objekt, in dem nichts steht, wird weggelassen statt leer
        # durchgereicht - ein Spieler ohne Foto hat eben kein Foto.
        return None if all(v is None for v in built.values()) else built

    if "const" in rule:
        return rule["const"]

    if "concat" in rule:
        parts = [dig(src, p) for p in rule["concat"]]
        parts = [str(p).strip() for p in parts if p not in (None, "")]
        value: Any = rule.get("sep", " ").join(parts) if parts else None
    else:
        value = dig(src, rule["path"]) if "path" in rule else None

    if isinstance(value, str):
        value = value.strip() or None

    if value is not None and rule.get("lowercase"):
        value = str(value).lower()

    if "map" in rule and value is not None:
        value = rule["map"].get(str(value), rule.get("default"))

    if value is None:
        value = rule.get("default")

    return _cast(value, rule.get("as"), path or rule.get("path", "?"))


class Mapper:
    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.partner_code: str = mapping["partner_code"]
        self.payload_version: str = mapping["target_payload_version"]

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Mapper":
        return cls(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def _branch(self, src: Any, spec: dict, path: str) -> dict:
        out: dict[str, Any] = {}
        for key, rule in spec.items():
            child = f"{path}.{key}" if path else key
            if isinstance(rule, dict) and not (
                    rule.keys() & {"path", "const", "concat", "object"}):
                nested = self._branch(src, rule, child)   # reine Verschachtelung
                if nested:
                    out[key] = nested
            else:
                value = apply_rule(src, rule, child)
                if value is not None:
                    out[key] = value
        return out

    def to_payload(self, raw: dict) -> dict:
        order = self._branch(raw, self.mapping["order"], "order")

        pspec = self.mapping["players"]
        rows = dig(raw, pspec["path"]) or []
        if not isinstance(rows, list):
            raise MappingError(f"{pspec['path']} ist keine Liste")

        players = []
        for i, row in enumerate(rows):
            player = {}
            for key, rule in pspec["fields"].items():
                value = apply_rule(row, rule, f"players[{i}].{key}")
                if value is not None:
                    player[key] = value
            players.append(player)

        order["players"] = players
        return {"payload_version": self.payload_version, "order": order}
