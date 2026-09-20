"""Orchestrator: Scout -> Forensic -> Analyst -> Outreach.

    python main.py            # live run (needs HS_API_KEY and ffmpeg)
    python main.py --demo     # fake tracks; scans use HumanStandard mock mode (free)
"""
import argparse
import sys
import time

import analyst
import config
import db
import forensic
import outreach
from scout import Track


def demo_tracks() -> list[Track]:
    now = time.time()
    specs = [
        ("Midnight Static", "kova", 4200, 310, 40, 22, 1800, 6),
        ("Neon Reverie", "synthwave_bot_99", 180000, 90, 4, 0, 10, 8),
        ("Porch Light", "june daley", 950, 88, 12, 9, 240, 3),
        ("Glass Hours", "the low tides", 22000, 1100, 130, 64, 5200, 14),
        ("Loop 47", "beatfactory", 6400, 20, 1, 0, 400, 2),
    ]
    return [
        Track(
            url=f"https://soundcloud.com/demo/{i}", title=t, artist=a, uploaded_at=now - h * 3600,
            duration=180, plays=p, likes=l, reposts=r, comments=c, followers=f,
        )
        for i, (t, a, p, l, r, c, f, h) in enumerate(specs)
    ]


def run(demo: bool) -> int:
    conn = db.connect()
    if demo:
        tracks = demo_tracks()
    else:
        import scout

        seen = {row[0] for row in conn.execute("SELECT url FROM tracks")}
        tracks = scout.discover(seen)
    # Credits are scarce, so scan the tracks with the best traction first. Suspected
    # play farming sinks to the bottom, because momentum is discounted by bot risk.
    def priority(track: Track) -> float:
        a = analyst.assess(track)
        return a.momentum * (1 - a.bot_risk / 100)

    tracks.sort(key=priority, reverse=True)
    print(f"Scout: {len(tracks)} new tracks (scan budget {config.MAX_SCANS_PER_RUN})")

    scans = 0
    for track in tracks:
        if db.already_scanned(conn, track.url):
            continue
        if scans >= config.MAX_SCANS_PER_RUN:
            print("Scan budget reached; remaining tracks wait for the next run.")
            break
        label = f"{track.artist} - {track.title}"
        try:
            if demo:
                result = forensic.demo_analyze(track.url)
            else:
                import scout

                result = forensic.analyze(scout.download_audio(track))
            scans += 1
        except Exception as exc:  # keep going; one bad track shouldn't stop the run
            print(f"  ERROR  {label}: {exc}")
            continue
        db.record_scan(conn, track, result.verdict, result.evidence)

        if result.verdict == forensic.AI:
            print(f"  AI     {label}: discarded, logged as synthetic spam")
            continue

        a = analyst.assess(track)
        score = outreach.scorecard_score(result.verdict, a)
        db.record_scorecard(conn, track.url, score, a.bot_risk)
        report = outreach.write_report(track, result.verdict, result.evidence, a, score)
        tag = "REVIEW" if result.verdict == forensic.REVIEW else "HUMAN "
        print(f"  {tag} {label}: score {score}, bot risk {a.bot_risk} -> {report.name}")
        if score >= config.ALERT_MIN_SCORE and a.bot_risk < 50:
            outreach.alert(track, result.verdict, a, score)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # artist names are not always ASCII
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    sys.exit(run(p.parse_args().demo))
