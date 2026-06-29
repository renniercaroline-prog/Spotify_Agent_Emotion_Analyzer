"""GEMS scoring taxonomy for the pipeline (full 45 items + 9 clusters).

The dashboard analysis uses a curated 25-emotion subset (analysis/taxonomy.py),
but the scored-track library stores the full 45 GEMS items + 9 cluster averages so
it stays a superset — identical schema to Anna's seed CSV and future-proof.
"""
from __future__ import annotations

GEMS_ITEMS = [
    # Wonder
    "wonder", "awe", "moved", "amazed", "dazzled",
    # Transcendence
    "inspired", "spiritual", "ecstatic", "elevated", "solemn",
    # Tenderness
    "tender", "affectionate", "loving", "sensual", "romantic",
    # Nostalgia
    "nostalgic", "dreamy", "sentimental", "melancholic", "longing",
    # Peacefulness
    "calm", "relaxed", "serene", "soothing", "meditative",
    # Power
    "powerful", "strong", "energetic", "triumphant", "heroic",
    # Joyful Activation
    "joyful", "cheerful", "lively", "animated", "radiant",
    # Tension
    "tense", "agitated", "nervous", "restless", "impatient",
    # Sadness
    "sad", "sorrowful", "depressed", "hopeless", "grieving",
]

GEMS_CLUSTERS = {
    "Wonder": GEMS_ITEMS[0:5],
    "Transcendence": GEMS_ITEMS[5:10],
    "Tenderness": GEMS_ITEMS[10:15],
    "Nostalgia": GEMS_ITEMS[15:20],
    "Peacefulness": GEMS_ITEMS[20:25],
    "Power": GEMS_ITEMS[25:30],
    "Joyful Activation": GEMS_ITEMS[30:35],
    "Tension": GEMS_ITEMS[35:40],
    "Sadness": GEMS_ITEMS[40:45],
}

ITEM_COLS = [f"gems_{i}" for i in GEMS_ITEMS]
CLUSTER_COLS = [f"gems_cluster_{c.lower().replace(' ', '_')}" for c in GEMS_CLUSTERS]

# bump when the scoring prompt/model changes, so re-scores are distinguishable
PROMPT_VERSION = "gems45-v1"
SCORING_MODEL = "gpt-4o-mini"


def normalize_key(artist, track) -> str:
    """Canonical track identity used everywhere (library, join, dedup)."""
    return f"{str(artist).strip().lower()}|||{str(track).strip().lower()}"


def cluster_averages(item_scores: dict) -> dict:
    """Given {item: score}, return {gems_cluster_<name>: mean of its 5 items}."""
    out = {}
    for cluster, items in GEMS_CLUSTERS.items():
        vals = [item_scores[i] for i in items
                if item_scores.get(i) is not None]
        col = f"gems_cluster_{cluster.lower().replace(' ', '_')}"
        out[col] = (sum(vals) / len(vals)) if vals else None
    return out
