"""Email delivery via Resend, with a console fallback for local/dev.

Set RESEND_API_KEY + FROM_EMAIL to send for real. Without a key, the email is
printed to the log so the whole flow still works locally.
"""
from __future__ import annotations

import os

import requests


def _brand_html(title: str, body_html: str, cta_url: str | None = None,
                cta_label: str = "Open your dashboard") -> str:
    btn = (f'<a href="{cta_url}" style="display:inline-block;background:#7c5cff;'
           f'color:#fff;text-decoration:none;padding:12px 22px;border-radius:9px;'
           f'font-weight:700">{cta_label}</a>' if cta_url else "")
    return f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      max-width:520px;margin:0 auto;color:#1a1a1a">
      <h1 style="font-size:22px;margin:0 0 12px">{title}</h1>
      <div style="font-size:15px;line-height:1.6;color:#333">{body_html}</div>
      <p style="margin:22px 0">{btn}</p>
      <p style="font-size:12px;color:#888;border-top:1px solid #eee;padding-top:14px">
        GEMS scores are AI-derived proxies for each track's emotional character, not
        measured feelings. Your uploaded data is deleted after processing.</p>
    </div>"""


def send_email(to: str, subject: str, html: str) -> bool:
    key = os.getenv("RESEND_API_KEY")
    frm = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
    if not key:
        print(f"[email:console] to={to} subject={subject!r}\n{html}\n")
        return False
    try:
        r = requests.post("https://api.resend.com/emails",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"from": frm, "to": [to], "subject": subject,
                                "html": html}, timeout=20)
        if r.status_code >= 300:
            print(f"[email:error] {r.status_code} {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[email:error] {e}")
        return False


def send_ready(to: str, name: str, url: str, summary: dict) -> bool:
    body = (f"Your emotional listening dashboard is ready. We analyzed "
            f"<b>{summary.get('plays', 0):,} plays</b> across "
            f"<b>{summary.get('unique_tracks', 0):,} tracks</b> and scored them on "
            f"25 GEMS emotions.<br><br>The link below is private to you.")
    html = _brand_html(f"{name}, your emotional year is ready 🎧", body, url)
    return send_email(to, "Your emotional listening dashboard is ready", html)


def send_admin(admin: str, user_email: str, status: str,
               url: str = None, summary: dict = None, reason: str = None) -> bool:
    """Send the operator a copy/notification of each run, for quality monitoring."""
    if status == "done":
        s = summary or {}
        body = (f"Dashboard generated for <b>{user_email}</b>.<br><br>"
                f"plays: {s.get('plays', 0):,} · tracks: {s.get('unique_tracks', 0):,} "
                f"({s.get('newly_fetched', 0)} new scored) · "
                f"coverage: {s.get('coverage_pct', '?')}% · "
                f"findings: {s.get('findings', 0)}")
        html = _brand_html("New dashboard generated", body, url, "View dashboard")
        return send_email(admin, f"[GEMS] dashboard for {user_email}", html)
    body = f"Processing FAILED for <b>{user_email}</b>:<br><br><i>{reason}</i>"
    html = _brand_html("A dashboard run failed", body)
    return send_email(admin, f"[GEMS] FAILED for {user_email}", html)


def send_failed(to: str, reason: str) -> bool:
    body = (f"We hit a problem processing your Spotify data:<br><br>"
            f"<i>{reason}</i><br><br>Please double-check you uploaded the Spotify "
            f"<b>Account data</b> zip (it contains StreamingHistory_music_*.json) "
            f"and try again.")
    html = _brand_html("We couldn't finish your dashboard", body)
    return send_email(to, "There was a problem with your dashboard", html)
