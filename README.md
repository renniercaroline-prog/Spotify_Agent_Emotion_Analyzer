# Music Emotion Analyzer Agent

An agentic LLM pipeline that turns a year of someone's Spotify history into an interactive
emotional dashboard — autonomously fetching each track's lyrics, scoring them across the 25
emotions of the **Geneva Emotional Music Scale (GEMS)**, running weighted statistics with
permutation tests to surface the most surprising patterns, and emailing the finished result,
all from a single upload.

**[▶ Live demo](https://renniercaroline-prog.github.io/Spotify_Agent_Emotion_Analyzer/)**
 · **[Try it on your own data](https://spotifyagentemotionanalyzer-production.up.railway.app/)**

---

## What it does

A person downloads their Spotify data, uploads the zip, and enters their email. A while later
they get a private link to a personalized dashboard revealing the emotional patterns in how
they listen — across the day, week, month, and seasons — with the most statistically
distinctive findings written out in plain English, e.g.:

> *"In October, your listening ran 39% more **triumphant** than your yearly average (p < 0.001)."*

It ships in two parts:

- **Public demo** — a static GitHub Pages site showing the full experience on one consented,
  pre-scored subject ("Anna").
- **The live product** — an upload → score → email service that does the GEMS scoring for new
  people and generates their dashboard, fully hands-off.

## The agent

This isn't a single LLM call — it's an **autonomous, multi-step pipeline** that decomposes one
goal ("profile this person's emotional listening") into a chain of tool-using steps and runs
them end to end without supervision:

1. **Parse** the Spotify export (handles both the basic and extended formats).
2. **Dedupe** the user's tracks against a **shared knowledge store** of already-scored songs.
3. For each *new* track, **fetch lyrics** from web lyric APIs.
4. **Score** the lyrics across 45 GEMS items with `gpt-4o-mini` (structured JSON output).
5. **Write** new scores back to the shared store, so every track is paid for **once, ever**.
6. **Analyze** — minutes-weighted emotion profiles, deviations from a personal baseline,
   multi-resolution time analysis, and a surprise-ranking engine validated by permutation tests.
7. **Generate** a self-contained interactive dashboard.
8. **Deliver** it by email — and notify the operator with QA stats.

The store is also **self-healing** (failed lookups are retried later) and the job queue
**resumes interrupted work** after a restart — the robustness an autonomous, long-running agent
needs to run unattended.

## Grounded in research

The scoring methodology comes directly from my paper, *The Role of Emotion in Music Popularity
Prediction* (University of Edinburgh). That work constructs proxy GEMS emotion scores for tracks
by prompting **GPT-4-class models to rate lyrics on the 45 GEMS items** — the exact technique
this product uses — and then **validates that those LLM-derived proxies capture genuine
emotional structure**: projected with multidimensional scaling, they recover the valence and
arousal axes of Russell's circumplex model of affect, with emotion clusters separating as
theory predicts. In other words, the paper provides the evidence that these scores are
*meaningful*, not noise — which is what justifies building analytics on top of them.

The paper also found that emotion features carry real, standalone predictive signal
(R² ≈ 0.24–0.30 on popularity) even where they're redundant with opaque learned representations,
and its future-work section proposes turning those interpretability findings into "a practical
emotion-profiling tool." **This project is that tool**, applied at the listener level: where the
paper asked *does emotion predict popularity?*, this asks *what does a person's emotional
listening look like, and how does it shift over time?* — a descriptive, personal application of
the same validated GEMS-via-LLM foundation.

> Note: GEMS scores describe the **music's** emotional character (an LLM-derived proxy), not a
> measurement of the listener's feelings — consistent with how the paper frames them.

## How the analysis works

- **Weighting** — every aggregate is weighted by **minutes listened**, so skips matter less and
  results reflect emotional *exposure*, not just play counts.
- **Personal baseline** — each pattern is expressed as a deviation from that person's own
  minutes-weighted mean. The story is how someone differs from their own norm.
- **Multi-resolution time** — time-of-day patterns are mined at several chunk sizes (2h / 3h /
  6h) and the engine surfaces whichever resolution shows the cleanest natural pattern.
- **Surprise-ranking engine** — scores every `(dimension, bucket, emotion)` cell by standardized
  effect size, gates on listening volume, validates candidates with **permutation tests**
  (no normality assumption), then balances the headline list across dimensions so no single lens
  dominates. Findings are templated to plain English — the analysis stage runs fully offline.

## Architecture

```
analysis/            # shared engine (used by both the demo and the live service)
  taxonomy.py        # the 25 emotions, labels, family colors
  analyze.py         # join + weighted profiles + permutation-tested surprise engine
  dashboard.py       # results -> single self-contained interactive dashboard.html (Chart.js)
  run.py             # CLI: history + gems -> dashboard.html
docs/                # Part A: static GitHub Pages demo (Anna)
pipeline/            # Part B: the agent
  gems.py            # 45-item GEMS taxonomy + cluster averages
  track_library.py   # shared scored-track store (SQLite), seeded + self-healing
  parse_export.py    # Spotify export zip -> per-play history
  lyrics.py          # lyric retrieval via LRCLIB + lyrics.ovh (no key, server-friendly)
  gems_scoring.py    # gpt-4o-mini GEMS scoring
  orchestrate.py     # end-to-end: zip -> dedupe -> score -> analyze -> dashboard
service/             # Part B: async web service
  app.py             # FastAPI: upload, background worker, status pages, results, admin
  email_send.py      # Resend delivery (+ console fallback in dev)
Dockerfile · docker-compose.yml · railway.json · .env.example
```

## Run it

**The dashboard engine (no keys needed):**
```bash
pip install -r requirements.txt
python3 analysis/run.py --history annas_listening_history.csv \
  --gems annas_tracks_gems_scored.csv --name "Anna" --out docs/dashboard.html
python3 -m http.server --directory docs 8765      # open http://localhost:8765/
```

**The full service locally:**
```bash
cp .env.example .env        # add OPENAI_API_KEY (lyrics need no key)
docker compose up --build   # open http://localhost:8000
```
Deploy (Railway + Resend): see [service/DEPLOY_SERVICE.md](service/DEPLOY_SERVICE.md).

## Privacy & ethics

Uploaded data is processed only to generate the dashboard and the **raw upload is deleted after
processing**; results live at unguessable URLs and expire. The shared track store holds **track
data only — never user identity**. Secrets and raw personal data are gitignored. GEMS scores are
disclosed throughout as proxies for the music's emotional character, not the listener's feelings.

## Tech stack

Python · FastAPI · SQLite · OpenAI `gpt-4o-mini` · pandas/numpy · Chart.js · Resend · Docker ·
Railway · GitHub Pages.
