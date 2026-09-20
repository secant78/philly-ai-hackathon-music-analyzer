"""Step 4: Outreach agent. Builds the A&R scorecard, writes HTML, pings Slack/Discord."""
import html
import re
from datetime import datetime

import httpx

import analyst
import config
import explain
from analyst import Assessment
from scout import Track

VERDICT_LABEL = {"HUMAN": "Human", "REVIEW": "Needs review", "AI": "AI"}
esc = html.escape

STYLE = """
:root { --bg:#f4f5fa; --card:#fff; --ink:#161a2b; --muted:#5f6680; --line:#e4e6f0; --soft:#f0f1f8; --accent:#5b3df5;
        --human:#12915a; --review:#c9820a; --ai:#d6352c; --human-bg:#e3f5ec; --review-bg:#fcefd6; --ai-bg:#fbe5e3;
        --shadow:0 1px 2px rgba(22,26,43,.05),0 6px 18px rgba(22,26,43,.06);
        --hero:linear-gradient(135deg,#3a27c9 0%,#5b3df5 55%,#8a5cff 100%); }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0d0f1a; --card:#161928; --ink:#eceefa; --muted:#9aa1bf; --line:#262b41; --soft:#1d2136; --accent:#8d78ff;
          --human:#45c98a; --review:#f2b13f; --ai:#ff6d63; --human-bg:#12301f; --review-bg:#38290b; --ai-bg:#3b1714;
          --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
          --hero:linear-gradient(135deg,#1a1450 0%,#2d1f7a 60%,#45298f 100%); }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); -webkit-font-smoothing:antialiased;
       font:15px/1.5 "Segoe UI Variable",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
a { color:var(--accent); }
.wrap { max-width:760px; margin:0 auto; padding:0 18px; }

.hero { background:var(--hero); color:#fff; padding:18px 0 92px; position:relative; overflow:hidden; }
.hero::after { content:""; position:absolute; right:-90px; top:-130px; width:360px; height:360px; border-radius:50%;
               background:radial-gradient(circle,rgba(255,255,255,.16),transparent 68%); }
.hero .wrap { position:relative; z-index:1; }
.back { color:#fff; opacity:.8; text-decoration:none; font-size:13.5px; }
.back:hover { opacity:1; }
.who { display:flex; gap:16px; align-items:center; margin-top:16px; }
.avatar { width:60px; height:60px; border-radius:18px; display:grid; place-items:center; font-size:26px; font-weight:700;
          color:#fff; flex:none; box-shadow:0 4px 14px rgba(0,0,0,.25); }
.who h1 { margin:0; font-size:26px; letter-spacing:-.02em; line-height:1.2; overflow-wrap:anywhere; }
.who .sub { opacity:.85; margin-top:4px; font-size:14.5px; }
.who .sub a { color:#fff; }
.badge { display:inline-block; font-size:12px; font-weight:650; padding:2px 11px; border-radius:99px; margin-bottom:6px; background:#fff; }
.HUMAN .badge { color:var(--human); } .REVIEW .badge { color:var(--review); } .AI .badge { color:var(--ai); }

.summary { background:var(--card); border:1px solid var(--line); border-radius:18px; box-shadow:var(--shadow); margin-top:-64px;
           padding:20px 22px; display:flex; gap:22px; align-items:center; flex-wrap:wrap; position:relative; z-index:2; }
.ring { --p:0; --c:var(--human); width:92px; height:92px; border-radius:50%; display:grid; place-items:center; flex:none; position:relative;
        background:conic-gradient(var(--c) calc(var(--p) * 1%), var(--soft) 0); }
.ring::before { content:""; position:absolute; inset:8px; border-radius:50%; background:var(--card); }
.ring b { position:relative; font-size:32px; letter-spacing:-.03em; }
.summary .txt { flex:1; min-width:200px; }
.summary .txt b { font-size:17px; }
.summary .txt p { margin:3px 0 0; color:var(--muted); font-size:14px; }
.notice { margin-top:12px; padding:10px 14px; border-radius:10px; background:var(--review-bg); color:var(--review); font-size:14px; }

.how { flex-basis:100%; border-top:1px solid var(--line); padding-top:16px; }
.how h3 { margin:0 0 12px; font-size:12.5px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
.hrow { display:grid; grid-template-columns:120px 1fr 36px; gap:3px 14px; align-items:center; margin-bottom:12px; }
.hn b { display:block; font-size:14px; }
.hn span { color:var(--muted); font-size:12px; }
.hbar { height:8px; background:var(--soft); border-radius:99px; overflow:hidden; }
.hbar i { display:block; height:100%; background:var(--accent); border-radius:99px; }
.hv { text-align:right; font-weight:700; }
.hd { grid-column:2 / -1; color:var(--muted); font-size:12.5px; }
.hsum { margin:6px 0 0; padding:10px 14px; background:var(--soft); border-radius:10px; font-size:13.5px; }
.hsum div + div { margin-top:3px; }
.hsum .adj { color:var(--review); }
@media (max-width:520px) { .hrow { grid-template-columns:1fr 36px; } .hbar { grid-column:1; } .hd { grid-column:1 / -1; } }
.card { background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); padding:18px 20px; margin-top:14px; }
h2 { margin:0 0 12px; font-size:12.5px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }

.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); border:1px solid var(--line); border-radius:12px; background:var(--soft); overflow:hidden; }
.stat { padding:12px 10px; text-align:center; border-left:1px solid var(--line); }
.stat:first-child { border-left:0; }
.stat b { display:block; font-size:22px; letter-spacing:-.02em; }
.stat span { color:var(--muted); font-size:12.5px; display:block; }
.stat small { color:var(--muted); font-size:11.5px; opacity:.85; }

.flag { color:var(--ai); background:var(--ai-bg); border-radius:8px; padding:6px 12px; margin:6px 0 0; font-size:14px; }

.verdict { display:flex; gap:12px; align-items:center; padding:12px 14px; border-radius:12px; font-weight:600; margin-bottom:6px; }
.HUMAN .verdict { background:var(--human-bg); color:var(--human); }
.REVIEW .verdict { background:var(--review-bg); color:var(--review); }
.AI .verdict { background:var(--ai-bg); color:var(--ai); }
.item { padding:14px 0; border-top:1px solid var(--line); }
.item:first-of-type { border-top:0; }
.item h3 { margin:0; font-size:15px; }
.item .val { margin-top:2px; }
.item .note { color:var(--muted); font-size:13px; margin-top:3px; }

.meter { position:relative; height:10px; border-radius:99px; margin:12px 0 4px;
         background:linear-gradient(90deg,var(--ai-bg),var(--review-bg) 45%,var(--human-bg)); border:1px solid var(--line); }
.meter i { position:absolute; top:-5px; width:18px; height:18px; border-radius:50%; background:var(--ink); border:3px solid var(--card); transform:translateX(-50%); }
.scale { display:flex; justify-content:space-between; color:var(--muted); font-size:11.5px; }

.dots { display:grid; grid-template-columns:repeat(25,1fr); gap:4px; max-width:420px; margin:10px 0 6px; }
.dot { aspect-ratio:1; border-radius:50%; background:var(--ai); }
.dot.h { background:var(--human); }
.key { display:flex; gap:16px; color:var(--muted); font-size:12.5px; }
.key i { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; }

.tl { display:flex; align-items:flex-end; gap:2px; height:70px; margin:12px 0 4px; padding-bottom:1px; border-bottom:1px solid var(--line); position:relative; }
.tl::before { content:""; position:absolute; left:0; right:0; bottom:50%; border-top:1px dashed var(--line); }
.tl i { flex:1; min-width:2px; border-radius:3px 3px 0 0; background:var(--human); opacity:.85; }
.tl i.hi { background:var(--ai); opacity:1; }

.foot { color:var(--muted); font-size:12.5px; text-align:center; margin:22px 0 40px; }
@media (max-width:520px) { .who h1 { font-size:21px; } .dots { grid-template-columns:repeat(13,1fr); } }
"""


