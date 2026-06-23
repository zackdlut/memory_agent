"""Persona memory = a SQLite-backed model of each person.

Stores a weighted view of traits / preferences plus behavior patterns and a
mention count. This is the "long-term model of a person" the agent uses to
understand and predict them.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time

from app.config import settings
from app.schemas import BehaviorPattern, Persona


class PersonaMemory:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personas (
                name TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # ---------------------------------------------------------------- writes
    def get(self, name: str) -> Persona | None:
        row = self._conn.execute(
            "SELECT data FROM personas WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return Persona(**json.loads(row["data"]))
        # alias lookup
        for p in self.all():
            if name in p.aliases:
                return p
        return None

    def get_exact(self, name: str) -> Persona | None:
        """Fetch strictly by primary-key name (no alias fallback)."""
        row = self._conn.execute(
            "SELECT data FROM personas WHERE name = ?", (name,)
        ).fetchone()
        return Persona(**json.loads(row["data"])) if row else None

    def delete(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM personas WHERE name = ?", (name,))
            self._conn.commit()

    def _save(self, persona: Persona) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO personas (name, data) VALUES (?, ?)",
            (persona.name, persona.model_dump_json()),
        )
        self._conn.commit()

    def upsert(
        self,
        name: str,
        *,
        aliases: list[str] | None = None,
        traits: list[str] | None = None,
        preferences: list[str] | None = None,
        patterns: list[BehaviorPattern] | None = None,
        trait_gain: float = 0.3,
        pref_gain: float = 0.3,
    ) -> Persona:
        with self._lock:
            persona = self.get(name) or Persona(name=name)
            persona.mention_count += 1
            persona.last_seen = time.time()
            if aliases:
                persona.aliases = sorted(set(persona.aliases) | set(aliases))
            for t in traits or []:
                persona.traits[t] = round(persona.traits.get(t, 0.0) + trait_gain, 4)
            for pref in preferences or []:
                persona.preferences[pref] = round(
                    persona.preferences.get(pref, 0.0) + pref_gain, 4
                )
            for pat in patterns or []:
                if not any(
                    p.trigger == pat.trigger and p.behavior == pat.behavior
                    for p in persona.patterns
                ):
                    persona.patterns.append(pat)
            self._save(persona)
            return persona

    def regenerate_summary(self, name: str, summary: str) -> None:
        with self._lock:
            persona = self.get(name)
            if persona:
                persona.summary = summary
                persona.last_summary_at = time.time()
                self._save(persona)

    def update(
        self,
        name: str,
        *,
        summary: str | None = None,
        remove_traits: list[str] | None = None,
        remove_preferences: list[str] | None = None,
        remove_pattern_indices: list[int] | None = None,
        add_aliases: list[str] | None = None,
    ) -> Persona | None:
        with self._lock:
            persona = self.get(name)
            if persona is None:
                return None
            if summary is not None:
                persona.summary = summary
                persona.last_summary_at = time.time()
            for t in remove_traits or []:
                persona.traits.pop(t, None)
            for pref in remove_preferences or []:
                persona.preferences.pop(pref, None)
            if remove_pattern_indices:
                drop = set(remove_pattern_indices)
                persona.patterns = [
                    pat for i, pat in enumerate(persona.patterns) if i not in drop
                ]
            if add_aliases:
                persona.aliases = sorted(set(persona.aliases) | set(add_aliases))
            self._save(persona)
            return persona

    def merge(self, source: str, target: str) -> Persona | None:
        """Fold the ``source`` persona into ``target`` and delete the source."""
        with self._lock:
            if source == target:
                return self.get_exact(target)
            ps = self.get_exact(source)
            pt = self.get_exact(target)
            if ps is None or pt is None:
                return pt
            for k, v in ps.traits.items():
                pt.traits[k] = round(pt.traits.get(k, 0.0) + v, 4)
            for k, v in ps.preferences.items():
                pt.preferences[k] = round(pt.preferences.get(k, 0.0) + v, 4)
            pt.aliases = sorted(set(pt.aliases) | set(ps.aliases) | {ps.name})
            for pat in ps.patterns:
                if not any(
                    p.trigger == pat.trigger and p.behavior == pat.behavior
                    for p in pt.patterns
                ):
                    pt.patterns.append(pat)
            pt.mention_count += ps.mention_count
            pt.last_seen = max(pt.last_seen, ps.last_seen)
            self._save(pt)
            self._conn.execute("DELETE FROM personas WHERE name = ?", (ps.name,))
            self._conn.commit()
            return pt

    def decay(self, factor: float) -> None:
        with self._lock:
            for persona in self.all():
                persona.traits = {k: round(v * factor, 4) for k, v in persona.traits.items()}
                persona.preferences = {
                    k: round(v * factor, 4) for k, v in persona.preferences.items()
                }
                self._save(persona)

    # ----------------------------------------------------------------- reads
    def all(self) -> list[Persona]:
        rows = self._conn.execute("SELECT data FROM personas").fetchall()
        return [Persona(**json.loads(r["data"])) for r in rows]

    def names(self) -> list[str]:
        return [r["name"] for r in self._conn.execute("SELECT name FROM personas").fetchall()]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM personas").fetchone()["c"]
