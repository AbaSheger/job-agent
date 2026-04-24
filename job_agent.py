#!/usr/bin/env python3
"""
Job Agent
Sources: Jobtech API (Arbetsformedlingen) + LinkedIn via jobspy
Brain:   Claude Haiku scores each job against full candidate profile
Output:  Ranked Telegram messages with tap-to-track buttons, daily at 07:30
"""

import os
import re
import json
import time
import hashlib
import requests
from datetime import datetime
from pathlib import Path

# Config
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_KEY    = os.environ["ANTHROPIC_API_KEY"]
BASE_DIR         = Path(__file__).parent
SEEN_FILE        = BASE_DIR / "seen_jobs.json"
TRACKER_FILE     = BASE_DIR / "tracker.json"
CANDIDATE_PROFILE_FILE = BASE_DIR / "candidate_profile.txt"
MIN_SCORE        = 6
MAX_JOBS_MSG     = 15
JOBTECH_URL      = "https://jobsearch.api.jobtechdev.se/search"
CLAUDE_MODEL     = "claude-haiku-4-5-20251001"

# Candidate profile
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
- Stockholm, Uppsala, hybrid, or remote
- Junior developer, QA, DevOps, and adjacent entry-level software roles
"""


def load_profile():
    """Load a private profile from env/file, with a public-safe sample fallback."""
    if os.environ.get("CANDIDATE_PROFILE"):
        return os.environ["CANDIDATE_PROFILE"]
    if CANDIDATE_PROFILE_FILE.exists():
        return CANDIDATE_PROFILE_FILE.read_text(encoding="utf-8")
    return SAMPLE_PROFILE


PROFILE = load_profile()
# Pre-filter
HARD_EXCLUDE = [
    "senior developer", "senior engineer", "senior software", "lead developer",
    "tech lead", "principal engineer", "head of engineering", "cto",
    "10+ years", "10 years experience", "8+ years", "8 years experience",
    "7+ years", "15 years",
]
MUST_PASS = [
    "develop", "developer", "engineer", "programmer", "programmerare",
    "utvecklare", "java", "python", "backend", "frontend", "fullstack",
    "devops", "test", "qa ", "quality assurance", "it-support", "it support",
    "software", "mjukvara", "system", "data engineer", "cloud",
    "konsult", ".net", "react", "angular",
]

def pre_filter(title, description):
    text = (title + " " + description).lower()
    if any(kw in text for kw in HARD_EXCLUDE):
        return False
    return any(kw in text for kw in MUST_PASS)

# Dedup key
def job_key(title, company):
    raw = title.lower().strip() + "|" + company.lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()

# Persistence
def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text())[-3000:])
    return set()

def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)))

def load_tracker():
    if TRACKER_FILE.exists():
        return json.loads(TRACKER_FILE.read_text())
    return {}

def save_tracker(data):
    TRACKER_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

# Jobtech
JOBTECH_QUERIES = [
    "java developer", "systemutvecklare java", "junior developer",
    "spring boot", "backend developer", "fullstack developer",
    "junior software engineer", "qa testare", "junior devops",
    "react developer", "graduate developer", "junior .net",
]

def fetch_jobtech(query, limit=50):
    try:
        r = requests.get(JOBTECH_URL, params={"q": query, "limit": limit}, timeout=15)
        r.raise_for_status()
        return r.json().get("hits", [])
    except Exception as e:
        print(f"    Jobtech error ({query!r}): {e}")
        return []

def parse_jobtech(raw):
    addr = raw.get("workplace_address") or {}
    app  = raw.get("application_details") or {}
    desc = raw.get("description") or {}
    title   = raw.get("headline", "Unknown role")
    company = (raw.get("employer") or {}).get("name", "Unknown")
    return {
        "key":       job_key(title, company),
        "title":     title,
        "company":   company,
        "location":  addr.get("municipality") or addr.get("region") or "Sverige",
        "url":       app.get("url") or "",
        "desc":      desc.get("text", "") if isinstance(desc, dict) else "",
        "published": (raw.get("publication_date") or "")[:10],
        "source":    "Arbetsformedlingen",
    }

def collect_jobtech():
    pool = {}
    for query in JOBTECH_QUERIES:
        print(f"    [{query}]")
        for raw in fetch_jobtech(query):
            job = parse_jobtech(raw)
            if job["key"] not in pool:
                pool[job["key"]] = job
        time.sleep(0.4)
    return pool

# LinkedIn
LINKEDIN_QUERIES = [
    "junior java developer", "junior backend developer",
    "junior software engineer", "junior fullstack developer",
    "qa engineer junior", "junior devops engineer",
    "graduate software developer", "junior .net developer",
]

def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()

def collect_linkedin():
    pool = {}
    try:
        from jobspy import scrape_jobs
        for query in LINKEDIN_QUERIES:
            print(f"    [{query}]")
            try:
                df = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=query,
                    location="Sweden",
                    results_wanted=20,
                    hours_old=48,
                    linkedin_fetch_description=True,
                )
                for _, row in df.iterrows():
                    title   = str(row.get("title") or "Unknown role")
                    company = str(row.get("company") or "Unknown")
                    key     = job_key(title, company)
                    if key not in pool:
                        pool[key] = {
                            "key":       key,
                            "title":     title,
                            "company":   company,
                            "location":  str(row.get("location") or "Sweden"),
                            "url":       str(row.get("job_url") or ""),
                            "desc":      strip_html(str(row.get("description") or ""))[:4000],
                            "published": str(row.get("date_posted") or "")[:10],
                            "source":    "LinkedIn",
                        }
            except Exception as e:
                print(f"    LinkedIn query error ({query!r}): {e}")
            time.sleep(2)
    except ImportError:
        print("    jobspy not installed - skipping LinkedIn")
    return pool

# Claude scoring
EVAL_SYSTEM = (
    "You are a recruiter evaluating job fit. "
    "Respond with valid JSON only - no markdown, no text outside the JSON."
)
EVAL_PROMPT = """Candidate profile:
{profile}

