# Spotify Emotional-Pattern Analysis (GEMS)

Maps a person's Spotify listening onto **25 curated emotions** from the **Geneva
Emotional Music Scale (GEMS)** and surfaces the most statistically surprising patterns
in *how they feel* across the day, week, and seasons.

Two deliverables (see `CLAUDE_CODE_BUILD_PROMPT.md` for the full spec):

- **Part A — public demo (built):** a static site showing the full experience on one
  already-scored subject ("Anna").
- **Part B — the product (not yet built):** upload → email → async GEMS scoring →
  emailed dashboard for new people.

## What's built so far (Part A)

```
analysis/
  taxonomy.py     # the 25 emotions, labels, family colors (single source of truth)
  analyze.py      # load + join + weighted profiles + surprise-ranking engine -> results dict
  dashboard.py    # results -> single self-contained interactive dashboard.html (Chart.js CDN)
  run.py          # CLI: history + gems -> dashboard.html
docs/             # published by GitHub Pages
  index.html      # landing page (Anna's teaser + email signup)
  dashboard.html  # Anna's full interactive dashboard (generated)
  DEPLOY.md       # GitHub Pages instructions
```

## Quick start

```bash
pip install -r requirements.txt

python3 analysis/run.py \
  --history annas_listening_history.csv \
  --gems    annas_tracks_gems_scored.csv \
  --name    "Anna" \
  --out     docs/dashboard.html

# preview locally
python3 -m http.server --directory docs 8765   # then open http://localhost:8765/
```

Flags: `--weight {minutes,plays}` (default minutes), `--hemisphere {north,south}`
(default north — affects season labels).

## How the analysis works

- **Join:** each play is matched to its track's GEMS vector by `spotify_uri`, falling
  back to a normalized `artist|||track` key. Coverage is printed; warns if < 95%
  (Anna reaches 100%).
- **Weighting:** every aggregate is weighted by **minutes listened**, so skips matter
  less and results reflect emotional *exposure*.
- **Baseline:** each person's own minutes-weighted mean. Every pattern is expressed as a
  deviation from that personal baseline.
- **Time resolution:** time-of-day patterns are mined at **multiple chunk sizes (2h / 3h /
  6h)** and the engine surfaces whichever resolution shows the cleanest natural pattern
  (overlapping windows are de-duplicated). Raw single hours are too noisy for findings but
  remain available as the hour-by-hour "emotional clock" chart.
- **Surprise engine:** scores every `(dimension, bucket, emotion)` cell by standardized
  effect size, gates on listening volume, permutation-tests a per-dimension pool (so quieter
  month/season lenses get a fair shot), then **balances the headline list across dimension
  classes** (≤3 time-of-day, ≤2 day-of-week, ≤2 month, ≤2 season) so no single lens
  dominates. Emits plain-English findings + an overall listener statement. Fully offline.

## Privacy / data

GEMS scores are **LLM-derived proxies for each track's emotional character**, not
measured listener feelings. The raw per-play CSVs, the `Spotify Account Data/` export,
and `.env` are **gitignored**. The committed Anna `dashboard.html` contains only
aggregate emotional data for the consented demo subject.

## Part B — the upload → score → email service (built)

```
pipeline/
  gems.py           # full 45-item GEMS taxonomy + cluster averages (scoring superset)
  track_library.py  # shared scored-track DB (SQLite); each track scored once, ever
  parse_export.py   # parse Spotify export zip (basic + extended formats) -> plays
  lyrics.py         # Genius search + scrape
  gems_scoring.py   # gpt-4o-mini GEMS scoring (same prompt as the notebook)
  orchestrate.py    # zip -> dedupe vs library -> score misses -> analyze -> dashboard
service/
  app.py            # FastAPI: upload form, background worker, status, results
  email_send.py     # Resend delivery (console fallback in dev)
  DEPLOY_SERVICE.md # Railway + Resend deploy guide
Dockerfile, docker-compose.yml, railway.json, .env.example
```

Run locally: `cp .env.example .env` (add `OPENAI_API_KEY` + `GENIUS_ACCESS_TOKEN`),
then `docker compose up --build` and open http://localhost:8000. Deploy: see
[service/DEPLOY_SERVICE.md](service/DEPLOY_SERVICE.md). The shared track library means
each unique track is fetched + scored **once across all users**, so API cost trends
toward zero as the catalog fills in.
