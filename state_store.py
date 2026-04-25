import json
import os

import requests


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE = os.environ.get("SUPABASE_STATE_TABLE", "job_agent_state")


def configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def backend_name():
    return "Supabase" if configured() else "local JSON/cache"


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "authorization": f"Bearer {SUPABASE_KEY}",
        "content-type": "application/json",
    }


def get_state(key, default=None):
    if not configured():
        return default

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    resp = requests.get(
        url,
        headers=_headers(),
        params={"key": f"eq.{key}", "select": "value"},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return default
    return rows[0].get("value", default)


def set_state(key, value):
    if not configured():
        return False

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    headers = _headers()
    headers["prefer"] = "resolution=merge-duplicates,return=minimal"
    resp = requests.post(
        url,
        headers=headers,
        params={"on_conflict": "key"},
        data=json.dumps({"key": key, "value": value}),
        timeout=15,
    )
    resp.raise_for_status()
    return True


def update_tracker_status(job_key, status, updated):
    tracker = get_state("tracker", {}) or {}
    tracker.setdefault(job_key, {})
    tracker[job_key]["status"] = status
    tracker[job_key]["updated"] = updated
    set_state("tracker", tracker)
    return tracker[job_key]
