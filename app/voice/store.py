"""SQLite-backed store of per-person voiceprints (speaker embeddings).

Each person keeps a single running-mean embedding (L2-normalised) so the model
of their voice strengthens with every utterance. Only the embedding vector is
persisted -- raw audio is never stored.

Reuses the same ``memory.db`` as the rest of the system.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import numpy as np

from app.config import settings


def _normalize(vec: np.ndarray) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr


class VoiceprintStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS voiceprints (
                person TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                dim INTEGER NOT NULL,
                count INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    # ----------------------------------------------------------------- reads
    def get(self, person: str) -> np.ndarray | None:
        row = self._conn.execute(
            "SELECT embedding, dim FROM voiceprints WHERE person = ?", (person,)
        ).fetchone()
        if not row:
            return None
        return np.frombuffer(row["embedding"], dtype=np.float32).reshape(row["dim"])

    def all(self) -> list[tuple[str, np.ndarray, int]]:
        rows = self._conn.execute(
            "SELECT person, embedding, dim, count FROM voiceprints"
        ).fetchall()
        out: list[tuple[str, np.ndarray, int]] = []
        for r in rows:
            emb = np.frombuffer(r["embedding"], dtype=np.float32).reshape(r["dim"])
            out.append((r["person"], emb, r["count"]))
        return out

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM voiceprints").fetchone()["c"]

    # ---------------------------------------------------------------- writes
    def enroll(self, person: str, emb: np.ndarray) -> None:
        """Fold a new utterance embedding into the person's running mean."""
        if not person:
            return
        new = _normalize(emb)
        with self._lock:
            existing = self.get(person)
            row = self._conn.execute(
                "SELECT count FROM voiceprints WHERE person = ?", (person,)
            ).fetchone()
            if existing is not None and row is not None:
                count = int(row["count"])
                merged = _normalize(existing * count + new)
                count += 1
            else:
                merged = new
                count = 1
            self._save(person, merged, count)

    def _save(self, person: str, emb: np.ndarray, count: int) -> None:
        arr = _normalize(emb)
        self._conn.execute(
            "INSERT OR REPLACE INTO voiceprints (person, embedding, dim, count, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (person, arr.astype(np.float32).tobytes(), int(arr.shape[0]), int(count), time.time()),
        )
        self._conn.commit()

    def match(self, emb: np.ndarray) -> list[tuple[str, float]]:
        """Return (person, cosine-similarity) sorted by similarity desc."""
        query = _normalize(emb)
        scored: list[tuple[str, float]] = []
        for person, stored, _count in self.all():
            if stored.shape != query.shape:
                continue
            score = float(np.dot(query, _normalize(stored)))
            scored.append((person, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def delete(self, person: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM voiceprints WHERE person = ?", (person,))
            self._conn.commit()

    def merge(self, source: str, target: str) -> None:
        """Fold the ``source`` voiceprint into ``target`` and drop the source.

        Used when two personas are merged so the voiceprint follows the person.
        """
        if not source or not target or source == target:
            return
        with self._lock:
            src = self.get(source)
            if src is None:
                return
            src_row = self._conn.execute(
                "SELECT count FROM voiceprints WHERE person = ?", (source,)
            ).fetchone()
            src_count = int(src_row["count"]) if src_row else 1
            tgt = self.get(target)
            tgt_row = self._conn.execute(
                "SELECT count FROM voiceprints WHERE person = ?", (target,)
            ).fetchone()
            if tgt is not None and tgt_row is not None:
                tgt_count = int(tgt_row["count"])
                merged = _normalize(tgt * tgt_count + src * src_count)
                self._save(target, merged, tgt_count + src_count)
            else:
                self._save(target, src, src_count)
            self._conn.execute("DELETE FROM voiceprints WHERE person = ?", (source,))
            self._conn.commit()

    def rename(self, source: str, target: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE OR REPLACE voiceprints SET person = ? WHERE person = ?",
                (target, source),
            )
            self._conn.commit()