Job:
Title: {title}
Company: {company}
Location: {location}
Source: {source}
Description: {description}

Evaluate fit honestly. Consider: direct skill match, adjacent fit, suitability for someone
with no commercial dev experience, Swedish market context.

Return exactly:
{{"score": <1-10>, "reason": "<one honest sentence>", "role_type": "<junior-dev|qa-test|devops|adjacent|long-shot>"}}

Score guide: 9-10 strong match, 7-8 good fit, 5-6 adjacent/worth trying, 1-4 skip."""

def claude_score(job):
    prompt = EVAL_PROMPT.format(
        profile=PROFILE,
        title=job["title"],
        company=job["company"],
        location=job["location"],
        source=job["source"],
        description=job["desc"][:3000],
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 200,
                "system": EVAL_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"    Claude error for '{job['title']}': {e}")
        return None

# Telegram
ROLE_LABEL  = {"junior-dev":"DEV","qa-test":"QA","devops":"OPS","adjacent":"ADJ","long-shot":"TRY"}
SOURCE_LABEL = {"LinkedIn":"LI","Arbetsformedlingen":"AF"}
score_label = lambda s: "HIGH" if s>=8 else "MED" if s>=6 else "LOW"

def tg(method, **kwargs):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            json=kwargs,
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  tg.{method} error: {e}")

def send_plain(text):
    tg("sendMessage",
       chat_id=TELEGRAM_CHAT_ID,
       text=text,
       parse_mode="HTML",
       disable_web_page_preview=True)

def send_job(job):
    """Send a single job card with tap-to-track inline buttons."""
    src  = SOURCE_LABEL.get(job.get("source",""), "JOB")
    role = ROLE_LABEL.get(job.get("role_type",""), "JOB")
    text = (
        f"[{score_label(job['score'])}] <b>{job['score']}/10</b> {role} {src}  {job['title']}\n"
        f"<i>{job['company']} - {job['location']}</i>\n"
        f"{job.get('reason','')}\n"
    )
    text += f"<a href=\"{job['url']}\">Apply -></a>" if job["url"].startswith("http") else "Search manually"
    if job.get("published"):
        text += f"  -  {job['published']}"

    key = job["key"]
    keyboard = {"inline_keyboard": [[
        {"text": "Applied",       "callback_data": f"applied|{key}"},
        {"text": "Not interested","callback_data": f"skip|{key}"},
        {"text": "Save",          "callback_data": f"save|{key}"},
    ]]}

    tg("sendMessage",
       chat_id=TELEGRAM_CHAT_ID,
       text=text,
       parse_mode="HTML",
       disable_web_page_preview=True,
       reply_markup=keyboard)

def pipeline_summary(tracker):
    counts = {"applied":0, "save":0, "skip":0}
    for v in tracker.values():
        s = v.get("status")
        if s in counts:
            counts[s] += 1
    total = sum(counts.values())
    if total == 0:
        return ""
    return (
        f"<b>Your pipeline</b>\n"
        f"Applied: {counts['applied']}  "
        f"Saved: {counts['save']}  "
        f"Skipped: {counts['skip']}\n"
        "---------------------\n"
    )

# Main
def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Job agent starting...")
    seen    = load_seen()
    tracker = load_tracker()

    # Collect
    print("  Fetching Jobtech...")
    jobtech_pool = collect_jobtech()
    print("  Fetching LinkedIn...")
    linkedin_pool = collect_linkedin()

    all_jobs = {**jobtech_pool, **linkedin_pool}
    print(f"  Total unique: {len(all_jobs)} (AF: {len(jobtech_pool)}, LI: {len(linkedin_pool)})")

    # Filter seen + already actioned
    actioned_keys = {k for k,v in tracker.items() if v.get("status") in ("applied","skip")}
    new_jobs   = [j for j in all_jobs.values() if j["key"] not in seen and j["key"] not in actioned_keys]
    candidates = [j for j in new_jobs if pre_filter(j["title"], j["desc"])]
    print(f"  New + not actioned: {len(new_jobs)}  After pre-filter: {len(candidates)}")

    # Claude scoring
    scored = []
    for i, job in enumerate(candidates):
        print(f"  [{i+1}/{len(candidates)}] {job['title']} @ {job['company']}")
        result = claude_score(job)
        if result and result.get("score", 0) >= MIN_SCORE:
            job.update({
                "score":     result["score"],
                "reason":    result.get("reason", ""),
                "role_type": result.get("role_type", "adjacent"),
            })
            scored.append(job)
            # Register in tracker so webhook can update it later
            tracker[job["key"]] = {
                "title":   job["title"],
                "company": job["company"],
                "url":     job["url"],
                "score":   job["score"],
                "source":  job["source"],
                "status":  "new",
                "added":   datetime.now().strftime("%Y-%m-%d"),
            }
        time.sleep(0.3)

    save_tracker(tracker)

    scored.sort(key=lambda j: j["score"], reverse=True)
    top = scored[:MAX_JOBS_MSG]
    print(f"  Scored >= {MIN_SCORE}: {len(scored)}  Sending top: {len(top)}")

    # Send header
    af_count = sum(1 for j in candidates if j["source"]=="Arbetsformedlingen")
    li_count = sum(1 for j in candidates if j["source"]=="LinkedIn")
    header = (
        f"<b>Job radar - {datetime.now():%d %b %Y}</b>\n"
        f"Evaluated <b>{len(candidates)}</b> new roles "
        f"(AF {af_count} - LI {li_count})\n"
        f"<b>{len(top)}</b> worth applying - tap to track\n"
        "---------------------\n"
    )

    summary = pipeline_summary(tracker)
    if summary:
        send_plain(summary + header)
    else:
        send_plain(header)
    time.sleep(0.3)

    if not top:
        send_plain(f"None scored above {MIN_SCORE}/10 today. Check back tomorrow.")
    else:
        for job in top:
            send_job(job)
            time.sleep(0.4)

    seen.update(all_jobs.keys())
    save_seen(seen)
    print("  Done.")

if __name__ == "__main__":
    main()
