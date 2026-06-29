"""Genius lyric retrieval — search then scrape — productionized from the notebook.

Polite rate limiting + retry on 429. Returns clean lyrics text or None.
"""
from __future__ import annotations

import os
import re
import time

import requests
from bs4 import BeautifulSoup

GENIUS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
_UA = {"User-Agent": "Mozilla/5.0 (compatible; GEMS-emotion-bot/1.0)"}


def search_genius(artist: str, track: str, _depth=0):
    """Search Genius for a track; return the best-matching song URL or None."""
    if not GENIUS_TOKEN:
        raise RuntimeError("GENIUS_ACCESS_TOKEN not set")
    resp = requests.get(
        "https://api.genius.com/search",
        headers={"Authorization": f"Bearer {GENIUS_TOKEN}"},
        params={"q": f"{track} {artist}"}, timeout=10)
    if resp.status_code == 429 and _depth < 3:
        time.sleep(5)
        return search_genius(artist, track, _depth + 1)
    resp.raise_for_status()
    hits = resp.json().get("response", {}).get("hits", [])
    if not hits:
        return None
    al = artist.lower()
    for hit in hits:
        if al in hit["result"]["primary_artist"]["name"].lower():
            return hit["result"]["url"]
    return hits[0]["result"]["url"]


def scrape_lyrics(url: str):
    """Scrape and clean lyrics from a Genius song page; None if too short/missing."""
    try:
        resp = requests.get(url, headers=_UA, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        if not containers:
            return None
        parts = []
        for c in containers:
            for br in c.find_all("br"):
                br.replace_with("\n")
            parts.append(c.get_text())
        lyrics = re.sub(r"\[.*?\]", "", "\n".join(parts)).strip()
        return lyrics if len(lyrics) > 50 else None
    except Exception:
        return None


def fetch_lyrics(artist: str, track: str, pause: float = 0.3):
    """Search + scrape with a small polite pause. Returns lyrics text or None."""
    url = search_genius(artist, track)
    if pause:
        time.sleep(pause)
    if not url:
        return None
    return scrape_lyrics(url)
