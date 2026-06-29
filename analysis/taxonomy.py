"""Emotion taxonomy for the dashboard.

The product is built around a curated set of **25 GEMS emotions** (not the 9
clusters). The original GEMS cluster each emotion belongs to is kept ONLY behind
the scenes — to color related emotions as visual families and to avoid surfacing
five near-duplicate findings in the surprise engine. Clusters are never shown in
the UI. Nothing subject-specific lives here.
"""

# The 25 emotions, in display order (grouped by family for a coherent radar).
SELECTED_EMOTIONS = [
    # transcendence
    "inspired", "ecstatic", "solemn",
    # tenderness
    "tender", "affectionate", "loving", "sensual", "romantic",
    # wonder
    "wonder",
    # nostalgia
    "longing", "nostalgic", "dreamy", "sentimental", "melancholic",
    # peacefulness
    "calm",
    # power
    "powerful", "energetic", "triumphant",
    # joyful activation
    "joyful", "radiant",
    # tension
    "tense", "nervous",
    # sadness
    "sad", "hopeless", "sorrowful",
]

# emotion -> original GEMS cluster (internal use: color families + dedup only)
EMOTION_PARENT = {
    "inspired": "transcendence", "ecstatic": "transcendence", "solemn": "transcendence",
    "tender": "tenderness", "affectionate": "tenderness", "loving": "tenderness",
    "sensual": "tenderness", "romantic": "tenderness",
    "wonder": "wonder",
    "longing": "nostalgia", "nostalgic": "nostalgia", "dreamy": "nostalgia",
    "sentimental": "nostalgia", "melancholic": "nostalgia",
    "calm": "peacefulness",
    "powerful": "power", "energetic": "power", "triumphant": "power",
    "joyful": "joyful_activation", "radiant": "joyful_activation",
    "tense": "tension", "nervous": "tension",
    "sad": "sadness", "hopeless": "sadness", "sorrowful": "sadness",
}

# one color per emotion. Hue follows the emotion's family; lightness/saturation
# vary within a family so related feelings look related but stay distinguishable.
EMOTION_COLORS = {
    # transcendence — sky blues
    "inspired": "#4ea8de", "ecstatic": "#6fc2ef", "solemn": "#3b82b8",
    # tenderness — pinks
    "tender": "#ff7eb6", "affectionate": "#ff9ec7", "loving": "#ff5fa2",
    "sensual": "#e85a8f", "romantic": "#ffb3d1",
    # wonder — violet
    "wonder": "#7c5cff",
    # nostalgia — warm browns / mauve
    "longing": "#b08968", "nostalgic": "#cda07a", "dreamy": "#a78b98",
    "sentimental": "#d8b48c", "melancholic": "#8c6f5e",
    # peacefulness — cyan
    "calm": "#48cae4",
    # power — reds
    "powerful": "#ff5c5c", "energetic": "#ff8559", "triumphant": "#d62828",
    # joyful activation — golds
    "joyful": "#ffd166", "radiant": "#ffb703",
    # tension — oranges
    "tense": "#f3722c", "nervous": "#f9a03f",
    # sadness — slate blues
    "sad": "#5a7d9a", "hopeless": "#466079", "sorrowful": "#6f93b0",
}


def emotion_label(emotion: str) -> str:
    return emotion.replace("_", " ").capitalize()


EMOTION_LABELS = {e: emotion_label(e) for e in SELECTED_EMOTIONS}
