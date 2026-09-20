"""Step 4: Outreach agent. Builds the A&R scorecard, writes HTML, pings Slack/Discord."""
import html
import re
from datetime import datetime

import httpx

import config
from analyst import Assessment
from scout import Track


def scorecard_score(verdict: str, a: Assessment) -> int:
    base = a.momentum * (1 - a.bot_risk / 100)
    if verdict == "REVIEW":
        base *= 0.8  # borderline calls need a human look first
    return round(base)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "track"


def render_html(track: Track, verdict: str, evidence: dict, a: Assessment, score: int) -> str:
    esc = html.escape
    color = {"HUMAN": "#1a9850", "REVIEW": "#f5a623", "AI": "#d73027"}[verdict]
    rows = "".join(
        f"<tr><td>{esc(k.replace('_', ' '))}</td><td>{esc(str(v))}</td></tr>"
        for k, v in a.metrics.items()
    )
    flags = "".join(f"<li>{esc(f)}</li>" for f in a.flags) or "<li>None</li>"
    note = (
        "<p><b>Review needed:</b> HumanStandard could not make a confident call, so listen before acting.</p>"
        if verdict == "REVIEW"
        else ""
    )
    return f"""<!doctype html><meta charset="utf-8"><title>A&amp;R Scorecard: {esc(track.title)}</title>
<body style="font-family:system-ui;max-width:640px;margin:2rem auto;color:#222">
<h1>{esc(track.title)}</h1><p>{esc(track.artist)} · <a href="{esc(track.url)}">listen</a></p>
<p><span style="background:{color};color:#fff;padding:.2rem .6rem;border-radius:4px">{esc(verdict)}</span>
 &nbsp; A&amp;R score <b>{score}/100</b> · bot risk <b>{a.bot_risk}/100</b> · momentum <b>{a.momentum}/100</b></p>
{note}<h3>Traction</h3><table cellpadding="4">{rows}</table>
<h3>Bot &amp; hype flags</h3><ul>{flags}</ul>
<h3>HumanStandard evidence</h3><pre style="white-space:pre-wrap;background:#f6f6f6;padding:.6rem">{esc(str(evidence))}</pre>
<p style="color:#888;font-size:.85em">Generated {datetime.now():%Y-%m-%d %H:%M}</p></body>"""


def write_report(track, verdict, evidence, a, score):
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORT_DIR / f"{score:03d}-{_slug(track.artist)}-{_slug(track.title)}.html"
    path.write_text(render_html(track, verdict, evidence, a, score), encoding="utf-8")
    return path


def alert(track: Track, verdict: str, a: Assessment, score: int) -> None:
    line = (
        f"*{verdict}* lead: {track.artist} - {track.title}\n"
        f"A&R score {score}/100 · bot risk {a.bot_risk} · {a.metrics['plays']:,} plays\n{track.url}"
    )
    if config.SLACK_WEBHOOK_URL:
        httpx.post(config.SLACK_WEBHOOK_URL, json={"text": line}, timeout=15)
    if config.DISCORD_WEBHOOK_URL:
        httpx.post(config.DISCORD_WEBHOOK_URL, json={"content": line}, timeout=15)
