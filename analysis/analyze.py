"""Shared emotion analysis engine.

Loads a person's listening history + their GEMS-scored unique tracks, joins them,
and produces a single `results` dict (written as results.json) containing:

  - meta (name, date range, totals)
  - taxonomy (the 25 emotions, labels, colors) for the dashboard
  - baseline (minutes-weighted mean of every emotion across all plays)
  - profiles (weighted emotion means per bucket for every grouping dimension)
  - signatures (the tracks/artists that most embody each emotion)
  - findings (the surprise-ranking engine's top plain-English insights)

The product is built around a curated set of 25 GEMS emotions (see taxonomy.py).
The original 9 clusters are used ONLY internally — to keep correlated findings
from crowding the headline list. Nothing here is subject-specific: the emotion
columns are auto-detected from the headers and the code fails loudly on mismatch.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from taxonomy import (
    EMOTION_COLORS,
    EMOTION_LABELS,
    EMOTION_PARENT,
    SELECTED_EMOTIONS,
    emotion_label,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PARTS_OF_DAY = [
    ("Night", range(0, 6)),
    ("Morning", range(6, 12)),
    ("Afternoon", range(12, 18)),
    ("Evening", range(18, 24)),
]
PART_OF_DAY_ORDER = [p[0] for p in PARTS_OF_DAY]
HOUR_TO_PART = {h: name for name, hrs in PARTS_OF_DAY for h in hrs}

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]

SEASON_NORTH = {12: "Winter", 1: "Winter", 2: "Winter",
                3: "Spring", 4: "Spring", 5: "Spring",
                6: "Summer", 7: "Summer", 8: "Summer",
                9: "Autumn", 10: "Autumn", 11: "Autumn"}
SEASON_SOUTH = {12: "Summer", 1: "Summer", 2: "Summer",
                3: "Autumn", 4: "Autumn", 5: "Autumn",
                6: "Winter", 7: "Winter", 8: "Winter",
                9: "Spring", 10: "Spring", 11: "Spring"}
SEASON_ORDER = ["Spring", "Summer", "Autumn", "Winter"]


@dataclass
class Config:
    weight: str = "minutes"          # 'minutes' or 'plays'
    hemisphere: str = "north"        # 'north' or 'south'
    min_minutes_frac: float = 0.01   # support gate: bucket must hold >=1% of minutes
    min_plays: int = 30              # ...and >= this many plays
    n_permutations: int = 2000       # permutation test iterations
    n_candidates: int = 24           # diverse shortlist size to significance-test
    n_findings: int = 9              # how many findings to surface
    seed: int = 7


# ---------------------------------------------------------------------------
# Load + join
# ---------------------------------------------------------------------------

def _norm_key(artist, track) -> str:
    return f"{str(artist).strip().lower()}|||{str(track).strip().lower()}"


def _detect_emotion_columns(gems: pd.DataFrame):
    """Auto-detect the 25 selected emotion columns; fail loudly if any missing."""
    cols = {}
    for emo in SELECTED_EMOTIONS:
        col = f"gems_{emo}"
        if col not in gems.columns:
            raise ValueError(f"Missing expected emotion column: {col}")
        cols[emo] = col
    return cols


def load_and_join(history_path: str, gems_path: str, warn=print):
    """Join plays -> their track's emotion vector. URI first, then normalized key."""
    hist = pd.read_csv(history_path)
    gems = pd.read_csv(gems_path)

    emo_cols = _detect_emotion_columns(gems)
    cols = list(emo_cols.values())

    gems = gems.reset_index(drop=True).copy()
    gems["_key"] = [_norm_key(a, t) for a, t in zip(gems["artist"], gems["track"])]

    uri_to_idx = {}
    if "spotify_uri" in gems.columns:
        for idx, u in gems["spotify_uri"].items():
            if isinstance(u, str) and u not in uri_to_idx:
                uri_to_idx[u] = idx
    key_to_idx = {}
    for idx, k in gems["_key"].items():
        if k not in key_to_idx:
            key_to_idx[k] = idx

    hist = hist.copy()
    if "minutes_played" not in hist.columns:
        hist["minutes_played"] = hist["ms_played"] / 60000.0
    hist["_key"] = [_norm_key(a, t) for a, t in zip(hist["artist"], hist["track"])]
    uris = (hist["spotify_uri"].values if "spotify_uri" in hist.columns
            else [None] * len(hist))

    gidx = np.full(len(hist), -1, dtype=int)
    for i, (u, k) in enumerate(zip(uris, hist["_key"].values)):
        j = uri_to_idx.get(u) if isinstance(u, str) else None
        if j is None:
            j = key_to_idx.get(k)
        if j is not None:
            gidx[i] = j

    matched = gidx >= 0
    cov_plays = matched.mean() * 100
    cov_min = (hist.loc[matched, "minutes_played"].sum()
               / hist["minutes_played"].sum() * 100)
    if cov_plays < 95:
        warn(f"WARNING: join coverage only {cov_plays:.1f}% of plays "
             f"({cov_min:.1f}% of minutes)")

    plays = hist.loc[matched].reset_index(drop=True).copy()
    emo_block = gems.iloc[gidx[matched]][cols].reset_index(drop=True)
    for c in cols:
        plays[c] = emo_block[c].values

    info = {
        "coverage_plays_pct": round(cov_plays, 2),
        "coverage_minutes_pct": round(cov_min, 2),
        "n_plays_total": int(len(hist)),
        "n_plays_matched": int(matched.sum()),
        "emo_cols": emo_cols,
    }
    return plays, info


