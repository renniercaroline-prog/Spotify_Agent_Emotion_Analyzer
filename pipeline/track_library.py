"""Shared scored-track library — a global cache so each unique track is fetched +
GEMS-scored only ONCE across all users (the core API-cost saver).

v1 backend: a single SQLite file (swap for Postgres later behind this interface).
Key = normalized lower(artist)|||lower(track); spotify_uri stored when known and
resolvable to the same record. Stores lyrics, has_lyrics, the 45 gems_<item>
scores, the 9 gems_cluster_<name> averages, plus provenance (source, model,
prompt version, timestamp). Never stores user identity — this is track data.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time

import pandas as pd

from gems import CLUSTER_COLS, ITEM_COLS, SCORING_MODEL, normalize_key

_SCORE_COLS = ITEM_COLS + CLUSTER_COLS
_BASE_COLS = ["key", "artist", "track", "spotify_uri", "lyrics", "has_lyrics"]
_META_COLS = ["source", "model", "prompt_version", "scored_at"]
_ALL_COLS = _BASE_COLS + _SCORE_COLS + _META_COLS


class TrackLibrary:
    """Thread-safe lookup/upsert over the scored-track store."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create()

    def _create(self):
        cols_sql = ",\n".join(
            [f'"{c}" REAL' for c in _SCORE_COLS]
        )
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tracks (
                key TEXT PRIMARY KEY,
                artist TEXT, track TEXT, spotify_uri TEXT,
                lyrics TEXT, has_lyrics INTEGER,
                {cols_sql},
                source TEXT, model TEXT, prompt_version TEXT, scored_at REAL
            )""")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uri ON tracks(spotify_uri)")
        self._conn.commit()

    # ---- reads ----
    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM tracks")
        return cur.fetchone()["n"]

    def lookup(self, keys: list[str]) -> dict[str, dict]:
        """Return {key: row_dict} for keys already in the library."""
        out = {}
        if not keys:
            return out
        with self._lock:
            # chunk to stay under SQLite's variable limit
            for i in range(0, len(keys), 800):
                chunk = keys[i:i + 800]
                q = (f"SELECT * FROM tracks WHERE key IN "
                     f"({','.join('?' * len(chunk))})")
                for r in self._conn.execute(q, chunk).fetchall():
                    out[r["key"]] = dict(r)
        return out

    # ---- writes ----
    def upsert(self, record: dict):
        """Insert or replace one track record (record may omit unknown cols)."""
        row = {c: record.get(c) for c in _ALL_COLS}
        row["scored_at"] = row.get("scored_at") or time.time()
        cols = ",".join(f'"{c}"' for c in _ALL_COLS)
        ph = ",".join("?" * len(_ALL_COLS))
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO tracks ({cols}) VALUES ({ph})",
                [row[c] for c in _ALL_COLS])
            self._conn.commit()

    def upsert_many(self, records: list[dict]):
        for r in records:
            self.upsert(r)

    def to_gems_frame(self, keys: list[str]) -> pd.DataFrame:
        """Return a DataFrame (analysis-engine schema) for the given track keys."""
        rows = self.lookup(keys)
        if not rows:
            return pd.DataFrame(columns=_BASE_COLS + _SCORE_COLS)
        df = pd.DataFrame(list(rows.values()))
        for c in _BASE_COLS + _SCORE_COLS:
            if c not in df.columns:
                df[c] = None
        return df


def seed_from_csv(lib: TrackLibrary, csv_path: str, source="seed:anna") -> int:
    """One-time seed of the library from a pre-scored CSV (e.g. Anna's tracks).
    Skips tracks already present. Returns number of new rows added."""
    df = pd.read_csv(csv_path)
    existing = set()
    cur = lib._conn.execute("SELECT key FROM tracks")
    existing = {r["key"] for r in cur.fetchall()}
    added = 0
    for r in df.to_dict("records"):
        key = normalize_key(r.get("artist"), r.get("track"))
        if key in existing:
            continue
        rec = {"key": key, "artist": r.get("artist"), "track": r.get("track"),
               "spotify_uri": r.get("spotify_uri"), "lyrics": r.get("lyrics"),
               "has_lyrics": int(bool(r.get("has_lyrics"))),
               "source": source, "model": SCORING_MODEL,
               "prompt_version": "seed", "scored_at": time.time()}
        for c in _SCORE_COLS:
            v = r.get(c)
            rec[c] = float(v) if pd.notna(v) else None
        lib.upsert(rec)
        added += 1
    return added
