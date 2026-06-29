# Deploying the upload → score → email service (Railway + Resend)

The backend is a single FastAPI app with an in-process background worker and a
SQLite track library. It runs anywhere that can run a Docker container with a
persistent volume. These steps use **Railway** (your chosen host) and **Resend**
(email).

## What runs

```
upload zip + email  ──▶  job queued  ──▶  worker:
   parse export → dedupe vs shared track DB → score ONLY new tracks (Genius + GPT)
   → write new scores back to the DB → analyze → build dashboard.html
   ──▶ email a private link.  Raw upload deleted after processing.
```

## 1. Run it locally first (optional sanity check)

```bash
cp .env.example .env          # fill in OPENAI_API_KEY + GENIUS_ACCESS_TOKEN
docker compose up --build     # open http://localhost:8000
```
Without a `RESEND_API_KEY` the "email" is printed to the log (dev mode) — the rest
of the flow still works.

## 2. Resend (email)

1. Sign up at https://resend.com, create an **API key** → that's `RESEND_API_KEY`.
2. To email **arbitrary** users (not just yourself), **verify a sending domain**
   in Resend and set `FROM_EMAIL` to an address on it (e.g. `hello@yourdomain.com`).
   Without a verified domain, Resend only delivers to your own address (fine for testing).

## 3. Railway (host)

1. https://railway.app → **New Project → Deploy from GitHub repo** → pick
   `Spotify_Agent_Emotion_Analyzer`. Railway detects the `Dockerfile` / `railway.json`.
2. **Add a Volume** to the service, mount path **`/data`** (persists the track
   library, jobs, and results across deploys — important so the cost-saving cache
   survives restarts).
3. **Variables** (Settings → Variables) — these are the only "secrets" you need:

   | Variable | Value |
   |---|---|
   | `OPENAI_API_KEY` | your OpenAI key |
   | `GENIUS_ACCESS_TOKEN` | your Genius token |
   | `RESEND_API_KEY` | your Resend key |
   | `FROM_EMAIL` | a verified-domain sender address |
   | `BASE_URL` | your public Railway URL, e.g. `https://your-app.up.railway.app` |
   | `DATA_DIR` | `/data` |
   | `TRACK_DB_PATH` | `/data/track_library.db` |

4. Deploy. Health check is `GET /healthz`. The upload form is the service root `/`.

## 4. Point the demo's "Make your own" at the service

In `docs/index.html`, change the signup form into a link/redirect to your Railway
upload page (`https://your-app.up.railway.app/`), then commit + push so GitHub
Pages picks it up.

## 5. (Optional) seed the shared track library

The full seed CSV (Anna's 3,985 scored tracks, with lyrics) is gitignored, so a
fresh Railway deploy starts with an **empty** library and fills as users upload.
To give it a head start without publishing copyrighted lyrics, generate a
lyrics-stripped seed and commit it as `data/track_seed.csv`:

```bash
python -c "import pandas as pd; df=pd.read_csv('annas_tracks_gems_scored.csv'); \
df.drop(columns=['lyrics']).to_csv('data/track_seed.csv', index=False)"
```
The app auto-seeds from `data/track_seed.csv` on first run if present.

## Notes / limits (v1)

- One job processes at a time (single worker). Fine for low volume; split into a
  separate worker + Redis queue when traffic grows.
- Users with many brand-new tracks take longer (each new track = one Genius fetch +
  one GPT call, ~1s). Returning catalog tracks are free (cache hits).
- Uploads are deleted after processing; results expire after `RESULT_TTL_DAYS` (30).
- GPT-4o-mini scoring is ~fractions of a cent per *new* track; the shared cache means
  each unique track is paid for once, ever.
```
