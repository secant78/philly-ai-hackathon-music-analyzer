# A&R Radar

Finds real, emerging artists on SoundCloud and filters out AI-generated tracks and fake-hype numbers, so an A&R scout spends their limited time on music worth hearing.

Built for the Philly AI Hackathon, HumanStandard track ("build for human music"). It uses the [HumanStandard](https://docs.hsverify.com) detection API to decide whether a track is human-made, AI-generated, or borderline.

<!-- Add a screenshot: save it as docs/dashboard.png and uncomment the next line. -->
<!-- ![Dashboard](docs/dashboard.png) -->

## The problem

A&R (Artists and Repertoire) scouts look for unsigned artists to sign, and much of that scouting happens on platforms like SoundCloud. Two things now waste their time:

- **AI-generated tracks** flood upload feeds, and an AI "artist" is not someone a label can sign.
- **Inflated play counts.** A track with 100,000 plays and 10 followers looks like a hit but isn't.

Neither problem can be solved by scrolling faster.

## What it does

A four-stage pipeline, run from `scout_pipeline/`:

| Stage | File | What happens |
|---|---|---|
| 1. Scout | `scout.py` | Searches SoundCloud for recent uploads. Skips DRM-locked tracks, DJ mixes, accounts with a big following, and channels that post hundreds of tracks. Ranks candidates by traction so scarce API credits go to the most promising tracks first, and takes one track per artist. |
| 2. Forensic | `forensic.py` | Downloads the audio and sends it to HumanStandard. AI verdicts are discarded and logged. Borderline verdicts are flagged for a human to review. |
| 3. Analyst | `analyst.py` | Measures engagement (likes, reposts, comments per play) and flags suspicious patterns such as plays far exceeding follower count. |
| 4. Outreach | `outreach.py`, `explain.py` | Produces an A&R score and an HTML scorecard per lead, with HumanStandard's evidence explained in plain language. Can send Slack or Discord alerts. |

A local web dashboard (`dashboard.py`) lists every scanned track with its verdict, score and evidence, and has filters, sorting, a shortlist, and a "Scan now" button.

## Quick start (Windows)

You need Python 3.11+ and ffmpeg (used to convert downloaded audio to mp3).

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

Open a new terminal, then:

```powershell
cd scout_pipeline
python -m pip install -r requirements.txt
copy .env.example .env
```

Put your HumanStandard API key in `.env` as `HS_API_KEY=...`. Never commit this file. It is already in `.gitignore`.

Try it without spending credits:

```powershell
python main.py --demo
python dashboard.py
```

`--demo` uses invented tracks and HumanStandard's free mock mode, so you can see the whole pipeline work. Then open http://127.0.0.1:8000 (tick "Show demo data" to see them).

Run a real scan:

```powershell
python main.py
```

## Configuration

Set these in `scout_pipeline/.env`:

| Setting | Default | Meaning |
|---|---|---|
| `HS_API_KEY` | (required) | Your HumanStandard key |
| `MAX_SCANS_PER_RUN` | 10 | Hard cap on scans per run. **One scan costs one credit.** |
| `MAX_AGE_HOURS` | 24 | How far back to look for uploads (336 is two weeks) |
| `SC_QUERIES` | `unsigned artist,new music` | SoundCloud search terms, comma separated |
| `MAX_FOLLOWERS` | 1000 | Skip uploaders with more followers (likely signed already) |
| `MAX_UPLOADER_TRACKS` | 200 | Skip accounts with more uploads (channels, aggregators) |
| `EXCLUDE_TITLE_WORDS` | `cover,remix,bootleg,mashup,flip,rework,refix` | Skip titles containing these whole words (originals only). Empty allows everything. |
| `SLACK_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL` | empty | Optional alerts for strong leads |

## How the A&R score works

The score ranks how promising a track is. It is separate from the human or AI verdict, which only decides whether a track gets a score at all.

- **Momentum (0-100):** engagement quality (60%) and reach (40%). Engagement weights comments most, then reposts, then likes, and is damped for tracks with very few plays.
- **Bot risk (0-100):** penalties for play-farming patterns, such as plays far above follower count or a very low like rate on a high-play track. These checks only apply above roughly 1,000 plays, so on small tracks bot risk is 0 because there is too little data to judge, not because the track was proven clean.
- **Score = momentum x (1 - bot risk / 100)**, reduced by 20% for borderline verdicts.

## Honest limitations

- **The score is a heuristic.** The weights and thresholds are our own judgment and have not been validated against real signings or hits. Use it to rank leads within a run, not to predict success.
- **A verdict is a probability, not proof.** HumanStandard's own documentation notes that detection error concentrates in certain genres. Borderline results should be heard by a person before anyone acts on them.
- **SoundCloud only.** Real scouting also uses TikTok, Spotify, live shows and personal networks. This is a first-pass filter, not a replacement for a scout.
- **"Emerging" is approximated.** Follower and upload counts are a rough proxy for "not signed yet." A signed artist can have few followers, and an unsigned one can have many.
- **Credit-limited.** Each scan costs a HumanStandard credit, so a run scans only the top-ranked tracks.
- **Search-based discovery.** SoundCloud search can match channel names and covers as well as original artists.

## Safety notes

- The dashboard listens on `127.0.0.1` only and refuses scan requests that do not come from its own page, so a website you visit cannot spend your credits.
- Track titles and artist names come from SoundCloud and are treated as untrusted text: the dashboard never renders them as HTML.
- The HumanStandard key lives in `.env` and is never written to the database or reports.

## Project layout

```
scout_pipeline/
  main.py         orchestrator (python main.py [--demo])
  scout.py        SoundCloud discovery and audio download
  forensic.py     HumanStandard API client
  analyst.py      traction and bot-risk scoring
  outreach.py     scorecards and webhook alerts
  explain.py      plain-language explanation of HumanStandard results
  dashboard.py    local web dashboard server
  dashboard.html  dashboard page
  db.py, config.py
```

Scan results are stored in `scout_pipeline/data/pipeline.db` and scorecards in `scout_pipeline/reports/`. Both are generated and git-ignored.
