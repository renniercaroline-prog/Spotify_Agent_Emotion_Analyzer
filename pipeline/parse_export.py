"""Parse an uploaded Spotify data export (zip) into a per-play history DataFrame
matching the analysis engine's schema, plus the unique-tracks table.

Handles both export shapes:
  - Basic "Account data": StreamingHistory_music_*.json
        {endTime, artistName, trackName, msPlayed}
  - Extended streaming history: endsong_*.json / Streaming_History_Audio_*.json
        {ts, ms_played, master_metadata_track_name,
         master_metadata_album_artist_name, spotify_track_uri}
Podcast/audiobook files are ignored.
"""
from __future__ import annotations

import io
import json
import zipfile

import pandas as pd

from gems import normalize_key

HISTORY_COLS = ["end_time", "date", "time", "day_of_week", "hour",
                "artist", "track", "ms_played", "minutes_played", "spotify_uri"]


def _is_music_basic(name: str) -> bool:
    n = name.lower()
    return "streaminghistory_music" in n and n.endswith(".json")


def _is_extended(name: str) -> bool:
    n = name.lower().rsplit("/", 1)[-1]
    return (n.endswith(".json")
            and (n.startswith("endsong") or n.startswith("streaming_history_audio")))


def _read_json_members(zf: zipfile.ZipFile, predicate) -> list:
    records = []
    for info in zf.infolist():
        if info.is_dir() or not predicate(info.filename):
            continue
        with zf.open(info) as fh:
            try:
                data = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
            except Exception:
                continue
        if isinstance(data, list):
            records.extend(data)
    return records


def parse_zip(zip_path_or_bytes) -> pd.DataFrame:
    """Return a per-play history DataFrame. Raises ValueError if no music plays."""
    if isinstance(zip_path_or_bytes, (bytes, bytearray)):
        zf = zipfile.ZipFile(io.BytesIO(zip_path_or_bytes))
    else:
        zf = zipfile.ZipFile(zip_path_or_bytes)

    with zf:
        ext = _read_json_members(zf, _is_extended)
        rows = []
        if ext:  # prefer the richer extended format when present
            for r in ext:
                track = r.get("master_metadata_track_name")
                artist = r.get("master_metadata_album_artist_name")
                if not track or not artist:
                    continue  # skip podcast/local/null rows
                rows.append({
                    "end_time": r.get("ts"), "artist": artist, "track": track,
                    "ms_played": r.get("ms_played") or 0,
                    "spotify_uri": r.get("spotify_track_uri"),
                })
        else:
            basic = _read_json_members(zf, _is_music_basic)
            for r in basic:
                if not r.get("trackName") or not r.get("artistName"):
                    continue
                rows.append({
                    "end_time": r.get("endTime"), "artist": r.get("artistName"),
                    "track": r.get("trackName"), "ms_played": r.get("msPlayed") or 0,
                    "spotify_uri": None,
                })

    if not rows:
        raise ValueError(
            "No music streaming history found. Make sure you uploaded the Spotify "
            "'Account data' (or 'Extended streaming history') zip — it should contain "
            "StreamingHistory_music_*.json or endsong_*.json files.")

    df = pd.DataFrame(rows)
    dt = pd.to_datetime(df["end_time"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df[dt.notna()].copy()
    dt = dt[dt.notna()]
    df["end_time"] = dt.dt.strftime("%Y-%m-%d %H:%M")
    df["date"] = dt.dt.strftime("%Y-%m-%d")
    df["time"] = dt.dt.strftime("%H:%M")
    df["day_of_week"] = dt.dt.day_name()
    df["hour"] = dt.dt.hour
    df["minutes_played"] = df["ms_played"].astype(float) / 60000.0
    # drop ultra-short blips (<30s) the way wrapped-style summaries do
    df = df[df["ms_played"].astype(float) >= 30000].reset_index(drop=True)
    return df[HISTORY_COLS]


def unique_tracks(history: pd.DataFrame) -> pd.DataFrame:
    """Collapse plays into unique tracks with a normalized key + best-known URI."""
    g = (history.groupby([history["artist"], history["track"]], sort=False)
         .agg(play_count=("track", "size"),
              total_minutes_played=("minutes_played", "sum"),
              spotify_uri=("spotify_uri", lambda s: next((u for u in s if isinstance(u, str)), None)))
         .reset_index())
    g["key"] = [normalize_key(a, t) for a, t in zip(g["artist"], g["track"])]
    return g
