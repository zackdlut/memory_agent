"""Episodic memory = FAISS vector store + SQLite metadata.

Maps the human "episodic memory" (events tied to time & people). Each episode
is embedded and added to a FAISS inner-product index over L2-normalised
vectors (so inner product == cosine similarity). Episode records live in
SQLite, with a ``faiss_row`` column linking back to the index row order, which
lets us rebuild the row->id mapping deterministically on startup.
"""

from __future__ import annotations

import json
import sqlite3
import threading

import faiss
import numpy as np

from app.config import settings
from app.llm import llm
from app.schemas import Episode


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


class EpisodicMemory:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.dim = settings.embed_dim
        self.index = faiss.IndexFlatIP(self.dim)
        self._row_ids: list[str] = []  # faiss row -> episode id
        self._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._load()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                faiss_row INTEGER,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _load(self) -> None:
        if settings.faiss_index_path.exists():
            try:
                self.index = faiss.read_index(str(settings.faiss_index_path))
            except Exception:
                self.index = faiss.IndexFlatIP(self.dim)
        rows = self._conn.execute(
            "SELECT id FROM episodes WHERE faiss_row IS NOT NULL ORDER BY faiss_row ASC"
        ).fetchall()
        self._row_ids = [r["id"] for r in rows]
        # if the index and mapping diverged, rebuild from scratch
        if self.index.ntotal != len(self._row_ids):
            self._rebuild()

    def _rebuild(self) -> None:
        self.index = faiss.IndexFlatIP(self.dim)
        self._row_ids = []
        rows = self._conn.execute("SELECT id, data FROM episodes ORDER BY rowid ASC").fetchall()
        for r in rows:
            ep = Episode(**json.loads(r["data"]))
            self._add_vector(ep)
        self._persist_index()

    # ---------------------------------------------------------------- writes
    def _add_vector(self, episode: Episode) -> int:
        text = episode.summary or episode.text
        vec = np.asarray(llm.embed(text), dtype="float32")
        vec = _normalize(vec).reshape(1, -1)
        row = self.index.ntotal
        self.index.add(vec)
        self._row_ids.append(episode.id)
        return row

    def add(self, episode: Episode) -> Episode:
        with self._lock:
            row = self._add_vector(episode)
            self._conn.execute(
                "INSERT OR REPLACE INTO episodes (id, faiss_row, data) VALUES (?, ?, ?)",
                (episode.id, row, episode.model_dump_json()),
            )
            self._conn.commit()
            self._persist_index()
            return episode

    def update(self, episode: Episode) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE episodes SET data = ? WHERE id = ?",
                (episode.model_dump_json(), episode.id),
            )
            self._conn.commit()

    def _persist_index(self) -> None:
        try:
            faiss.write_index(self.index, str(settings.faiss_index_path))
        except Exception:
            pass

    # ----------------------------------------------------------------- reads
    def get(self, episode_id: str) -> Episode | None:
        row = self._conn.execute(
            "SELECT data FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        return Episode(**json.loads(row["data"])) if row else None

    def all(self) -> list[Episode]:
        rows = self._conn.execute("SELECT data FROM episodes ORDER BY rowid DESC").fetchall()
        return [Episode(**json.loads(r["data"])) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM episodes").fetchone()["c"]

    def search(self, query: str, top_k: int = 8) -> list[tuple[Episode, float]]:
        with self._lock:
            if self.index.ntotal != self.count():
                self._rebuild()
            if self.index.ntotal == 0:
                return []
            vec = np.asarray(llm.embed(query), dtype="float32")
            vec = _normalize(vec).reshape(1, -1)
            k = min(top_k, self.index.ntotal)
            scores, idxs = self.index.search(vec, k)
        out: list[tuple[Episode, float]] = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0 or idx >= len(self._row_ids):
                continue
            ep = self.get(self._row_ids[idx])
            if ep:
                out.append((ep, float(score)))
        return out

    def decay(self, factor: float) -> None:
        with self._lock:
            for ep in self.all():
                ep.weight = round(ep.weight * factor, 4)
                self._conn.execute(
                    "UPDATE episodes SET data = ? WHERE id = ?",
                    (ep.model_dump_json(), ep.id),
                )
            self._conn.commit()

    def prune(self, min_weight: float) -> int:
        with self._lock:
            to_delete = [ep.id for ep in self.all() if ep.weight < min_weight]
            for eid in to_delete:
                self._conn.execute("DELETE FROM episodes WHERE id = ?", (eid,))
            self._conn.commit()
            if to_delete:
                self._rebuild()
            return len(to_delete)
