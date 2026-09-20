"""Step 2: Forensic agent. Sends audio to HumanStandard and normalizes the verdict.

API: https://docs.hsverify.com  (POST /api/analyze -> job_id, poll /api/jobs/{id}/status)
"""
import hashlib
import time
from dataclasses import dataclass

import httpx

import config

AI, REVIEW, HUMAN = "AI", "REVIEW", "HUMAN"


@dataclass
class Verdict:
    verdict: str  # AI | REVIEW | HUMAN
    evidence: dict  # raw result payload, kept verbatim for the scorecard


def _normalize(result: dict) -> str:
    raw = str(result["verdict"]).strip().lower()
    if raw == "human":
        return HUMAN
    if raw == "ai":
        # Auto-discard only when the strict signals agree, so we never bin a human
        # artist on a borderline call. Either field may be absent, which means no objection.
        tiers = result.get("tier_verdicts") or {}
        if tiers.get("human_safe", "ai") != "ai":
            return REVIEW
        if result.get("industry_label_status", "meets_definition") != "meets_definition":
            return REVIEW
        return AI
    if raw in {"uncertain", "suspicious"}:
        return REVIEW
    raise ValueError(f"Unrecognized verdict {raw!r}")


def _client() -> httpx.Client:
    if not config.HS_API_KEY:
        raise RuntimeError("HS_API_KEY is not set")
    return httpx.Client(
        base_url=config.HS_BASE_URL,
        headers={"Authorization": f"Bearer {config.HS_API_KEY}"},
        timeout=120,
    )


def _wait(client: httpx.Client, job_id: str, timeout_s: int = 300) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}/status")
        resp.raise_for_status()
        body = resp.json()
        if body["status"] == "complete":
            return body["result"]
        if body["status"] == "failed":
            raise RuntimeError(body.get("error") or "HumanStandard analysis failed")
        time.sleep(2)
    raise TimeoutError(f"job {job_id} did not finish in {timeout_s}s")


def analyze(audio_path=None, mock: str | None = None) -> Verdict:
    """Scan a local audio file. With `mock` set, no file is read and no credit is spent."""
    params = {"detail": "full"}
    if mock:
        params["mock"] = mock
    with _client() as client:
        if audio_path is None:
            resp = client.post("/api/analyze", params=params)
        else:
            with open(audio_path, "rb") as fh:
                resp = client.post("/api/analyze", params=params, files={"file": (audio_path.name, fh)})
        resp.raise_for_status()
        result = _wait(client, resp.json()["job_id"])
    return Verdict(_normalize(result), result)


MOCK_SCENARIOS = ["human", "ai", "suspicious", "human"]


def demo_analyze(url: str) -> Verdict:
    """Free mock scan. Uses the real API when a key is set, else a local fake."""
    scenario = MOCK_SCENARIOS[int(hashlib.sha1(url.encode()).hexdigest(), 16) % len(MOCK_SCENARIOS)]
    if config.HS_API_KEY:
        return analyze(mock=scenario)
    fake = {"verdict": scenario, "confidence": 0.9, "mock": True, "mock_scenario": scenario}
    return Verdict(_normalize(fake), fake)
