"""Async upload -> score -> email web service (FastAPI).

Flow: user uploads their Spotify export zip + email -> a job is queued -> a
background worker runs the pipeline (parse, dedupe against the shared track DB,
score only new tracks, analyze, build dashboard) -> emails a private link.

Single-process design (a background worker thread + a SQLite job store): no Redis
needed for v1. Uploads are deleted after processing; results live at unguessable
URLs and expire after RESULT_TTL_DAYS.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
import traceback

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# make pipeline/ importable
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (os.path.join(_ROOT, "pipeline"),):
    if p not in sys.path:
        sys.path.insert(0, p)

from orchestrate import get_library, run_pipeline   # noqa: E402
import email_send                                    # noqa: E402

DATA_DIR = os.getenv("DATA_DIR", os.path.join(_ROOT, "data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
RESULT_DIR = os.path.join(DATA_DIR, "results")
JOBS_DB = os.path.join(DATA_DIR, "jobs.db")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "60"))
RESULT_TTL_DAYS = int(os.getenv("RESULT_TTL_DAYS", "30"))
for d in (DATA_DIR, UPLOAD_DIR, RESULT_DIR):
    os.makedirs(d, exist_ok=True)

app = FastAPI(title="GEMS Emotional Listening")
_LIB = None


# --------------------------------------------------------------------------- #
# Job store (SQLite)
# --------------------------------------------------------------------------- #
class JobStore:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.execute("""CREATE TABLE IF NOT EXISTS jobs(
            id TEXT PRIMARY KEY, email TEXT, name TEXT, status TEXT, stage TEXT,
            token TEXT, error TEXT, created_at REAL, updated_at REAL)""")
        self.c.commit()

    def add(self, jid, email, name):
        with self.lock:
            self.c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                           (jid, email, name, "queued", "queued", None, None,
                            time.time(), time.time()))
            self.c.commit()

    def update(self, jid, **kw):
        kw["updated_at"] = time.time()
        sets = ",".join(f"{k}=?" for k in kw)
        with self.lock:
            self.c.execute(f"UPDATE jobs SET {sets} WHERE id=?",
                           [*kw.values(), jid])
            self.c.commit()

    def get(self, jid):
        with self.lock:
            r = self.c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return dict(r) if r else None

    def next_queued(self):
        with self.lock:
            r = self.c.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
        return dict(r) if r else None


_JOBS = JobStore(JOBS_DB)


# --------------------------------------------------------------------------- #
# Background worker
# --------------------------------------------------------------------------- #
def _process(job):
    jid, email, name = job["id"], job["email"], job["name"]
    zip_path = os.path.join(UPLOAD_DIR, f"{jid}.zip")
    token = secrets.token_urlsafe(16)
    out_html = os.path.join(RESULT_DIR, f"{token}.html")
    try:
        _JOBS.update(jid, status="running", stage="starting")

        def progress(stage, **info):
            label = stage
            if stage == "scoring":
                label = f"scoring new tracks {info.get('done',0)}/{info.get('total',0)}"
            elif stage == "dedup":
                label = f"{info.get('cached',0)} cached, {info.get('to_score',0)} new to score"
            _JOBS.update(jid, stage=label)

        summary = run_pipeline(zip_path, name or "You", out_html, _LIB,
                               progress=progress)
        url = f"{BASE_URL}/r/{token}"
        _JOBS.update(jid, status="done", stage="done", token=token)
        email_send.send_ready(email, name or "there", url, summary)
        admin = os.getenv("ADMIN_EMAIL")
        if admin:
            email_send.send_admin(admin, email, "done", url=url, summary=summary)
    except Exception as e:
        traceback.print_exc()
        _JOBS.update(jid, status="failed", stage="failed", error=str(e)[:300])
        email_send.send_failed(email, str(e)[:300])
        admin = os.getenv("ADMIN_EMAIL")
        if admin:
            email_send.send_admin(admin, email, "failed", reason=str(e)[:300])
    finally:
        try:
            os.remove(zip_path)  # retention: delete raw upload after processing
        except OSError:
            pass


def _worker_loop():
    while True:
        job = _JOBS.next_queued()
        if not job:
            time.sleep(2)
            continue
        _JOBS.update(job["id"], status="running")
        _process(job)


def _cleanup_loop():
    """Delete result files older than RESULT_TTL_DAYS."""
    while True:
        cutoff = time.time() - RESULT_TTL_DAYS * 86400
        try:
            for f in os.listdir(RESULT_DIR):
                p = os.path.join(RESULT_DIR, f)
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.remove(p)
        except OSError:
            pass
        time.sleep(6 * 3600)


@app.on_event("startup")
def _startup():
    global _LIB
    _LIB = get_library()
    print(f"Track library ready: {_LIB.count()} tracks")
    threading.Thread(target=_worker_loop, daemon=True).start()
    threading.Thread(target=_cleanup_loop, daemon=True).start()


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
_CSS = """body{margin:0;background:#0e1117;color:#e6edf3;font-family:-apple-system,
BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.6}
.wrap{max-width:560px;margin:0 auto;padding:60px 22px}h1{font-size:30px;letter-spacing:-.5px}
.lead{color:#9aa7b4}label{display:block;margin:16px 0 6px;font-size:14px}
input[type=email],input[type=text],input[type=file]{width:100%;background:#161b22;color:#e6edf3;
border:1px solid #2a323d;border-radius:9px;padding:12px;font-size:15px}
.consent{display:flex;gap:9px;font-size:13px;color:#9aa7b4;margin-top:14px}
button{margin-top:18px;background:#7c5cff;color:#fff;border:none;border-radius:9px;
padding:13px 20px;font-size:15px;font-weight:700;cursor:pointer}
.card{background:#161b22;border:1px solid #2a323d;border-radius:14px;padding:22px;margin-top:18px}
.muted{color:#9aa7b4;font-size:13px}a{color:#9bb7ff}"""

_UPLOAD_PAGE = f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Make your emotional listening dashboard</title><style>{_CSS}</style></head><body>
<div class=wrap>
  <h1>Your emotional year in music</h1>
  <p class=lead>Upload your Spotify data and we'll map every track onto 25 GEMS emotions,
     then email you a private interactive dashboard.</p>
  <div class=card>
    <form action="/upload" method=post enctype="multipart/form-data">
      <label>Your Spotify export (.zip)</label>
      <input type=file name=file accept=".zip" required>
      <p class=muted>Spotify → Privacy Settings → "Download your data" (Account data).
         It arrives by email as a zip — upload it here.</p>
      <label>Your email</label>
      <input type=email name=email placeholder="you@email.com" required>
      <label>Your name (optional)</label>
      <input type=text name=name placeholder="for your dashboard title">
      <label class=consent><input type=checkbox name=consent required>
        <span>Email me my results. I understand my listening data is processed to
        generate my dashboard and the uploaded file is deleted afterward.</span></label>
      <button type=submit>Analyze my year →</button>
    </form>
  </div>
  <p class=muted style="margin-top:14px">This can take a while if you have lots of new
     tracks (we only score songs no one's scored before). We'll email you when it's done.</p>
</div></body></html>"""


def _status_page(job):
    jid = job["id"]
    if job["status"] == "done":
        link = f"{BASE_URL}/r/{job['token']}"
        inner = (f"<h1>Your dashboard is ready 🎧</h1>"
                 f"<div class=card><a href='{link}'>Open your dashboard →</a>"
                 f"<p class=muted>We also emailed you this link.</p></div>")
        refresh = ""
    elif job["status"] == "failed":
        inner = (f"<h1>Something went wrong</h1><div class=card>"
                 f"<p>{job.get('error') or 'Unknown error.'}</p>"
                 f"<p class=muted><a href='/'>Try again →</a></p></div>")
        refresh = ""
    else:
        inner = (f"<h1>Working on your year…</h1><div class=card>"
                 f"<p>Status: <b>{job.get('stage') or job['status']}</b></p>"
                 f"<p class=muted>You can close this page — we'll email you when it's "
                 f"ready. This can take a few minutes to a few hours.</p></div>")
        refresh = "<meta http-equiv=refresh content=5>"
    return (f"<!doctype html><html><head><meta charset=utf-8>{refresh}"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Your dashboard</title><style>{_CSS}</style></head><body>"
            f"<div class=wrap>{inner}</div></body></html>")


@app.get("/", response_class=HTMLResponse)
def home():
    return _UPLOAD_PAGE


@app.get("/healthz")
def healthz():
    scored = 0
    if _LIB:
        try:
            cur = _LIB._conn.execute(
                "SELECT COUNT(*) AS n FROM tracks WHERE has_lyrics=1")
            scored = cur.fetchone()["n"]
        except Exception:
            pass
    # report only presence (booleans) of secrets, never their values
    return {
        "ok": True,
        "library_tracks": _LIB.count() if _LIB else 0,
        "library_scored": scored,
        "config": {
            "openai_key": bool(os.getenv("OPENAI_API_KEY")),
            "genius_token": bool(os.getenv("GENIUS_ACCESS_TOKEN")),
            "resend_key": bool(os.getenv("RESEND_API_KEY")),
            "from_email": os.getenv("FROM_EMAIL") or None,
            "admin_email": os.getenv("ADMIN_EMAIL") or None,
            "base_url": os.getenv("BASE_URL") or None,
            "data_dir": DATA_DIR,
        },
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...), email: str = Form(...),
                 consent: str = Form(None), name: str = Form("")):
    if not consent:
        return JSONResponse({"error": "consent required"}, status_code=400)
    if "@" not in email:
        return JSONResponse({"error": "valid email required"}, status_code=400)
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        return JSONResponse({"error": f"file too large (max {MAX_UPLOAD_MB}MB)"},
                            status_code=400)
    if not (file.filename or "").lower().endswith(".zip"):
        return JSONResponse({"error": "please upload a .zip"}, status_code=400)

    jid = secrets.token_urlsafe(10)
    with open(os.path.join(UPLOAD_DIR, f"{jid}.zip"), "wb") as f:
        f.write(data)
    _JOBS.add(jid, email.strip(), (name or "").strip())
    return RedirectResponse(f"/status/{jid}", status_code=303)


@app.get("/status/{jid}", response_class=HTMLResponse)
def status(jid: str):
    job = _JOBS.get(jid)
    if not job:
        return HTMLResponse("<p>Job not found.</p>", status_code=404)
    return _status_page(job)


@app.get("/r/{token}", response_class=HTMLResponse)
def result(token: str):
    if not token.replace("-", "").replace("_", "").isalnum():
        return HTMLResponse("Not found", status_code=404)
    path = os.path.join(RESULT_DIR, f"{token}.html")
    if not os.path.exists(path):
        return HTMLResponse("<p>This dashboard has expired or doesn't exist.</p>",
                            status_code=404)
    with open(path) as f:
        return HTMLResponse(f.read())
