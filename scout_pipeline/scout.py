"""Step 1: Scout agent. Finds fresh SoundCloud uploads and pulls audio via yt-dlp."""
import time
from dataclasses import dataclass, field
from pathlib import Path

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


def _track_from_info(info: dict) -> Track:
    return Track(
        url=info.get("webpage_url") or info["url"],
        title=info.get("title") or "Untitled",
        artist=info.get("uploader") or info.get("channel") or "Unknown",
        uploaded_at=float(info.get("timestamp") or 0),
        duration=float(info.get("duration") or 0),
        plays=int(info.get("view_count") or 0),
        likes=int(info.get("like_count") or 0),
        reposts=int(info.get("repost_count") or 0),
        comments=int(info.get("comment_count") or 0),
        followers=int(info.get("channel_follower_count") or 0),
    )


def _sources() -> list[str]:
    urls = [f"scsearch{config.RESULTS_PER_QUERY}:{q}" for q in config.SC_QUERIES]
    urls += config.SC_PROFILES
    return urls


def discover(seen_urls: set[str]) -> list[Track]:
    """Return unseen audio tracks uploaded within MAX_AGE_HOURS, newest first."""
    cutoff = time.time() - config.MAX_AGE_HOURS * 3600
    found: dict[str, Track] = {}
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for source in _sources():
            result = ydl.extract_info(source, download=False)
            for entry in (result or {}).get("entries") or []:
                if not entry:
                    continue
                track = _track_from_info(entry)
                if track.url in seen_urls or track.url in found:
                    continue
                if track.uploaded_at < cutoff:
                    continue
                if track.duration and track.duration > config.MAX_TRACK_MINUTES * 60:
                    continue  # skip DJ mixes and podcasts
                found[track.url] = track
    return sorted(found.values(), key=lambda t: t.uploaded_at, reverse=True)


def download_audio(track: Track) -> Path:
    """Download a temporary mp3 for the forensic scan."""
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": str(config.TMP_DIR / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(track.url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
    track.audio_path = path
    return path
