# Job Agent

Daily AI-assisted job search agent for Sweden. It collects roles from Jobtech and LinkedIn, filters out poor fits, asks Claude to score each remaining job against a candidate profile, and sends a ranked Telegram digest every morning.

The project is intentionally small: one scheduled Python workflow, public job APIs/scraping, a private profile prompt, local JSON state, and Telegram delivery.

## Features

- Searches Arbetsformedlingen Jobtech and LinkedIn via `python-jobspy`
- Includes a small remote-role search for reputable international companies
- Deduplicates roles across sources
- Filters obvious senior/poor-fit roles before using an LLM
- Caps Claude scoring to a small set of locally ranked candidates to control API cost
- Scores jobs with Claude using structured JSON output
- Sends a ranked Telegram digest with apply/save/skip buttons
- Persists seen jobs and button state between GitHub Actions runs
- Runs manually or on a GitHub Actions schedule

## Public Repo Safety

Do not commit personal profile data, Telegram chat IDs, API keys, or generated tracker files.

This repo keeps those out of source control:

- `ANTHROPIC_API_KEY`, `TELEGRAM_TOKEN`, and `TELEGRAM_CHAT_ID` are read from GitHub Actions secrets.
- `CANDIDATE_PROFILE` can be stored as a GitHub Actions secret.
- For local runs, `candidate_profile.txt` can be placed beside `job_agent.py`; it is ignored by Git.
- `seen_jobs.json` and `tracker.json` are generated runtime state and ignored by Git.
- On GitHub Actions, runtime state is stored in an Actions cache, not committed to the repository.

## Setup

1. Fork or clone this repo.
2. Add these secrets in GitHub: Settings > Secrets and variables > Actions.
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ANTHROPIC_API_KEY`
   - `CANDIDATE_PROFILE`
3. Enable Actions in the Actions tab.
4. Trigger the workflow manually first to test it.

## Local Run

```bash
pip install -r requirements.txt
```

Create `candidate_profile.txt` locally, then set the required environment variables and run:

```bash
python job_agent.py
```
