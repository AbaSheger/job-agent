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
STATE_DIR        = Path(os.environ.get("JOB_AGENT_STATE_DIR", BASE_DIR))
STATE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE        = STATE_DIR / "seen_jobs.json"
TRACKER_FILE     = STATE_DIR / "tracker.json"
UPDATE_OFFSET_FILE = STATE_DIR / "telegram_update_offset.txt"
CANDIDATE_PROFILE_FILE = BASE_DIR / "candidate_profile.txt"
MIN_SCORE        = 6
MAX_JOBS_MSG     = 15
MAX_CANDIDATES_TO_SCORE = 5
MAX_DESC_CHARS   = 700
MIN_LOCAL_PRIORITY = 10
JOBTECH_LIMIT    = 30
LINKEDIN_RESULTS = 10
LINKEDIN_HOURS   = 24
JOBTECH_URL      = "https://jobsearch.api.jobtechdev.se/search"
CLAUDE_MODEL     = "claude-haiku-4-5-20251001"
REPUTABLE_COMPANIES = [
    "spotify", "klarna", "tink", "mongodb", "elastic", "gitlab", "github",
    "atlassian", "canonical", "red hat", "docker", "cloudflare", "stripe",
    "wise", "revolut", "adyen", "booking.com", "shopify", "datadog",
    "microsoft", "google", "amazon", "aws", "apple", "meta", "netflix",
    "jetbrains", "miro", "automattic", "thoughtworks", "accenture",
]

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
TITLE_EXCLUDE = [
    "senior", "lead", "principal", "staff engineer", "manager",
    "architect", "arkitekt", "chef", "cto", "lia", "praktik",
    "praktikant", "internship", "examensjobb", "exjobb", "thesis",
]
TEXT_EXCLUDE = [
    "lead developer", "tech lead", "principal", "staff engineer",
    "head of engineering", "engineering manager", "developer manager",
    "team manager", "team lead", "cto", "architect", "arkitekt",
    "erfaren utvecklare", "erfaren systemutvecklare",
    "10+ years", "10 years experience", "8+ years", "8 years experience",
    "7+ years", "7 years experience", "15 years", "flera ars erfarenhet",
    "lia-praktik", "lia praktik", "larande i arbete", "lärande i arbete",
    "lia-student", "praktikplats", "praktikant", "student internship",
    "internship", "unpaid internship", "examensjobb", "examensarbete",
    "exjobb", "master thesis", "bachelor thesis",
]
MUST_PASS = [
    "develop", "developer", "engineer", "programmer", "programmerare",
    "utvecklare", "java", "python", "backend", "frontend", "fullstack",
    "devops", "test", "qa ", "quality assurance", "it-support", "it support",
    "software", "mjukvara", "system", "data engineer", "cloud",
    "konsult", ".net", "react", "angular", "supporttekniker",
    "applikationssupport", "application support", "technical support",
    "graduate", "trainee", "nyexaminerad", "junior",
]
ENTRY_LEVEL_SIGNALS = [
    "junior", "graduate", "trainee", "entry level", "entry-level",
    "nyexaminerad", "nyutexaminerad",
    "0-1 years", "0-2 years", "no experience",
]

def pre_filter(title, description):
    title_text = title.lower()
    text = (title + " " + description).lower()
    if any(kw in title_text for kw in TITLE_EXCLUDE):
        return False
    if any(kw in text for kw in TEXT_EXCLUDE):
        return False
    if any(kw in title_text for kw in ENTRY_LEVEL_SIGNALS):
        return True
    return any(kw in text for kw in MUST_PASS)

def candidate_priority(job):
    company = job["company"].lower()
    text = f"{job['title']} {company} {job['location']} {job['desc'][:500]}".lower()
    score = 0
    boosts = {
        "junior": 10,
        "nyexaminerad": 10,
        "nyutexaminerad": 10,
        "graduate": 8,
        "trainee": 8,
        "java": 7,
        "spring": 7,
        "backend": 6,
        ".net": 6,
        "c#": 6,
        "react": 5,
        "frontend": 4,
        "qa": 3,
        "test": 3,
        "devops": 2,
        "cloud": 2,
    }
    for keyword, weight in boosts.items():
        if keyword in text:
            score += weight
    if job.get("remote"):
        score += 8
    if "remote" in text:
        score += 5
    if any(company_name in company for company_name in REPUTABLE_COMPANIES):
        score += 10
    if job["source"] == "Arbetsformedlingen":
        score += 2
    return score

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

def load_update_offset():
    if UPDATE_OFFSET_FILE.exists():
        try:
            return int(UPDATE_OFFSET_FILE.read_text().strip())
        except ValueError:
            return None
    return None

def save_update_offset(offset):
    UPDATE_OFFSET_FILE.write_text(str(offset))

# Jobtech
JOBTECH_QUERIES = [
    "java developer", "systemutvecklare java", "junior developer",
    "spring boot", "backend developer",
    "junior software engineer", "qa testare", "junior devops",
    "graduate developer", "junior .net",
    "javautvecklare", "backendutvecklare", "frontendutvecklare",
    "systemutvecklare junior", "nyexaminerad utvecklare",
    "testare junior", "qa engineer",
]

