import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# HumanStandard API, see https://docs.hsverify.com
HS_BASE_URL = os.getenv("HS_BASE_URL", "https://app.jobsbyhumans.com")
HS_API_KEY = os.getenv("HS_API_KEY", "")

# One credit is one scan and the hackathon key has 200, so cap scans per run.
MAX_SCANS_PER_RUN = int(os.getenv("MAX_SCANS_PER_RUN", "10"))
MAX_AGE_HOURS = float(os.getenv("MAX_AGE_HOURS", "24"))
MAX_TRACK_MINUTES = float(os.getenv("MAX_TRACK_MINUTES", "10"))

# Search terms and profile URLs to watch, comma separated.
SC_QUERIES = [q.strip() for q in os.getenv("SC_QUERIES", "unsigned artist,new music").split(",") if q.strip()]
SC_PROFILES = [p.strip() for p in os.getenv("SC_PROFILES", "").split(",") if p.strip()]
RESULTS_PER_QUERY = int(os.getenv("RESULTS_PER_QUERY", "25"))

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
# Only alert on leads with at least this scorecard score (0-100).
ALERT_MIN_SCORE = int(os.getenv("ALERT_MIN_SCORE", "60"))

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "pipeline.db"
REPORT_DIR = ROOT / "reports"
TMP_DIR = ROOT / "tmp"
