"""Step 1: Scout agent. Finds fresh SoundCloud uploads and pulls audio via yt-dlp."""
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yt_dlp

import config


@dataclass
class Track:
    url: str
    title: str
    artist: str
    uploaded_at: float  # unix seconds
    duration: float
    plays: int = 0
    likes: int = 0
    reposts: int = 0
    comments: int = 0
    followers: int = 0
    audio_path: Path | None = None
    extra: dict = field(default_factory=dict)


API = "https://api-v2.soundcloud.com"


def _client_id() -> str:
    """Reuse the public web client id that yt-dlp keeps current."""
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        ie = ydl.get_info_extractor("Soundcloud")
        ie._update_client_id()
        return ie._CLIENT_ID


def _track_from_api(t: dict) -> Track:
    user = t.get("user") or {}
    created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")).timestamp()
    return Track(
        url=t["permalink_url"],
        title=t.get("title") or "Untitled",
        artist=user.get("username") or "Unknown",
        uploaded_at=created,
        duration=(t.get("full_duration") or t.get("duration") or 0) / 1000,
        plays=int(t.get("playback_count") or 0),
        likes=int(t.get("likes_count") or 0),
        reposts=int(t.get("reposts_count") or 0),
        comments=int(t.get("comment_count") or 0),
        followers=int(user.get("followers_count") or 0),
        extra={"policy": t.get("policy"), "genre": t.get("genre")},
    )


def _fetch_tracks(client: httpx.Client, cid: str) -> list[dict]:
    raw: list[dict] = []
    for query in config.SC_QUERIES:
        resp = client.get(
            f"{API}/search/tracks",
            params={
                "q": query,
                "client_id": cid,
                "filter.created_at": "last_day",
                "limit": config.RESULTS_PER_QUERY,
            },
        )
        resp.raise_for_status()
        raw += resp.json().get("collection", [])
    for profile in config.SC_PROFILES:
        user = client.get(f"{API}/resolve", params={"url": profile, "client_id": cid})
        user.raise_for_status()
        resp = client.get(
            f"{API}/users/{user.json()['id']}/tracks",
            params={"client_id": cid, "limit": 20},
        )
        resp.raise_for_status()
        raw += resp.json().get("collection", [])
    return raw


def discover(seen_urls: set[str]) -> list[Track]:
    """Return unseen, downloadable tracks from emerging artists uploaded within MAX_AGE_HOURS."""
    cutoff = time.time() - config.MAX_AGE_HOURS * 3600
    found: dict[str, Track] = {}
    with httpx.Client(timeout=30) as client:
        for raw in _fetch_tracks(client, _client_id()):
            if raw.get("policy") in {"SNIP", "BLOCK"} or raw.get("access") == "preview":
                continue  # Go+ previews and blocked tracks cannot be downloaded
            track = _track_from_api(raw)
            if track.url in seen_urls or track.url in found or track.uploaded_at < cutoff:
                continue
            if track.duration > config.MAX_TRACK_MINUTES * 60:
                continue  # skip DJ mixes and podcasts
            if config.MAX_FOLLOWERS and track.followers > config.MAX_FOLLOWERS:
                continue  # already established, not an emerging artist
            found[track.url] = track
    return sorted(found.values(), key=lambda t: t.uploaded_at, reverse=True)


def download_audio(track: Track) -> Path:
    """Download a temporary mp3 for the forensic scan."""
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio/best",
        "outtmpl": str(config.TMP_DIR / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(track.url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
    track.audio_path = path
    return path
