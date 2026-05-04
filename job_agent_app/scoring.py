import json

import requests

from .config import (
    ANTHROPIC_KEY,
    CLAUDE_MODEL,
    MAX_BATCH_RESULTS,
    MAX_DESC_CHARS,
    MIN_SCORE,
    PROFILE,
)


EVAL_SYSTEM = (
    "You are a recruiter evaluating job fit. "
    "Respond with valid JSON only - no markdown, no text outside the JSON."
)

SYSTEM_BLOCK = [
    {
        "type": "text",
        "text": EVAL_SYSTEM + "\n\nCandidate profile:\n" + PROFILE,
        "cache_control": {"type": "ephemeral"},
    }
]

TARGET_ROLE_PROMPT = (
    "realistic junior/graduate software roles, QA automation, test automation, "
    "application/technical/cloud support, integration developer, system developer, "
    "junior DevOps, technical consultant, implementation consultant, and SQL/API "
    "application specialist roles"
)

EVAL_PROMPT = """Job:
Title: {title}
Company: {company}
Location: {location}
Source: {source}
Description: {description}

Evaluate fit honestly. Consider: direct skill match, adjacent fit, suitability for someone
with no commercial dev experience, Swedish market context, and remote roles outside Sweden
only when the company is reputable, EU-friendly, and realistic for a junior candidate.
Strongly penalize job-board spam, talent-pool posts, AI-training/task work, freelance
marketplaces, vague agency listings, and listings without a concrete engineering role.

Return exactly:
{{
  "score": <1-10>,
  "reason": "<one concrete sentence citing a specific technology or requirement>",
  "role_type": "<junior-dev|qa-test|devops|adjacent|long-shot>"
}}

Score guide: 9-10 strong match, 7-8 good fit, 5-6 adjacent/worth trying, 1-4 skip."""

BATCH_EVAL_PROMPT = """Jobs:
{jobs}

Evaluate these jobs for the candidate above. Prefer {target_roles}, Swedish/local
roles, and reputable EU-friendly remote companies. Penalize internships, unrealistic
senior expectations, vague staffing spam, talent-pool posts, AI-training/task work,
freelance marketplaces, and duplicate roles from the same company.

Return valid JSON only, jobs ranked by fit score descending:
{{
  "jobs": [
    {{
      "key": "<job key>",
      "score": <1-10>,
      "reason": "<one concrete sentence citing a specific technology or requirement>",
      "role_type": "<junior-dev|qa-test|devops|adjacent|long-shot>"
    }}
  ]
}}

Return at most {max_results} jobs. Only include jobs scoring {min_score}/10 or higher."""


def anthropic_headers():
    return {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def parse_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def claude_score(job):
    prompt = EVAL_PROMPT.format(
        title=job["title"],
        company=job["company"],
        location=job["location"],
        source=job["source"],
        description=job["desc"][:MAX_DESC_CHARS],
    )
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=anthropic_headers(),
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 200,
                "system": SYSTEM_BLOCK,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"]
        return parse_json_text(text)
    except Exception as exc:
        print(f"    Claude error for '{job['title']}': {exc}")
        return None


def format_batch_jobs(jobs):
    compact = []
    for index, job in enumerate(jobs, start=1):
        compact.append(
            "\n".join([
                f"{index}. key: {job['key']}",
                f"title: {job['title']}",
                f"company: {job['company']}",
                f"location: {job['location']}",
                f"source: {job['source']}",
                f"description: {job['desc'][:MAX_DESC_CHARS]}",
            ])
        )
    return "\n\n".join(compact)


def claude_score_batch(jobs):
    if not jobs:
        return []

    prompt = BATCH_EVAL_PROMPT.format(
        jobs=format_batch_jobs(jobs),
        target_roles=TARGET_ROLE_PROMPT,
        max_results=MAX_BATCH_RESULTS,
        min_score=MIN_SCORE,
    )
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=anthropic_headers(),
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 1400,
                "system": SYSTEM_BLOCK,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"]
        return parse_json_text(text).get("jobs", [])
    except Exception as exc:
        print(f"    Claude batch error: {exc}")
        return []

