"""Step 4: Outreach agent. Builds the A&R scorecard, writes HTML, pings Slack/Discord."""
import html
import re
from datetime import datetime

import httpx

import config
import explain
from analyst import Assessment
from scout import Track

VERDICT_LABEL = {"HUMAN": "Human", "REVIEW": "Needs review", "AI": "AI"}

STYLE = """
:root { --bg:#f5f6f8; --card:#fff; --ink:#1b1f24; --muted:#667085; --line:#e3e6ea; --accent:#3b5bdb;
        --human:#1a9850; --review:#d98a00; --ai:#d73027; --human-bg:#e6f4ec; --review-bg:#fdf1dc; --ai-bg:#fbe6e4; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1216; --card:#171b21; --ink:#e8ebef; --muted:#98a2b3; --line:#262c35; --accent:#7b93ff;
          --human:#46c37b; --review:#f0b03a; --ai:#ff6b62; --human-bg:#14301f; --review-bg:#3a2c0c; --ai-bg:#3c1815; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
.wrap { max-width:720px; margin:0 auto; padding:28px 16px 56px; }
h1 { margin:0 0 2px; font-size:24px; letter-spacing:-.01em; }
h2 { margin:0 0 10px; font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
a { color:var(--accent); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-top:14px; }
.top { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
.meta { color:var(--muted); }
.badge { display:inline-block; font-size:12px; font-weight:600; padding:2px 10px; border-radius:99px; margin-bottom:8px; }
.HUMAN .badge { background:var(--human-bg); color:var(--human); }
.REVIEW .badge { background:var(--review-bg); color:var(--review); }
.AI .badge { background:var(--ai-bg); color:var(--ai); }
.score { text-align:right; }
.score b { display:block; font-size:44px; line-height:1; letter-spacing:-.02em; }
.score span { color:var(--muted); font-size:13px; }
.pills { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
.pill { background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:6px 10px; font-size:13px; }
.pill b { font-size:15px; }
.notice { margin-top:14px; padding:10px 14px; border-radius:8px; background:var(--review-bg); color:var(--review); }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; }
.tile { background:var(--bg); border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.tile b { display:block; font-size:22px; letter-spacing:-.01em; }
.tile span { color:var(--muted); font-size:13px; }
.tile small { display:block; color:var(--muted); font-size:12px; margin-top:2px; }
.flag { color:var(--ai); margin:4px 0; }
.ok { color:var(--muted); margin:0; }
dl { margin:0; }
dt { font-weight:600; margin-top:14px; }
dt:first-child { margin-top:0; }
dd { margin:2px 0 0; }
dd.note { color:var(--muted); font-size:13px; }
.foot { color:var(--muted); font-size:12.5px; margin-top:18px; }
@media (max-width:520px) { .top { flex-direction:column; } .score { text-align:left; } }
"""


def scorecard_score(verdict: str, a: Assessment) -> int:
    base = a.momentum * (1 - a.bot_risk / 100)
    if verdict == "REVIEW":
        base *= 0.8  # borderline calls need a human look first
    return round(base)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "track"


def _age(hours: float) -> str:
    return f"{round(hours)} hours ago" if hours < 48 else f"{round(hours / 24)} days ago"


def _tile(esc, label: str, value: str, note: str = "") -> str:
    small = f"<small>{esc(note)}</small>" if note else ""
    return f"<div class='tile'><b>{esc(value)}</b><span>{esc(label)}</span>{small}</div>"


def traction_html(a: Assessment) -> str:
    esc, m = html.escape, a.metrics
    tiles = [
        _tile(esc, "plays", f"{m['plays']:,}", f"about {m['plays_per_hour']:g} per hour"),
        _tile(esc, "likes", f"{m['likes']:,}", f"{m['like_rate']:.1%} of plays"),
        _tile(esc, "reposts", f"{m['reposts']:,}"),
        _tile(esc, "comments", f"{m['comments']:,}"),
        _tile(esc, "followers", f"{m['followers']:,}", f"{m['plays_per_follower']:g} plays per follower"),
        _tile(esc, "uploaded", _age(m["age_hours"])),
    ]
    return f"<div class='grid'>{''.join(tiles)}</div>"


def bot_risk_html(a: Assessment) -> str:
    esc = html.escape
    if a.flags:
        return "".join(f"<p class='flag'>&#9888; {esc(f)}</p>" for f in a.flags)
    if a.metrics["plays"] < 1000:
        return (
            "<p class='ok'>Not enough plays to judge. The play-farming checks start at around "
            "1,000 plays, so a score of 0 here means no data, not a clean bill of health.</p>"
        )
    return "<p class='ok'>No suspicious patterns found: plays, likes, comments and followers look consistent.</p>"


def evidence_html(verdict: str, evidence: dict) -> str:
    """The HumanStandard result in plain language, each field with a one-line explanation."""
    e = explain.explain(verdict, evidence)
    esc = html.escape
    rows = "".join(
        f"<dt>{esc(i['label'])}</dt><dd>{esc(i['value'])}</dd><dd class='note'>{esc(i['note'])}</dd>"
        for i in e["items"]
    )
    footer = f"<p class='foot'>{esc(e['footer'])}</p>" if e["footer"] else ""
    return f"<p><b>{esc(e['headline'])}</b></p><dl>{rows}</dl>{footer}"


def render_html(track: Track, verdict: str, evidence: dict, a: Assessment, score: int) -> str:
    esc = html.escape
    url = track.url if track.url.startswith("https://") else "#"
    notice = (
        "<div class='notice'><b>Review needed.</b> HumanStandard could not make a confident call, "
        "so listen before acting.</div>"
        if verdict == "REVIEW"
        else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A&amp;R Scorecard: {esc(track.title)}</title><style>{STYLE}</style></head>
<body><div class="wrap {esc(verdict)}">
<div class="card"><div class="top">
  <div>
    <span class="badge">{esc(VERDICT_LABEL[verdict])}</span>
    <h1>{esc(track.title)}</h1>
    <div class="meta">{esc(track.artist)} &middot; <a href="{esc(url)}" target="_blank" rel="noopener">listen on SoundCloud</a></div>
  </div>
  <div class="score"><b>{score}</b><span>A&amp;R score (0-100)</span></div>
</div>
<div class="pills">
  <span class="pill">Momentum <b>{a.momentum}</b>/100</span>
  <span class="pill">Bot risk <b>{a.bot_risk}</b>/100</span>
</div>{notice}</div>
<div class="card"><h2>Traction</h2>{traction_html(a)}</div>
<div class="card"><h2>Bot &amp; play-farming check</h2>{bot_risk_html(a)}</div>
<div class="card"><h2>HumanStandard evidence</h2>{evidence_html(verdict, evidence)}</div>
<p class="foot">Generated {datetime.now():%Y-%m-%d %H:%M}. The A&amp;R score is a heuristic for ranking leads, not a prediction.</p>
</div></body></html>"""


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
