"""Turns a raw HumanStandard result into plain-language explanations.

Wording follows https://docs.hsverify.com/reviewers/result-fields
"""


def _strength(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    if confidence >= 0.9:
        return "strong"
    if confidence >= 0.7:
        return "moderate"
    return "weak"


def _headline(verdict: str, strength: str | None) -> str:
    if verdict == "HUMAN":
        text = "HumanStandard says this track is human-made"
    elif verdict == "AI":
        text = "HumanStandard says this track is AI-generated"
    else:
        return "HumanStandard could not make a confident call. Listen before deciding."
    return f"{text} ({strength} evidence)" if strength else text


def _origin(origin: str | None) -> str:
    if origin in (None, "", "human"):
        return "None. It doesn't resemble any known AI generator."
    if origin == "uncertain":
        return "No clear match. It sits between several groups of tracks, so no generator is named."
    if origin == "unknown":
        return "Flagged as AI but matches no generator on file, which is common for newer tools."
    return f"It most resembles tracks made with {origin.title()}."


def _moments(timeline: list[float], verdict: str) -> tuple[str, str] | None:
    if not timeline:
        return None
    hot = sum(1 for r in timeline if r >= 0.5)
    peak = max(timeline)
    at = timeline.index(peak) / max(len(timeline) - 1, 1)
    value = f"{hot} of {len(timeline)} sections looked AI-like (risk above 50%)"
    note = (
        f"The single highest reading was {peak:.0%}, about {at:.0%} of the way through the track. "
        "Isolated spikes are normal, and the verdict already accounts for them, so trust the verdict "
        "over this number. If you do listen, start there."
        if verdict == "HUMAN"
        else f"The single highest reading was {peak:.0%}, about {at:.0%} of the way through the track. "
        "Listen there first."
    )
    return value, note


def explain(verdict: str, ev: dict) -> dict:
    """Return {"headline", "items": [{"label", "value", "note"}], "footer"} for display."""
    conf = ev.get("confidence")
    strength = _strength(conf)
    items = []

    if conf is not None:
        note = (
            "How strong the evidence is for the verdict above, from 0.5 (a coin flip) to 1.0 "
            "(overwhelming). It is not the chance that the track is AI."
        )
        if verdict == "HUMAN" and strength == "weak":
            note += " The verdict is human, but the evidence is thin, so a listen is worthwhile."
        items.append({"label": "How sure is it?", "value": f"{strength.capitalize()} ({conf:.2f})", "note": note})

    items.append(
        {
            "label": "Which AI tool does it resemble?",
            "value": _origin(ev.get("origin")),
            "note": "Answers 'what does this sound like', which is a different question from 'is this AI'.",
        }
    )

    nearest = (ev.get("origin_map") or {}).get("summary_line")
    if nearest:
        items.append(
            {
                "label": "How does it compare to known recordings?",
                "value": nearest,
                "note": "HumanStandard checks the audio against a library of verified-human and "
                "AI-generated tracks and looks at the 25 closest matches.",
            }
        )

    moments = _moments(ev.get("risk_timeline") or [], verdict)
    if moments:
        items.append({"label": "Any AI-like moments?", "value": moments[0], "note": moments[1]})

    status = ev.get("industry_label_status")
    if status == "meets_definition":
        items.append(
            {
                "label": "Industry label",
                "value": "Qualifies as AI-Generated",
                "note": "The detection cleared HumanStandard's certification bar.",
            }
        )
    elif status == "suspected":
        items.append(
            {
                "label": "Industry label",
                "value": "Suspected AI, not confirmed",
                "note": "It leans AI but is below the certification bar. Treat it as a flag for human review.",
            }
        )

    footer = f"Detector version {ev['model_version']}" if ev.get("model_version") else ""
    return {"headline": _headline(verdict, strength), "items": items, "footer": footer}