def scorecard_score(verdict: str, a: Assessment) -> int:
    base = a.momentum * (1 - a.bot_risk / 100)
    if verdict == "REVIEW":
        base *= 0.8  # borderline calls need a human look first
    return round(base)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "track"


def _age(hours: float) -> str:
    return f"{round(hours)}h ago" if hours < 48 else f"{round(hours / 24)}d ago"


def _avatar_color(name: str) -> str:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) % 360
    return f"hsl({h} 52% 46%)"


def traction_html(a: Assessment) -> str:
    m = a.metrics
    cells = [
        (f"{m['plays']:,}", "plays", f"~{m['plays_per_hour']:g} per hour"),
        (f"{m['likes']:,}", "likes", f"{m['like_rate']:.1%} of plays"),
        (f"{m['reposts']:,}", "reposts", ""),
        (f"{m['comments']:,}", "comments", ""),
        (f"{m['followers']:,}", "followers", f"{m['plays_per_follower']:g} plays each"),
        (_age(m["age_hours"]), "uploaded", ""),
    ]
    return "<div class='stats'>" + "".join(
        f"<div class='stat'><b>{esc(v)}</b><span>{esc(label)}</span>"
        + (f"<small>{esc(note)}</small>" if note else "")
        + "</div>"
        for v, label, note in cells
    ) + "</div>"


