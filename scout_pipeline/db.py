import json
import sqlite3
import time

from config import DB_PATH


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tracks (
            url TEXT PRIMARY KEY,
            title TEXT, artist TEXT,
            verdict TEXT,          -- AI | REVIEW | HUMAN
            evidence TEXT,         -- raw HumanStandard payload as JSON
            scanned_at REAL
        );
        CREATE TABLE IF NOT EXISTS synthetic_spam (
            url TEXT PRIMARY KEY, title TEXT, artist TEXT, evidence TEXT, logged_at REAL
        );
        CREATE TABLE IF NOT EXISTS scorecards (
            url TEXT PRIMARY KEY, score INTEGER, bot_risk INTEGER, created_at REAL
        );
        """
    )
    # `details` (traction metrics, flags, score, report file) arrived after the first release.
    if "details" not in {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}:
        conn.execute("ALTER TABLE tracks ADD COLUMN details TEXT")
        conn.commit()
    return conn


def already_scanned(conn: sqlite3.Connection, url: str) -> bool:
    return conn.execute("SELECT 1 FROM tracks WHERE url = ?", (url,)).fetchone() is not None


def record_scan(conn, track, verdict: str, evidence: dict, details: dict | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracks (url, title, artist, verdict, evidence, scanned_at, details)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            track.url, track.title, track.artist, verdict, json.dumps(evidence), time.time(),
            json.dumps(details) if details is not None else None,
        ),
    )
    if verdict == "AI":
        conn.execute(
            "INSERT OR REPLACE INTO synthetic_spam VALUES (?,?,?,?,?)",
            (track.url, track.title, track.artist, json.dumps(evidence), time.time()),
        )
    conn.commit()


def record_scorecard(conn, url: str, score: int, bot_risk: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO scorecards VALUES (?,?,?,?)", (url, score, bot_risk, time.time())
    )
    conn.commit()
