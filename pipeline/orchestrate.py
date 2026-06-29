"""End-to-end new-user pipeline: Spotify export zip -> dashboard.html.

  zip -> parse plays + unique tracks
      -> look each track up in the shared library (only MISSES hit Genius + GPT)
      -> write newly scored tracks back to the library
      -> join to the user's plays and run the analysis engine + dashboard

Reuses analysis/analyze.py and analysis/dashboard.py unchanged.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

import pandas as pd

# make sibling packages importable (analysis/ and this pipeline/ dir)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_HERE, os.path.join(_ROOT, "analysis")):
    if p not in sys.path:
        sys.path.insert(0, p)

from gems import (CLUSTER_COLS, ITEM_COLS, PROMPT_VERSION, SCORING_MODEL,
                  cluster_averages)
from lyrics import fetch_lyrics
from gems_scoring import score_lyrics
from parse_export import parse_zip, unique_tracks
from track_library import TrackLibrary

from analyze import Config, analyze          # noqa: E402
from dashboard import build_html             # noqa: E402


def _score_one(row) -> dict:
    """Fetch + score a single missing track; returns a library record."""
    rec = {"key": row.key, "artist": row.artist, "track": row.track,
           "spotify_uri": getattr(row, "spotify_uri", None),
           "source": "lyricsapi+gpt", "model": SCORING_MODEL,
           "prompt_version": PROMPT_VERSION, "scored_at": time.time(),
           "lyrics": None, "has_lyrics": 0}
    for c in ITEM_COLS + CLUSTER_COLS:
        rec[c] = None
    lyrics = None
    try:
        lyrics = fetch_lyrics(row.artist, row.track)
    except Exception:
        lyrics = None
    if not lyrics:
        return rec  # stored as has_lyrics=0 so we don't re-fetch endlessly
    rec["lyrics"], rec["has_lyrics"] = lyrics, 1
    scores = score_lyrics(lyrics)
    if scores:
        for item, v in scores.items():
            rec[f"gems_{item}"] = v
        rec.update(cluster_averages(scores))
    return rec


def run_pipeline(zip_path, name, out_html_path, lib: TrackLibrary,
                 progress=None, hemisphere="north"):
    """Run the full pipeline. `progress(stage, **info)` is an optional callback.
    Returns a summary dict."""
    def report(stage, **info):
        if progress:
            progress(stage, **info)

    report("parsing")
    history = parse_zip(zip_path)
    uniq = unique_tracks(history)
    keys = uniq["key"].tolist()
    report("parsed", plays=int(len(history)), unique_tracks=int(len(keys)))

    hits = lib.lookup(keys)
    misses = [r for r in uniq.itertuples() if r.key not in hits]
    report("dedup", cached=len(hits), to_score=len(misses))

    newly_scored = 0
    for i, row in enumerate(misses, 1):
        rec = _score_one(row)
        lib.upsert(rec)
        if rec["has_lyrics"]:
            newly_scored += 1
        if progress and (i % 10 == 0 or i == len(misses)):
            report("scoring", done=i, total=len(misses), new_scored=newly_scored)

    # build the user's gems frame from the (now complete) library
    gems_df = lib.to_gems_frame(keys)

    with tempfile.TemporaryDirectory() as td:
        hist_csv = os.path.join(td, "history.csv")
        gems_csv = os.path.join(td, "gems.csv")
        history.to_csv(hist_csv, index=False)
        gems_df.to_csv(gems_csv, index=False)

        report("analyzing")
        results = analyze(hist_csv, gems_csv, name=name,
                          cfg=Config(hemisphere=hemisphere),
                          warn=lambda m: report("warn", message=m))

    os.makedirs(os.path.dirname(os.path.abspath(out_html_path)), exist_ok=True)
    with open(out_html_path, "w") as f:
        f.write(build_html(results))

    summary = {
        "name": name,
        "plays": results["meta"]["total_plays"],
        "unique_tracks": int(len(keys)),
        "cached": len(hits),
        "newly_fetched": len(misses),
        "newly_scored": newly_scored,
        "coverage_pct": results["meta"]["coverage_plays_pct"],
        "findings": len(results["findings"]),
        "out": out_html_path,
    }
    report("done", **summary)
    return summary


def get_library() -> TrackLibrary:
    """Open the shared library, seeding on first run from whichever seed exists:
    the full local CSV (with lyrics, gitignored) or a committed head-start seed
    (data/track_seed.csv, lyrics-stripped). Starts empty if neither is present."""
    db_path = os.getenv("TRACK_DB_PATH", os.path.join(_ROOT, "data", "track_library.db"))
    lib = TrackLibrary(db_path)
    if lib.count() == 0:
        for seed in (os.path.join(_ROOT, "annas_tracks_gems_scored.csv"),
                     os.path.join(_ROOT, "data", "track_seed.csv")):
            if os.path.exists(seed):
                from track_library import seed_from_csv
                n = seed_from_csv(lib, seed)
                print(f"Seeded track library with {n} tracks from {os.path.basename(seed)}")
                break
    return lib


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run the new-user pipeline on a zip")
    ap.add_argument("--zip", required=True)
    ap.add_argument("--name", default="You")
    ap.add_argument("--out", default="user_dashboard.html")
    ap.add_argument("--hemisphere", default="north")
    args = ap.parse_args()
    lib = get_library()
    s = run_pipeline(args.zip, args.name, args.out, lib,
                     progress=lambda st, **i: print(f"  [{st}] {i}"),
                     hemisphere=args.hemisphere)
    print("DONE:", s)