def how_html(verdict: str, a: Assessment, score: int) -> str:
    """Show where this track's score came from, using its own numbers."""
    m = a.metrics
    eng, reach = analyst.momentum_parts(m["plays"], m["likes"], m["reposts"], m["comments"])
    e, r = round(eng * 100), round(reach * 100)
    raw = round(eng * 60 + reach * 40)
    rows = [
        ("Engagement", "60% of momentum", e,
         f"{m['likes']:,} likes, {m['reposts']:,} reposts and {m['comments']:,} comments on {m['plays']:,} plays. "
         "Comments count most, then reposts, then likes."),
        ("Reach", "40% of momentum", r,
         f"{m['plays']:,} plays, on a scale where about 100,000 plays is the maximum."),
    ]
    body = "".join(
        f"<div class='hrow'><div class='hn'><b>{esc(n)}</b><span>{esc(w)}</span></div>"
        f"<div class='hbar'><i style='width:{v}%'></i></div><div class='hv'>{v}</div>"
        f"<div class='hd'>{esc(d)}</div></div>"
        for n, w, v, d in rows
    )
    lines = [f"<div>Momentum = 60% &times; {e} + 40% &times; {r} = <b>{raw}</b></div>"]
    after_penalty = round(a.momentum * (1 - a.bot_risk / 100))  # the score applies the penalty on top of momentum
    if raw - after_penalty > 0:
        lines.append(
            f"<div class='adj'>Play-farming penalty: &minus;{raw - after_penalty} points for suspicious play patterns</div>"
        )
    if verdict == "REVIEW":
        lines.append("<div class='adj'>Borderline HumanStandard verdict: score reduced by 20%</div>")
    lines.append(f"<div><b>A&amp;R score = {score}</b></div>")
    return f"<div class='how'><h3>How this score is calculated</h3>{body}<div class='hsum'>{''.join(lines)}</div></div>"


def play_warning_html(a: Assessment) -> str:
    """A warning card, only when a play-farming pattern was detected."""
    if not a.flags:
        return ""
    items = "".join(f"<p class='flag'>&#9888; {esc(f)}</p>" for f in a.flags)
    return f"<div class='card'><h2>Suspicious plays</h2>{items}</div>"


def _meter(conf: float) -> str:
    pos = max(0.0, min(1.0, (conf - 0.5) / 0.5)) * 100
    return (
        f"<div class='meter'><i style='left:{pos:.0f}%'></i></div>"
        "<div class='scale'><span>0.5 coin flip</span><span>1.0 overwhelming</span></div>"
    )


def _neighbors(evidence: dict) -> str:
    counts = ((evidence.get("origin_map") or {}).get("neighborhood") or {}).get("counts") or {}
    dots = "".join(
        f"<i class='dot {'h' if name.lower() == 'human' else ''}' title='{esc(name)}'></i>"
        for name, c in counts.items()
        for _ in range(int(c))
    )
    if not dots:
        return ""
    return (
        f"<div class='dots'>{dots}</div>"
        "<div class='key'><span><i style='background:var(--human)'></i>verified human recording</span>"
        "<span><i style='background:var(--ai)'></i>AI-generated</span></div>"
    )


