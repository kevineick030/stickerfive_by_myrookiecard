"""Vertragspruefung ohne externe Bibliothek.

Prueft eine Nutzlast gegen die Teilmenge von JSON Schema, die
specs/partner_payload.v1.schema.json verwendet. Bewusst klein und lesbar:
Der Vertrag mit dem Partner ist zu wichtig, um von einer Abhaengigkeit
abzuhaengen, die irgendwann nicht mehr gepflegt wird.

Meldet ALLE Verstoesse, nicht nur den ersten - sonst schickt man dem
Partner zehn Mails statt einer.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any

TYPES = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool, "null": type(None),
}


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path or '<root>'}: {self.message}"


class Contract:
    def __init__(self, schema: dict):
        self.schema = schema
        self.defs = schema.get("$defs", {})

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Contract":
        return cls(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def validate(self, payload: Any) -> list[Violation]:
        out: list[Violation] = []
        self._check(payload, self.schema, "", out)
        return out

    # ------------------------------------------------------------------
    def _resolve(self, node: dict) -> dict:
        ref = node.get("$ref")
        if not ref:
            return node
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"Nicht unterstuetzte Referenz: {ref}")
        return self.defs[ref.split("/")[-1]]

    def _check(self, value: Any, node: dict, path: str, out: list[Violation]) -> None:
        node = self._resolve(node)

        expected = node.get("type")
        if expected is not None:
            allowed = [expected] if isinstance(expected, str) else expected
            # bool ist in Python ein int - fuer den Vertrag ist es das nicht.
            ok = any(
                (isinstance(value, bool) if t == "boolean"
                 else (isinstance(value, TYPES[t]) and not isinstance(value, bool))
                 if t in ("integer", "number")
                 else isinstance(value, TYPES[t]))
                for t in allowed)
            if not ok:
                out.append(Violation(path, f"erwartet {'/'.join(allowed)}, "
                                           f"bekommen {type(value).__name__}"))
                return

        if "enum" in node and value not in node["enum"]:
            allowed = ", ".join("null" if v is None else repr(v) for v in node["enum"])
            out.append(Violation(path, f"{value!r} ist nicht erlaubt (zulaessig: {allowed})"))

        if value is None:
            return

        if isinstance(value, str):
            if "minLength" in node and len(value) < node["minLength"]:
                out.append(Violation(path, f"kuerzer als {node['minLength']} Zeichen"))
            if "maxLength" in node and len(value) > node["maxLength"]:
                out.append(Violation(path, f"laenger als {node['maxLength']} Zeichen "
                                           f"(ist {len(value)})"))
            if "pattern" in node and not re.search(node["pattern"], value):
                out.append(Violation(path, f"entspricht nicht dem Muster {node['pattern']}"))

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in node and value < node["minimum"]:
                out.append(Violation(path, f"kleiner als {node['minimum']}"))
            if "maximum" in node and value > node["maximum"]:
                out.append(Violation(path, f"groesser als {node['maximum']}"))

        if isinstance(value, list):
            if "minItems" in node and len(value) < node["minItems"]:
                out.append(Violation(path, f"weniger als {node['minItems']} Eintraege"))
            if "maxItems" in node and len(value) > node["maxItems"]:
                out.append(Violation(path, f"mehr als {node['maxItems']} Eintraege"))
            if "items" in node:
                for i, item in enumerate(value):
                    self._check(item, node["items"], f"{path}[{i}]", out)

        if isinstance(value, dict):
            props = node.get("properties", {})
            for req in node.get("required", []):
                if req not in value:
                    out.append(Violation(f"{path}.{req}" if path else req, "Pflichtfeld fehlt"))
            if node.get("additionalProperties") is False:
                for key in value:
                    if key not in props:
                        out.append(Violation(f"{path}.{key}" if path else key,
                                             "unbekanntes Feld — bewusst abgelehnt, damit "
                                             "Fremdfelder nicht ins Kernmodell sickern"))
            for key, sub in props.items():
                if key in value:
                    self._check(value[key], sub, f"{path}.{key}" if path else key, out)


def validate_file(schema_path: str, payload_path: str) -> list[Violation]:
    return Contract.load(schema_path).validate(
        json.loads(pathlib.Path(payload_path).read_text(encoding="utf-8")))
