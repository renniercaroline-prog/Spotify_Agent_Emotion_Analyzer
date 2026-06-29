# Deploying the demo to GitHub Pages

The `docs/` folder is a fully static site (plain HTML/CSS/JS + Chart.js from a CDN).
No build step. Three files matter:

- `index.html` — landing page with Anna's headline findings + the email signup form.
- `dashboard.html` — Anna's full interactive dashboard (self-contained; all data inlined).
- (`dashboard_results.json` is written alongside but gitignored — the dashboard inlines its own data.)

## Enable GitHub Pages (one time)

1. Push `main` to GitHub (already done if you're reading this in the repo).
2. Repo **Settings → Pages → Build and deployment**
   - **Source:** Deploy from a branch
   - **Branch:** `main`  **Folder:** `/docs`  → **Save**
3. Wait ~1 minute. Your site goes live at:
   `https://renniercaroline-prog.github.io/Spotify_Agent_Emotion_Analyzer/`

## Regenerate Anna's dashboard

From the repo root:

```bash
python3 analysis/run.py \
  --history annas_listening_history.csv \
  --gems    annas_tracks_gems_scored.csv \
  --name    "Anna" \
  --out     docs/dashboard.html
```

Then commit & push `docs/dashboard.html`; Pages redeploys automatically.

## Email signup (Formspree)

`index.html` posts the signup form to **Formspree**. To activate it:

1. Create a free account at https://formspree.io and add a new form.
2. Copy its endpoint id (the `xyzabcd` part of `https://formspree.io/f/xyzabcd`).
3. In `index.html`, replace `YOUR_FORM_ID` in the `<form action="...">` with that id.
4. Commit & push. Submissions now arrive in your Formspree inbox / email.

The form id is **not a secret** — it's a public endpoint, safe to commit. (Formspree's
free tier is email submissions only; file upload + real GEMS scoring come with Part B.)

## Check before publishing

- Open `docs/index.html` and `docs/dashboard.html` locally (`python3 -m http.server
  --directory docs`) — every chart should draw, no console errors.
- Confirm **no secrets or raw PII** are committed: `.env`, the `Spotify Account Data/`
  export, the raw `annas_*` CSVs, the paper PDF, the build spec, and the notebooks are all
  gitignored. The committed `dashboard.html` contains only aggregate emotional data for the
  consented demo subject.
