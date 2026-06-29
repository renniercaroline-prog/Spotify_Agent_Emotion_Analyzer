"""GEMS scoring with gpt-4o-mini — productionized from the notebook.

Same prompt, model, temperature=0, and JSON response format. Returns a dict of
all 45 GEMS item scores (0–1), or None on failure.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

from gems import GEMS_ITEMS, SCORING_MODEL

_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        _client = OpenAI(api_key=key)
    return _client


def score_lyrics(lyrics: str) -> dict | None:
    """Score lyrics on all 45 GEMS items. Returns {item: float 0-1} or None."""
    prompt = (
        "Rate the emotions in these lyrics on a scale from 0 to 1, where 0 means "
        "the emotion is completely absent and 1 means it is strongly present.\n\n"
        f"Rate each of these 45 emotions: {', '.join(GEMS_ITEMS)}\n\n"
        "Return ONLY a JSON object with each emotion as a key and its score as a "
        "value. No other text.\n\nLyrics:\n" + (lyrics or "")[:3000])
    try:
        resp = _get_client().chat.completions.create(
            model=SCORING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"})
        raw = json.loads(resp.choices[0].message.content)
    except Exception:
        return None
    # keep only known items, coerce to float in [0,1]
    out = {}
    for item in GEMS_ITEMS:
        v = raw.get(item)
        try:
            out[item] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            out[item] = None
    return out
