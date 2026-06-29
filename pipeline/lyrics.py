"""Lyric retrieval for GEMS scoring.

Uses server-friendly lyrics APIs that return plain text without scraping:
  1. LRCLIB  (https://lrclib.net) — free, no key, built for apps, good coverage
  2. lyrics.ovh fallback           — free, no key

We deliberately do NOT scrape genius.com: its lyric pages are Cloudflare
bot-protected (HTTP 403 from servers), so scraping is unreliable — especially
from cloud hosts like Railway.
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote

import requests

_UA = {"User-Agent": "gems-emotion-app/1.0 (+https://carolinerennier.com)"}


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\[.*?\]", "", text)        # strip [Verse]/[Chorus] markers
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(text) > 50 else None


def _from_lrclib(artist: str, track: str):
    # exact-ish match first
    try:
        r = requests.get("https://lrclib.net/api/get", headers=_UA, timeout=12,
                         params={"artist_name": artist, "track_name": track})
        if r.status_code == 200:
            pl = _clean((r.json() or {}).get("plainLyrics"))
            if pl:
                return pl
    except Exception:
        pass
    # fuzzy search fallback within LRCLIB
    try:
        r = requests.get("https://lrclib.net/api/search", headers=_UA, timeout=12,
                         params={"artist_name": artist, "track_name": track})
        if r.status_code == 200:
            for item in (r.json() or [])[:5]:
                pl = _clean(item.get("plainLyrics"))
                if pl:
                    return pl
    except Exception:
        pass
    return None


def _from_lyrics_ovh(artist: str, track: str):
    try:
        r = requests.get(
            f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(track)}", timeout=12)
        if r.status_code == 200:
            return _clean((r.json() or {}).get("lyrics"))
    except Exception:
        pass
    return None


def fetch_lyrics(artist: str, track: str, pause: float = 0.15):
    """Return plain lyrics text for a track, or None if not found anywhere."""
    for source in (_from_lrclib, _from_lyrics_ovh):
        lyrics = source(artist, track)
        if pause:
            time.sleep(pause)
        if lyrics:
            return lyrics
    return None