def fetch_jobtech(query, limit=JOBTECH_LIMIT):
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
        "remote":    False,
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
    "junior react developer", "junior qa tester",
]
REMOTE_LINKEDIN_QUERIES = [
    "junior software engineer remote",
    "junior backend developer remote",
    "graduate software engineer remote",
    "junior developer remote Europe",
]
REMOTE_LINKEDIN_LOCATIONS = ["Europe", "European Union", "United Kingdom"]

def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()

def collect_linkedin():
    pool = {}
    try:
        from jobspy import scrape_jobs
        searches = [(query, "Sweden", False) for query in LINKEDIN_QUERIES]
        searches += [
            (query, location, True)
            for query in REMOTE_LINKEDIN_QUERIES
            for location in REMOTE_LINKEDIN_LOCATIONS
        ]
        for query, location, remote_only in searches:
            remote_label = " remote" if remote_only else ""
            print(f"    [{query} @ {location}{remote_label}]")
            try:
                df = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=query,
                    location=location,
                    results_wanted=LINKEDIN_RESULTS,
                    hours_old=LINKEDIN_HOURS,
                    is_remote=remote_only,
                    linkedin_fetch_description=True,
                )
                for _, row in df.iterrows():
                    title   = str(row.get("title") or "Unknown role")
                    company = str(row.get("company") or "Unknown")
                    is_remote = bool(row.get("is_remote")) or remote_only
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
                            "source":    "LinkedIn Remote" if is_remote else "LinkedIn",
                            "remote":    is_remote,
                        }
            except Exception as e:
                print(f"    LinkedIn query error ({query!r}, {location!r}): {e}")
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
with no commercial dev experience, Swedish market context, and remote roles outside Sweden
when the company is reputable and the role is realistic for a junior candidate.

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
        description=job["desc"][:MAX_DESC_CHARS],
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
SOURCE_LABEL = {"LinkedIn":"LI","LinkedIn Remote":"REMOTE","Arbetsformedlingen":"AF"}
score_label = lambda s: "HIGH" if s>=8 else "MED" if s>=6 else "LOW"

def tg(method, **kwargs):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            json=kwargs,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  tg.{method} error: {e}")
        return None

def process_callback_updates(tracker):
    offset = load_update_offset()
    params = {"timeout": 0, "allowed_updates": json.dumps(["callback_query"])}
    if offset is not None:
        params["offset"] = offset

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        updates = r.json().get("result", [])
    except Exception as e:
        print(f"  tg.getUpdates error: {e}")
        return tracker

    if not updates:
        return tracker

    changed = 0
    next_offset = offset
    status_labels = {
        "applied": "Applied",
        "skip": "Not interested",
        "save": "Saved",
    }

    for update in updates:
        next_offset = max(next_offset or 0, update["update_id"] + 1)
        callback = update.get("callback_query") or {}
        data = callback.get("data", "")
        callback_id = callback.get("id")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}

        if str(chat.get("id")) != str(TELEGRAM_CHAT_ID):
            continue
        if "|" not in data:
            continue

        status, key = data.split("|", 1)
        if status not in status_labels:
            continue

        tracker.setdefault(key, {})
        tracker[key]["status"] = status
        tracker[key]["updated"] = datetime.now().strftime("%Y-%m-%d")
        changed += 1

        if callback_id:
            tg("answerCallbackQuery", callback_query_id=callback_id, text=status_labels[status])

    if next_offset is not None:
        save_update_offset(next_offset)
    if changed:
        save_tracker(tracker)
        print(f"  Processed {changed} Telegram button update(s)")
    return tracker

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
    tracker = process_callback_updates(tracker)

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
    skipped_repeat_count = len(all_jobs) - len(new_jobs)
    candidates = [j for j in new_jobs if pre_filter(j["title"], j["desc"])]
    candidates = [j for j in candidates if candidate_priority(j) >= MIN_LOCAL_PRIORITY]
    candidates.sort(key=candidate_priority, reverse=True)
    candidates_to_score = candidates[:MAX_CANDIDATES_TO_SCORE]
    print(f"  New + not actioned: {len(new_jobs)}  After pre-filter: {len(candidates)}")
    print(f"  Skipped already seen/actioned: {skipped_repeat_count}")
    print(f"  Scoring with Claude: {len(candidates_to_score)} / {len(candidates)} candidates")

    # Claude scoring
    scored = []
    for i, job in enumerate(candidates_to_score):
        print(f"  [{i+1}/{len(candidates_to_score)}] {job['title']} @ {job['company']}")
        result = claude_score(job)
        if result and result.get("score", 0) >= MIN_SCORE:
            job.update({
                "score":     result["score"],
                "reason":    result.get("reason", ""),
                "role_type": result.get("role_type", "adjacent"),
            })
            scored.append(job)
            # Register in tracker so Telegram button callbacks can update it later.
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
    af_count = sum(1 for j in candidates_to_score if j["source"]=="Arbetsformedlingen")
    li_count = sum(1 for j in candidates_to_score if j["source"]=="LinkedIn")
    remote_count = sum(1 for j in candidates_to_score if j["source"]=="LinkedIn Remote")
    header = (
        f"<b>Job radar - {datetime.now():%d %b %Y}</b>\n"
        f"Evaluated <b>{len(candidates_to_score)}</b> of {len(candidates)} new roles "
        f"(AF {af_count} - LI {li_count} - Remote {remote_count})\n"
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
