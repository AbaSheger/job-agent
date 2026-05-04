import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("JOB_AGENT_STATE_DIR", ROOT_DIR))
STATE_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

SEEN_FILE = STATE_DIR / "seen_jobs.json"
TRACKER_FILE = STATE_DIR / "tracker.json"
UPDATE_OFFSET_FILE = STATE_DIR / "telegram_update_offset.txt"
CANDIDATE_PROFILE_FILE = ROOT_DIR / "candidate_profile.txt"

MIN_SCORE = 6
MAX_JOBS_MSG = 15
MAX_CANDIDATES_TO_SCORE = 30
MAX_BATCH_RESULTS = 8
MAX_DESC_CHARS = 450
MIN_LOCAL_PRIORITY = 6
MAX_JOBS_PER_COMPANY = 2

JOBTECH_LIMIT = 30
JOBTECH_URL = "https://jobsearch.api.jobtechdev.se/search"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_URL = "https://remoteok.com/api"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

SAMPLE_PROFILE = """
Target: Junior software engineering roles in Sweden.

TECHNICAL STACK:
- Backend: Java, Spring Boot, C#, .NET, REST APIs
- Frontend: React, TypeScript, Angular
- Databases: PostgreSQL, MySQL
- DevOps: Docker, GitHub Actions, Linux, cloud fundamentals
- Testing: JUnit, Mockito, xUnit, Postman

EXPERIENCE:
- Internship and project experience across full-stack development
- Strong interest in AI-assisted product and engineering workflows

PREFERENCES:
- On-site/hybrid: Stockholm, Uppsala, Gävle, Ludvika, Falun, or anywhere in Dalarna
- Remote: EU-based companies only (living in Sweden, need EU employment eligibility)
- Junior developer, QA automation, test automation, DevOps junior, cloud/application
  support, integration developer, system developer, technical consultant,
  implementation consultant, and SQL/API application specialist roles
"""


def load_profile():
    """Load a private profile from env/file, with a public-safe sample fallback."""
    if os.environ.get("CANDIDATE_PROFILE"):
        return os.environ["CANDIDATE_PROFILE"]
    if CANDIDATE_PROFILE_FILE.exists():
        return CANDIDATE_PROFILE_FILE.read_text(encoding="utf-8")
    return SAMPLE_PROFILE


PROFILE = load_profile()