# ---------------------------------------------------------------------------
# Time enrichment
# ---------------------------------------------------------------------------

def enrich_time(plays: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    plays = plays.copy()
    dt = pd.to_datetime(plays["end_time"])
    plays["_dt"] = dt
    if "hour" not in plays.columns:
        plays["hour"] = dt.dt.hour
    plays["hour"] = plays["hour"].astype(int)
    if "day_of_week" not in plays.columns:
        plays["day_of_week"] = dt.dt.day_name()
    plays["part_of_day"] = plays["hour"].map(HOUR_TO_PART)
    # multi-resolution time-of-day chunks (bucket = start hour of the block)
    plays["tod_2h"] = (plays["hour"] // 2) * 2
    plays["tod_3h"] = (plays["hour"] // 3) * 3
    plays["is_weekend"] = plays["day_of_week"].isin(["Saturday", "Sunday"])
    plays["weekend_label"] = np.where(plays["is_weekend"], "Weekend", "Weekday")
    plays["month"] = dt.dt.strftime("%Y-%m")
    plays["month_num"] = dt.dt.month
    plays["year"] = dt.dt.year.astype(str)
    season_map = SEASON_NORTH if cfg.hemisphere == "north" else SEASON_SOUTH
    plays["season"] = plays["month_num"].map(season_map)
    plays["_w"] = (plays["minutes_played"] if cfg.weight == "minutes"
                   else pd.Series(1.0, index=plays.index))
    return plays


# ---------------------------------------------------------------------------
# Weighted aggregation
# ---------------------------------------------------------------------------

def _wmean(values: np.ndarray, weights: np.ndarray) -> float:
    """Minutes-weighted mean, ignoring plays with no GEMS score (NaN)."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = ~np.isnan(values)
    w = weights[mask].sum()
    if w <= 0:
        return float("nan")
    return float(np.dot(values[mask], weights[mask]) / w)


def _weighted_std(values, weights):
    values = np.asarray(values, dtype=float)
    m = _wmean(values, weights)
    if math.isnan(m):
        return 0.0
    var = _wmean((values - m) ** 2, weights)
    return math.sqrt(max(var, 0.0))


def _entropy(vec):
    v = np.clip(np.array(vec, dtype=float), 1e-12, None)
    p = v / v.sum()
    return float(-(p * np.log(p)).sum() / math.log(len(p)))  # normalized 0..1


def baseline_profile(plays, info, cfg):
    w = plays["_w"].values
    return {"emotions": {emo: _wmean(plays[col].values, w)
                         for emo, col in info["emo_cols"].items()}}


def profile_by(plays, info, cfg, group_col, order=None):
    """Weighted mean of all 25 emotions per bucket, plus support + diversity."""
    buckets = []
    groups = plays.groupby(group_col, sort=False)
    keys = order if order is not None else sorted(groups.groups.keys())
    for key in keys:
        if key not in groups.groups:
            continue
        g = groups.get_group(key)
        w = g["_w"].values
        emotions = {emo: _wmean(g[col].values, w)
                    for emo, col in info["emo_cols"].items()}
        buckets.append({
            "label": str(key),
            "minutes": round(float(g["minutes_played"].sum()), 1),
            "plays": int(len(g)),
            "unique_tracks": int(g["_key"].nunique()),
            "emotions": emotions,
            "diversity": _entropy(list(emotions.values())),
        })
    return buckets


DIMENSIONS = [
    ("hour", "Hour of day", lambda p: list(range(24))),
    ("tod_2h", "Time of day (2h)", lambda p: list(range(0, 24, 2))),
    ("tod_3h", "Time of day (3h)", lambda p: list(range(0, 24, 3))),
    ("part_of_day", "Part of day", lambda p: PART_OF_DAY_ORDER),
    ("day_of_week", "Day of week", lambda p: DOW_ORDER),
    ("weekend_label", "Weekday vs weekend", lambda p: ["Weekday", "Weekend"]),
    ("month", "Month", lambda p: sorted(p["month"].unique())),
    ("season", "Season", lambda p: SEASON_ORDER),
    ("year", "Year", lambda p: sorted(p["year"].unique())),
]


def build_profiles(plays, info, cfg):
    profiles = {}
    for col, label, order_fn in DIMENSIONS:
        profiles[col] = {
            "label": label,
            "buckets": profile_by(plays, info, cfg, col, order=order_fn(plays)),
        }
    return profiles


# ---------------------------------------------------------------------------
# Signature tracks/artists per emotion
# ---------------------------------------------------------------------------

def signature_tracks(plays, info, cfg, top_n=5, min_minutes=10):
    """For each emotion: the tracks/artists that most embody it in this listening."""
    out = {}
    track_min = plays.groupby("_key").agg(
        artist=("artist", "first"), track=("track", "first"),
        minutes=("minutes_played", "sum")).reset_index()
    first = plays.drop_duplicates("_key").set_index("_key")
    for emo, col in info["emo_cols"].items():
        track_min[emo] = track_min["_key"].map(first[col])
    art_w = plays.groupby("artist")["minutes_played"].sum()
    for emo, col in info["emo_cols"].items():
        elig = track_min[track_min["minutes"] >= min_minutes]
        top_t = elig.sort_values(emo, ascending=False).head(top_n)
        tracks = [{"artist": r.artist, "track": r.track,
                   "score": round(float(getattr(r, emo)), 3),
                   "minutes": round(float(r.minutes), 1)}
                  for r in top_t.itertuples()]
        a = plays.groupby("artist").apply(
            lambda g: _wmean(g[col].values, g["_w"].values), include_groups=False)
        a = a[art_w >= min_minutes * 2].sort_values(ascending=False).head(top_n)
        artists = [{"artist": name, "score": round(float(val), 3),
                    "minutes": round(float(art_w[name]), 1)}
                   for name, val in a.items() if not math.isnan(val)]
        out[emo] = {"tracks": tracks, "artists": artists}
    return out


# ---------------------------------------------------------------------------
# Leaderboards + song-tied metadata
# ---------------------------------------------------------------------------

def _dominant_emotion(scores: dict):
    """The single highest-scoring emotion for a track/artist (None if unscored)."""
    best, best_v = None, -1.0
    for emo, v in scores.items():
        if v is not None and not (isinstance(v, float) and math.isnan(v)) and v > best_v:
            best, best_v = emo, v
    if best is None:
        return {"emotion": None, "emotion_label": None,
                "color": "#9aa7b4", "score": 0.0}
    return {"emotion": best, "emotion_label": emotion_label(best),
            "color": EMOTION_COLORS[best], "score": round(float(best_v), 3)}


def leaderboards(plays, info, top_n=12):
    """Most-played tracks and artists (by minutes), each tagged with its dominant emotion."""
    first = plays.drop_duplicates("_key").set_index("_key")
    tg = (plays.groupby("_key")
          .agg(artist=("artist", "first"), track=("track", "first"),
               plays=("_key", "size"), minutes=("minutes_played", "sum"))
          .sort_values("minutes", ascending=False).head(top_n))
    tracks = []
    for key, r in tg.iterrows():
        dom = _dominant_emotion({e: first.loc[key, c] for e, c in info["emo_cols"].items()})
        tracks.append({"track": r.track, "artist": r.artist, "plays": int(r.plays),
                       "minutes": round(float(r.minutes), 1), **dom})

    ag = (plays.groupby("artist")
          .agg(plays=("artist", "size"), minutes=("minutes_played", "sum"),
               tracks=("_key", "nunique"))
          .sort_values("minutes", ascending=False).head(top_n))
    artists = []
    for name, r in ag.iterrows():
        sub = plays[plays["artist"] == name]
        w = sub["_w"].values
        dom = _dominant_emotion({e: _wmean(sub[c].values, w)
                                 for e, c in info["emo_cols"].items()})
        artists.append({"artist": name, "plays": int(r.plays),
                        "minutes": round(float(r.minutes), 1),
                        "tracks": int(r.tracks), **dom})
    return {"tracks": tracks, "artists": artists}


def defining_by_part(plays, info):
    """The single most-played track in each part of the day, with its dominant emotion."""
    first = plays.drop_duplicates("_key").set_index("_key")
    out = []
    for part in PART_OF_DAY_ORDER:
        sub = plays[plays["part_of_day"] == part]
        if len(sub) == 0:
            continue
        tg = (sub.groupby("_key")
              .agg(artist=("artist", "first"), track=("track", "first"),
                   plays=("_key", "size"), minutes=("minutes_played", "sum"))
              .sort_values("minutes", ascending=False).head(1))
        for key, r in tg.iterrows():
            dom = _dominant_emotion({e: first.loc[key, c]
                                     for e, c in info["emo_cols"].items()})
            out.append({"part": part, "track": r.track, "artist": r.artist,
                        "plays": int(r.plays), "minutes": round(float(r.minutes), 1),
                        **dom})
    return out


def discovery_by_month(plays):
    """New tracks per month (first time each track appears in the history)."""
    disc = plays.groupby("_key")["_dt"].min().dt.strftime("%Y-%m")
    counts = disc.value_counts().sort_index()
    return [{"month": m, "new_tracks": int(n)} for m, n in counts.items()]


# ---------------------------------------------------------------------------
# Surprise-ranking engine
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    dimension: str
    dim_label: str
    bucket: str
    emotion: str
    col: str
    bucket_mean: float
    baseline: float
    z: float
    pct: float
    minutes: float
    plays: int
    p_value: float = 1.0
    interestingness: float = 0.0


def _possessive(name: str) -> str:
    name = name.strip()
    if not name or name.lower() in ("listener", "you"):
        return "Their"
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _ampm(h: int) -> str:
    h %= 24
    return f"{(h % 12) or 12}{'am' if h < 12 else 'pm'}"


# how a mined dimension maps to a "class" for balancing the headline list
TOD_DIMS = {"hour": 1, "tod_2h": 2, "tod_3h": 3, "part_of_day": 6}
# which time-of-day resolutions feed the surprise engine (1h is too noisy; it
# stays available as the hour-by-hour "emotional clock" chart for exploration)
MINE_TOD_DIMS = ["tod_2h", "tod_3h", "part_of_day"]
MINE_DIMS = MINE_TOD_DIMS + ["day_of_week", "weekend_label", "month", "season"]
# at most this many findings per dimension class, so no single lens dominates
CLASS_CAP = {"timeofday": 3, "dayofweek": 2, "month": 2, "season": 2}


def _dim_class(dim: str) -> str:
    if dim in TOD_DIMS:
        return "timeofday"
    if dim in ("day_of_week", "weekend_label"):
        return "dayofweek"
    return dim  # 'month' or 'season'


def _center_region(c: "Cell") -> str:
    """A coarse label used to collapse overlapping time windows across the 1/2/3/6h
    resolutions into one finding (so the same pattern isn't reported four times)."""
    if c.dimension in TOD_DIMS and c.dimension != "part_of_day":
        size = TOD_DIMS[c.dimension]
        return HOUR_TO_PART[(int(c.bucket) + size // 2) % 24]
    return c.bucket


def _diverse_select(cells, limit, class_cap=None,
                    fam_cap=2, emo_cap=2, bucket_cap=2):
    """Walk cells in priority order, keeping a varied set: collapse overlapping
    time windows / correlated emotions, and (optionally) cap per dimension class."""
    seen, ccount, bcount, fcount, ecount, out = set(), {}, {}, {}, {}, []
    for c in cells:
        cls = _dim_class(c.dimension)
        fam = EMOTION_PARENT[c.emotion]
        bg = _center_region(c)
        d = "up" if c.z > 0 else "down"
        if (cls, bg, fam, d) in seen:
            continue
        if class_cap is not None and ccount.get(cls, 0) >= class_cap.get(cls, 99):
            continue
        if bcount.get((cls, bg), 0) >= bucket_cap:
            continue
        if fcount.get((fam, d), 0) >= fam_cap:
            continue
        if ecount.get(c.emotion, 0) >= emo_cap:
            continue
        seen.add((cls, bg, fam, d))
        ccount[cls] = ccount.get(cls, 0) + 1
        bcount[(cls, bg)] = bcount.get((cls, bg), 0) + 1
        fcount[(fam, d)] = fcount.get((fam, d), 0) + 1
        ecount[c.emotion] = ecount.get(c.emotion, 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


def find_surprises(plays, info, cfg, baseline, name="Listener"):
    rng = np.random.default_rng(cfg.seed)
    total_minutes = plays["minutes_played"].sum()
    min_minutes = cfg.min_minutes_frac * total_minutes
    dim_labels = {d: lbl for d, lbl, _ in DIMENSIONS}

    scales = {col: (_weighted_std(plays[col].values, plays["_w"].values) or 1e-9)
              for col in info["emo_cols"].values()}

    # build candidate cells per mined dimension
    by_dim: dict[str, list[Cell]] = {d: [] for d in MINE_DIMS}
    for dim in MINE_DIMS:
        for bucket_key, g in plays.groupby(dim):
            w = g["_w"].values
            mins = float(g["minutes_played"].sum())
            n = int(len(g))
            if mins < min_minutes or n < cfg.min_plays:
                continue
            for emo, col in info["emo_cols"].items():
                bm = _wmean(g[col].values, w)
                base = baseline["emotions"][emo]
                z = (bm - base) / scales[col]
                pct = (bm - base) / base * 100 if base > 1e-6 else 0.0
                by_dim[dim].append(Cell(
                    dimension=dim, dim_label=dim_labels[dim], bucket=str(bucket_key),
                    emotion=emo, col=col, bucket_mean=bm, baseline=base,
                    z=z, pct=pct, minutes=mins, plays=n))

    # build a pool to permutation-test: top diverse cells PER dimension, so every
    # lens (incl. the quieter season/month) gets a fair shot at significance.
    pool: list[Cell] = []
    for dim in MINE_DIMS:
        cells = sorted(by_dim[dim], key=lambda c: abs(c.z), reverse=True)
        pool += _diverse_select(cells, limit=cfg.n_candidates)

    idx = np.arange(len(plays))
    w_all = plays["_w"].values
    for c in pool:
        col_vals = plays[c.col].values
        n_in = int((plays[c.dimension].astype(str) == c.bucket).sum())
        observed = abs(c.bucket_mean - c.baseline)
        hits = 0
        for _ in range(cfg.n_permutations):
            sel = rng.choice(idx, size=n_in, replace=False)
            bm = _wmean(col_vals[sel], w_all[sel])
            if abs(bm - c.baseline) >= observed:
                hits += 1
        c.p_value = (hits + 1) / (cfg.n_permutations + 1)
        rel = min(1.0, c.minutes / (0.05 * total_minutes))
        c.interestingness = abs(c.z) * rel

    sig = sorted([c for c in pool if c.p_value < 0.05],
                 key=lambda c: c.interestingness, reverse=True)

    # final list: balanced across dimension classes, one finding per specific
    # bucket (so the day/seasons spread out), then relaxed to fill 9
    chosen = _diverse_select(sig, cfg.n_findings, class_cap=CLASS_CAP, bucket_cap=1)
    if len(chosen) < cfg.n_findings:
        used = {(_dim_class(c.dimension), _center_region(c),
                 EMOTION_PARENT[c.emotion], "up" if c.z > 0 else "down")
                for c in chosen}
        remaining = [c for c in sig
                     if (_dim_class(c.dimension), _center_region(c),
                         EMOTION_PARENT[c.emotion], "up" if c.z > 0 else "down") not in used]
        chosen += _diverse_select(remaining, cfg.n_findings - len(chosen),
                                  class_cap=None, bucket_cap=1)
    chosen.sort(key=lambda c: c.interestingness, reverse=True)
    return [_finding_dict(c, name) for c in chosen]


def _month_name(bucket: str) -> str:
    import calendar
    y, mo = bucket.split("-")
    return f"{calendar.month_name[int(mo)]} {y}"


def _bucket_phrase(c: Cell) -> str:
    if c.dimension in TOD_DIMS and c.dimension != "part_of_day":
        size = TOD_DIMS[c.dimension]
        h = int(c.bucket)
        return f"{_ampm(h)}–{_ampm(h + size)} listening"
    if c.dimension in ("part_of_day", "weekend_label"):
        return f"{c.bucket.lower()} listening"
    if c.dimension == "day_of_week":
        return f"{c.bucket} listening"
    if c.dimension == "season":
        return f"listening in {c.bucket}"
    if c.dimension == "month":
        return f"listening in {_month_name(c.bucket)}"
    return f"{c.bucket} listening"


def _finding_dict(c: Cell, name: str = "Listener") -> dict:
    emo_lbl = emotion_label(c.emotion).lower()
    direction = "more" if c.pct >= 0 else "less"
    magnitude = abs(round(c.pct))
    phrase = _bucket_phrase(c)
    if c.p_value < 0.001:
        psig = "p < 0.001"
    elif c.p_value < 0.01:
        psig = "p < 0.01"
    else:
        psig = f"p = {c.p_value:.3f}"
    poss = _possessive(name)
    sentence = (f"{poss} {phrase} runs {magnitude}% {direction} "
                f"*{emo_lbl}* than their overall average ({psig}).")
    return {
        "sentence": sentence,
        "dimension": c.dimension,
        "dim_label": c.dim_label,
        "bucket": c.bucket,
        "emotion": c.emotion,
        "emotion_label": emotion_label(c.emotion),
        "color": EMOTION_COLORS[c.emotion],
        "bucket_mean": round(c.bucket_mean, 4),
        "baseline": round(c.baseline, 4),
        "pct": round(c.pct, 1),
        "z": round(c.z, 3),
        "p_value": round(c.p_value, 4),
        "minutes": round(c.minutes, 1),
        "plays": c.plays,
    }


# ---------------------------------------------------------------------------
# Overall listener statement
# ---------------------------------------------------------------------------

_TOD_WORDS = {"Night": "late at night", "Morning": "in the mornings",
              "Afternoon": "in the afternoons", "Evening": "in the evenings"}


def _finding_clause(f: dict) -> str:
    """A short 'more X <when>' fragment for the narrative, from a finding dict."""
    emo = f["emotion_label"].lower()
    direction = "more" if f["pct"] >= 0 else "less"
    d, b = f["dimension"], f["bucket"]
    if d in TOD_DIMS and d != "part_of_day":
        when = _TOD_WORDS[HOUR_TO_PART[(int(b) + TOD_DIMS[d] // 2) % 24]]
    elif d == "part_of_day":
        when = _TOD_WORDS[b]
    elif d == "day_of_week":
        when = f"on {b}s"
    elif d == "weekend_label":
        when = "on weekends" if b == "Weekend" else "on weekdays"
    elif d == "month":
        when = f"in {_month_name(b).split()[0]}"
    elif d == "season":
        when = f"in {b}"
    else:
        when = ""
    return f"{direction} {emo} {when}".strip()


def build_narrative(name, baseline, findings, meta) -> str:
    em = baseline["emotions"]
    ranked = sorted(em.items(), key=lambda x: -x[1])
    top = [emotion_label(k).lower() for k, _ in ranked[:3]]
    low = [emotion_label(k).lower() for k, _ in ranked[-2:]]
    hours = meta["total_hours"]
    poss = _possessive(name)
    whose = "their" if poss == "Their" else poss

    s1 = (f"Across {hours:,.0f} hours of listening, {name} leans toward "
          f"{top[0]}, {top[1]}, and {top[2]} music — {low[0]} and {low[1]} "
          f"stay in the background.")

    # up to three clauses spanning different dimension classes for variety
    clauses, classes = [], set()
    for f in findings:
        cls = _dim_class(f["dimension"])
        if cls in classes:
            continue
        classes.add(cls)
        clauses.append(_finding_clause(f))
        if len(clauses) >= 3:
            break
    for f in findings:  # backfill if we couldn't get three distinct classes
        if len(clauses) >= 3:
            break
        cl = _finding_clause(f)
        if cl not in clauses:
            clauses.append(cl)

    if clauses:
        joined = (clauses[0] if len(clauses) == 1
                  else ", ".join(clauses[:-1]) + f", and {clauses[-1]}")
        s2 = f" But {whose} mood keeps a rhythm — running {joined}."
    else:
        s2 = ""
    return s1 + s2


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def analyze(history_path, gems_path, name="Listener", cfg: Config | None = None,
            warn=print):
    cfg = cfg or Config()
    plays, info = load_and_join(history_path, gems_path, warn=warn)
    plays = enrich_time(plays, cfg)

    baseline = baseline_profile(plays, info, cfg)
    profiles = build_profiles(plays, info, cfg)
    sigs = signature_tracks(plays, info, cfg)
    boards = leaderboards(plays, info)
    defining = defining_by_part(plays, info)
    discovery = discovery_by_month(plays)
    findings = find_surprises(plays, info, cfg, baseline, name=name)

    dt = plays["_dt"]
    meta = {
        "name": name,
        "date_start": dt.min().strftime("%Y-%m-%d"),
        "date_end": dt.max().strftime("%Y-%m-%d"),
        "total_minutes": round(float(plays["minutes_played"].sum()), 1),
        "total_hours": round(float(plays["minutes_played"].sum()) / 60, 1),
        "total_plays": int(len(plays)),
        "unique_tracks": int(plays["_key"].nunique()),
        "unique_artists": int(plays["artist"].nunique()),
        "weight": cfg.weight,
        "hemisphere": cfg.hemisphere,
        "coverage_plays_pct": info["coverage_plays_pct"],
        "coverage_minutes_pct": info["coverage_minutes_pct"],
        "n_emotions": len(SELECTED_EMOTIONS),
    }
    taxonomy = {
        "emotions": SELECTED_EMOTIONS,
        "emotion_labels": EMOTION_LABELS,
        "emotion_colors": EMOTION_COLORS,
        "emotion_parent": EMOTION_PARENT,
    }
    narrative = build_narrative(name, baseline, findings, meta)
    return {
        "meta": meta,
        "taxonomy": taxonomy,
        "baseline": baseline,
        "profiles": profiles,
        "signatures": sigs,
        "leaderboards": boards,
        "defining_by_part": defining,
        "discovery": discovery,
        "findings": findings,
        "narrative": narrative,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Emotion listening analysis -> results.json")
    ap.add_argument("--history", required=True)
    ap.add_argument("--gems", required=True)
    ap.add_argument("--name", default="Listener")
    ap.add_argument("--out", default="results.json")
    ap.add_argument("--weight", choices=["minutes", "plays"], default="minutes")
    ap.add_argument("--hemisphere", choices=["north", "south"], default="north")
    args = ap.parse_args()
    cfg = Config(weight=args.weight, hemisphere=args.hemisphere)
    results = analyze(args.history, args.gems, name=args.name, cfg=cfg)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    m = results["meta"]
    print(f"Join coverage: {m['coverage_plays_pct']}% plays / "
          f"{m['coverage_minutes_pct']}% minutes")
    print(f"Wrote {args.out}: {len(results['findings'])} findings, "
          f"{m['total_plays']} plays, {m['unique_tracks']} tracks")


if __name__ == "__main__":
    main()
