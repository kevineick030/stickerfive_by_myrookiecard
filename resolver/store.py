"""Datenzugriff des Aufloesungsdienstes.

Der Dienst kennt nur diese schmale Schnittstelle. Das ist Absicht: Er soll
noch laufen, wenn die Engine dreimal umgebaut wurde - also darf er nichts
ueber ihr Innenleben wissen.

PsqlStore ruft psql als Unterprozess auf, weil in dieser Umgebung kein
Datenbanktreiber installiert ist. In Produktion wird genau diese Klasse
gegen einen echten Treiber getauscht; der Rest des Dienstes bleibt gleich.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol

# Jeder Token wird VOR jedem Datenbankkontakt hiergegen geprueft. Damit kann
# aus einer URL nichts in eine Abfrage geraten, was dort nicht hingehoert.
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{12,48}$")

GONE = {"status": "GONE"}


def token_is_wellformed(token: str) -> bool:
    return bool(TOKEN_RE.match(token or ""))


class TwinStore(Protocol):
    def resolve(self, token: str) -> dict: ...
    def manifest(self, fingerprint: str) -> dict | None: ...


@dataclass
class InMemoryStore:
    """Fuer Tests und die oertliche Vorfuehrung."""
    twins: dict[str, dict]
    manifests: dict[str, dict]

    def resolve(self, token: str) -> dict:
        if not token_is_wellformed(token):
            return dict(GONE)
        entry = self.twins.get(token)
        if entry is None or entry.get("status") != "OK":
            return dict(GONE)
        self.scans = getattr(self, "scans", {})
        self.scans[token] = self.scans.get(token, 0) + 1
        return dict(entry)

    def manifest(self, fingerprint: str) -> dict | None:
        return self.manifests.get(fingerprint)


class PsqlStore:
    """Ruft die Aufloesung in der Datenbank auf.

    Die gesamte Logik - unbekannt, widerrufen und noch nicht gedruckt sehen
    von aussen gleich aus - steckt in resolve_twin(). Der Dienst entscheidet
    darueber nichts selbst.
    """

    def __init__(self, dsn_env: dict[str, str] | None = None, psql: str = "psql"):
        self.env = dsn_env or {}
        self.psql = psql

    def _query(self, sql: str, **params: str) -> str:
        # Abfrage ueber stdin, damit psql die Variablen selbst quotet. Der
        # Token ist ausserdem schon gegen TOKEN_RE geprueft - zwei Schranken
        # statt einer.
        cmd = [self.psql, "-tAq", "-v", "ON_ERROR_STOP=1"]
        for key, value in params.items():
            cmd += ["-v", f"{key}={value}"]
        import os
        env = {**os.environ, **self.env}
        done = subprocess.run(cmd, input=sql, capture_output=True, text=True,
                              env=env, timeout=10)
        if done.returncode != 0:
            raise RuntimeError(done.stderr.strip()[:400])
        return done.stdout.strip()

    def resolve(self, token: str) -> dict:
        if not token_is_wellformed(token):
            return dict(GONE)
        try:
            raw = self._query("select resolve_twin(:'tok')", tok=token)
        except Exception:
            # Ein Datenbankfehler darf nicht verraten, ob es den Token gibt.
            return dict(GONE)
        return json.loads(raw) if raw else dict(GONE)

    def manifest(self, fingerprint: str) -> dict | None:
        if not re.match(r"^[0-9a-f]{64}$", fingerprint or ""):
            return None
        try:
            raw = self._query(
                "select manifest from render_artifact where fingerprint = :'fp'", fp=fingerprint)
        except Exception:
            return None
        return json.loads(raw) if raw else None