def _timeline(evidence: dict) -> str:
    tl = evidence.get("risk_timeline") or []
    if not tl:
        return ""
    bars = "".join(
        f"<i class='{'hi' if r >= 0.5 else ''}' style='height:{max(4, round(r * 100))}%' title='{r:.0%} AI risk'></i>"
        for r in tl
    )
    return (
        f"<div class='tl'>{bars}</div>"
        "<div class='scale'><span>start of track</span><span>dashed line = 50% risk</span><span>end</span></div>"
    )


def evidence_html(verdict: str, evidence: dict) -> str:
    """The HumanStandard result in plain language, with a small visual for each measure."""
    e = explain.explain(verdict, evidence)
    visuals = {
        "How sure": _meter(evidence["confidence"]) if evidence.get("confidence") is not None else "",
        "How does it compare": _neighbors(evidence),
        "Any AI-like": _timeline(evidence),
    }
    rows = []
    for i in e["items"]:
        extra = next((v for k, v in visuals.items() if i["label"].startswith(k)), "")
        rows.append(
            f"<div class='item'><h3>{esc(i['label'])}</h3><div class='val'>{esc(i['value'])}</div>"
            f"{extra}<div class='note'>{esc(i['note'])}</div></div>"
        )
    footer = f"<p class='foot' style='margin:12px 0 0;text-align:left'>{esc(e['footer'])}</p>" if e["footer"] else ""
    return f"<div class='verdict'>{esc(e['headline'])}</div>{''.join(rows)}{footer}"


def render_html(track: Track, verdict: str, evidence: dict, a: Assessment, score: int) -> str:
    url = track.url if track.url.startswith("https://") else "#"
    initial = esc((list(track.artist.strip()) or ["?"])[0].upper())
    ring_color = "var(--review)" if verdict == "REVIEW" else "var(--human)"
    notice = (
        "<div class='notice'><b>Review needed.</b> HumanStandard could not make a confident call, "
        "so listen before acting.</div>"
        if verdict == "REVIEW"
        else ""
    )
    blurb = {
        "HUMAN": "Verified as human-made with real listener traction. A good candidate for a first listen.",
        "REVIEW": "The detector was not confident either way. Traction is real, but a person should listen first.",
    }.get(verdict, "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A&amp;R Scorecard: {esc(track.title)}</title><style>{STYLE}</style></head>
<body class="{esc(verdict)}">
<header class="hero"><div class="wrap">
  <a class="back" href="/">&larr; A&amp;R Radar</a>
  <div class="who">
    <div class="avatar" style="background:{_avatar_color(track.artist)}">{initial}</div>
    <div>
      <span class="badge">{esc(VERDICT_LABEL[verdict])}</span>
      <h1>{esc(track.title)}</h1>
      <div class="sub">{esc(track.artist)} &middot; <a href="{esc(url)}" target="_blank" rel="noopener">Listen on SoundCloud &#8599;</a></div>
    </div>
  </div>
</div></header>
<main class="wrap">
  <section class="summary">
    <div class="ring" style="--p:{score};--c:{ring_color}"><b>{score}</b></div>
    <div class="txt"><b>A&amp;R score {score}/100</b><p>{esc(blurb)}</p>{notice}</div>
    {how_html(verdict, a, score)}
  </section>
  <section class="card"><h2>Traction</h2>{traction_html(a)}</section>
  {play_warning_html(a)}
  <section class="card"><h2>HumanStandard evidence</h2>{evidence_html(verdict, evidence)}</section>
  <p class="foot">Generated {datetime.now():%Y-%m-%d %H:%M}. The A&amp;R score is a heuristic for ranking leads, not a prediction.</p>
</main></body></html>"""


def write_report(track, verdict, evidence, a, score):
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORT_DIR / f"{score:03d}-{_slug(track.artist)}-{_slug(track.title)}.html"
    path.write_text(render_html(track, verdict, evidence, a, score), encoding="utf-8")
    return path


def alert(track: Track, verdict: str, a: Assessment, score: int) -> None:
    line = (
        f"*{verdict}* lead: {track.artist} - {track.title}\n"
        f"A&R score {score}/100 · {a.metrics['plays']:,} plays\n{track.url}"
    )
    if config.SLACK_WEBHOOK_URL:
        httpx.post(config.SLACK_WEBHOOK_URL, json={"text": line}, timeout=15)
    if config.DISCORD_WEBHOOK_URL:
        httpx.post(config.DISCORD_WEBHOOK_URL, json={"content": line}, timeout=15)
