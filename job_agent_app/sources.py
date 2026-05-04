import time

import requests

from .config import JOBTECH_LIMIT, JOBTECH_URL, REMOTIVE_URL, REMOTEOK_URL
from .utils import job_key, strip_html


JOBTECH_BASE_QUERIES = [
    "java developer", "systemutvecklare java", "junior developer",
    "spring boot", "backend developer",
    "junior software engineer", "qa testare", "junior devops",
    "graduate developer", "junior .net",
    "javautvecklare", "backendutvecklare", "frontendutvecklare",
    "systemutvecklare junior", "nyexaminerad utvecklare",
    "testare junior", "qa engineer",
]

TARGET_JOBTECH_QUERIES = [
    "qa automation engineer", "test automation developer",
    "application support engineer", "technical support engineer",
    "integration developer", "system developer", "devops junior",
    "cloud support engineer", "technical consultant", "support developer",
    "systemförvaltare utveckling", "systemforvaltare utveckling",
    "applikationsspecialist sql", "applikationsspecialist api",
    "implementation consultant",
]

JOBTECH_QUERIES = JOBTECH_BASE_QUERIES + TARGET_JOBTECH_QUERIES
REMOTIVE_CATEGORIES = ["software-dev", "devops-sysadmin", "quality-assurance"]


def fetch_jobtech(query, limit=JOBTECH_LIMIT):
    try:
        response = requests.get(
            JOBTECH_URL,
            params={"q": query, "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("hits", [])
    except Exception as exc:
        print(f"    Jobtech error ({query!r}): {exc}")
        return []


def parse_jobtech(raw):
    addr = raw.get("workplace_address") or {}
    app = raw.get("application_details") or {}
    desc = raw.get("description") or {}
    title = raw.get("headline", "Unknown role")
    company = (raw.get("employer") or {}).get("name", "Unknown")
    return {
        "key": job_key(title, company),
        "title": title,
        "company": company,
        "location": addr.get("municipality") or addr.get("region") or "Sverige",
        "url": app.get("url") or "",
        "desc": desc.get("text", "") if isinstance(desc, dict) else "",
        "published": (raw.get("publication_date") or "")[:10],
        "source": "Arbetsformedlingen",
        "remote": False,
    }


def collect_jobtech():
    pool = {}
    for query in JOBTECH_QUERIES:
        print(f"    [{query}]")
        for raw in fetch_jobtech(query):
            job = parse_jobtech(raw)
            pool.setdefault(job["key"], job)
        time.sleep(0.4)
    return pool


def fetch_remotive(category):
    try:
        response = requests.get(
            REMOTIVE_URL,
            params={"category": category, "limit": 100},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 job-agent/1.0"},
        )
        response.raise_for_status()
        return response.json().get("jobs", [])
    except Exception as exc:
        print(f"    Remotive error ({category}): {exc}")
        return []


def parse_remotive(raw):
    title = raw.get("title", "Unknown role")
    company = raw.get("company_name", "Unknown")
    return {
        "key": job_key(title, company),
        "title": title,
        "company": company,
        "location": raw.get("candidate_required_location", "Remote"),
        "url": raw.get("url", ""),
        "desc": strip_html(raw.get("description", ""))[:4000],
        "published": (raw.get("publication_date") or "")[:10],
        "source": "Remotive",
        "remote": True,
    }


def collect_remotive():
    pool = {}
    for category in REMOTIVE_CATEGORIES:
        print(f"    [{category}]")
        for raw in fetch_remotive(category):
            job = parse_remotive(raw)
            pool.setdefault(job["key"], job)
        time.sleep(1)
    return pool


def fetch_remoteok():
    try:
        response = requests.get(
            REMOTEOK_URL,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 job-agent/1.0"},
        )
        response.raise_for_status()
        return [
            item for item in response.json()
            if isinstance(item, dict) and item.get("id")
        ]
    except Exception as exc:
        print(f"    RemoteOK error: {exc}")
        return []


def parse_remoteok(raw):
    title = raw.get("position", "Unknown role")
    company = raw.get("company", "Unknown")
    return {
        "key": job_key(title, company),
        "title": title,
        "company": company,
        "location": "Remote",
        "url": raw.get("apply_url") or raw.get("url", ""),
        "desc": strip_html(raw.get("description", ""))[:4000],
        "published": (raw.get("date") or "")[:10],
        "source": "RemoteOK",
        "remote": True,
    }


def collect_remoteok():
    pool = {}
    print("    [all remote jobs]")
    for raw in fetch_remoteok():
        job = parse_remoteok(raw)
        pool.setdefault(job["key"], job)
    return pool


def collect_all_sources():
    print("  Fetching Jobtech...")
    jobtech_pool = collect_jobtech()
    print("  Fetching Remotive...")
    remotive_pool = collect_remotive()
    print("  Fetching RemoteOK...")
    remoteok_pool = collect_remoteok()
    return jobtech_pool, remotive_pool, remoteok_pool

