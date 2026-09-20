"""Step 3: Analyst agent. Scores organic traction and flags likely play farming."""
import math
import time
from dataclasses import dataclass, field

from scout import Track


@dataclass
class Assessment:
    bot_risk: int  # 0-100, higher means more suspicious
    momentum: int  # 0-100, higher means stronger organic traction
    flags: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def assess(track: Track) -> Assessment:
    hours = max((time.time() - track.uploaded_at) / 3600, 1.0)
    plays = max(track.plays, 0)
    followers = max(track.followers, 1)
    like_rate = track.likes / plays if plays else 0.0
    repost_rate = track.reposts / plays if plays else 0.0
    comment_rate = track.comments / plays if plays else 0.0
    velocity = plays / hours
    plays_per_follower = plays / followers

    risk, flags = 0, []
    if plays >= 1000 and plays_per_follower > 100:
        risk += 40
        flags.append(f"{plays:,} plays against {track.followers:,} followers")
    elif plays >= 1000 and plays_per_follower > 30:
        risk += 20
        flags.append("Plays far exceed audience size")
    if plays >= 5000 and like_rate < 0.002:
        risk += 30
        flags.append(f"Like rate only {like_rate:.2%}")
    if plays >= 5000 and track.comments == 0:
        risk += 15
        flags.append("No comments despite high plays")
    if velocity > 5000:
        risk += 15
        flags.append(f"Extreme velocity: {velocity:,.0f} plays/hour")
    risk = min(risk, 100)

    # Momentum: engagement quality (60%) and reach (40%), both log-scaled and capped.
    engagement = min((like_rate * 100 + repost_rate * 300 + comment_rate * 500) / 12, 1.0)
    engagement *= min(plays / 100, 1.0)  # rates on a handful of plays are noise
    reach = min(math.log10(plays + 1) / 5, 1.0)
    momentum = round((engagement * 0.6 + reach * 0.4) * 100 * (1 - risk / 150))

    return Assessment(
        bot_risk=risk,
        momentum=max(momentum, 0),
        flags=flags,
        metrics={
            "plays": plays,
            "likes": track.likes,
            "reposts": track.reposts,
            "comments": track.comments,
            "followers": track.followers,
            "like_rate": round(like_rate, 4),
            "plays_per_hour": round(velocity, 1),
            "plays_per_follower": round(plays_per_follower, 2),
            "age_hours": round(hours, 1),
        },
    )
