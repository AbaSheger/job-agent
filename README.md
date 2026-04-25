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
- Supports optional Supabase state and a Vercel Telegram webhook for instant button tracking
- Runs manually or on a GitHub Actions schedule

## Public Repo Safety

Do not commit personal profile data, Telegram chat IDs, API keys, or generated tracker files.

This repo keeps those out of source control:

- `ANTHROPIC_API_KEY`, `TELEGRAM_TOKEN`, and `TELEGRAM_CHAT_ID` are read from GitHub Actions secrets.
- `CANDIDATE_PROFILE` can be stored as a GitHub Actions secret.
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` can be stored as GitHub/Vercel secrets for shared hosted state.
- `TELEGRAM_WEBHOOK_SECRET` can be stored as a Vercel secret to validate Telegram webhook requests.
- For local runs, `candidate_profile.txt` can be placed beside `job_agent.py`; it is ignored by Git.
- `seen_jobs.json` and `tracker.json` are generated runtime state and ignored by Git.
- On GitHub Actions, runtime state is stored in an Actions cache, not committed to the repository.

## Supabase + Vercel

The project works without hosted state, but Supabase and Vercel make Telegram buttons update immediately.

1. Create a Supabase project.
2. Run `supabase_schema.sql` in the Supabase SQL editor.
3. Add these GitHub Actions secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
4. Deploy this repo to Vercel.
5. Add these Vercel environment variables:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `TELEGRAM_WEBHOOK_SECRET`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
6. Register the Telegram webhook:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
  -d "url=https://YOUR_VERCEL_DOMAIN/api/telegram_webhook" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET" \
  -d 'allowed_updates=["callback_query"]'
```

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
pip install -r requirements.txt python-jobspy
```

Create `candidate_profile.txt` locally, then set the required environment variables and run:

```bash
python job_agent.py
```
