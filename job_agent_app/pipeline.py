import time
from datetime import datetime

import state_store

from .config import MAX_JOBS_MSG, MIN_LOCAL_PRIORITY, MIN_SCORE
from .filters import (
    candidate_priority,
    diversify_candidates,
    is_location_eligible,
    is_recent_job,
    pre_filter,
)
from .scoring import claude_score_batch
from .sources import collect_all_sources
from .state import load_seen, load_tracker, save_seen, save_tracker
from .telegram import pipeline_summary, process_callback_updates, send_job, send_plain


def select_candidates(all_jobs, seen, tracker):
    actioned_keys = {
        key for key, value in tracker.items()
        if value.get("status") in ("applied", "skip")
    }
    new_jobs = [
        job for job in all_jobs.values()
        if job["key"] not in seen and job["key"] not in actioned_keys
    ]
    candidates = [job for job in new_jobs if pre_filter(job["title"], job["desc"])]
    candidates = [job for job in candidates if is_recent_job(job)]
    candidates = [job for job in candidates if is_location_eligible(job)]
    candidates = [
        job for job in candidates
        if candidate_priority(job) >= MIN_LOCAL_PRIORITY
    ]
    candidates.sort(key=candidate_priority, reverse=True)
    return new_jobs, diversify_candidates(candidates), candidates


def build_tracker_entry(job):
    return {
        "title": job["title"],
        "company": job["company"],
        "url": job["url"],
        "score": job["score"],
        "source": job["source"],
        "status": "new",
        "added": datetime.now().strftime("%Y-%m-%d"),
    }


def score_candidates(candidates_to_score, tracker):
    scored = []
    jobs_by_key = {job["key"]: job for job in candidates_to_score}

    for result in claude_score_batch(candidates_to_score):
        job = jobs_by_key.get(result.get("key"))
        if not job or result.get("score", 0) < MIN_SCORE:
            continue

        job.update({
            "score": result["score"],
            "reason": result.get("reason", ""),
            "role_type": result.get("role_type", "adjacent"),
        })
        scored.append(job)
        tracker[job["key"]] = build_tracker_entry(job)

    save_tracker(tracker)
    scored.sort(key=lambda job: job["score"], reverse=True)
    return scored


def send_digest(top, tracker, candidates_to_score, candidate_count):
    af_count = count_source(candidates_to_score, "Arbetsformedlingen")
    remotive_count = count_source(candidates_to_score, "Remotive")
    remoteok_count = count_source(candidates_to_score, "RemoteOK")
    header = (
        f"<b>Job radar - {datetime.now():%d %b %Y}</b>\n"
        f"Evaluated <b>{len(candidates_to_score)}</b> of {candidate_count} "
        f"new roles (AF {af_count} - Remotive {remotive_count} - "
        f"RemoteOK {remoteok_count})\n"
        f"<b>{len(top)}</b> worth applying - tap to track\n"
        "---------------------\n"
    )

    summary = pipeline_summary(tracker)
    send_plain(summary + header if summary else header)
    time.sleep(0.3)

    if not top:
        send_plain(f"None scored above {MIN_SCORE}/10 today. Check back tomorrow.")
        return

    for job in top:
        send_job(job)
        time.sleep(0.4)


def count_source(jobs, source):
    return sum(1 for job in jobs if job["source"] == source)


def log_collection_counts(jobtech_pool, remotive_pool, remoteok_pool, all_jobs):
    print(
        f"  Total unique: {len(all_jobs)} "
        f"(AF: {len(jobtech_pool)}, Remotive: {len(remotive_pool)}, "
        f"RemoteOK: {len(remoteok_pool)})"
    )


def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Job agent starting...")
    print(f"  State backend: {state_store.backend_name()}")

    seen = load_seen()
    tracker = process_callback_updates(load_tracker())

    jobtech_pool, remotive_pool, remoteok_pool = collect_all_sources()
    all_jobs = {**jobtech_pool, **remotive_pool, **remoteok_pool}
    log_collection_counts(jobtech_pool, remotive_pool, remoteok_pool, all_jobs)

    new_jobs, candidates_to_score, candidates = select_candidates(
        all_jobs,
        seen,
        tracker,
    )
    skipped_repeat_count = len(all_jobs) - len(new_jobs)
    print(
        f"  New + not actioned: {len(new_jobs)}  "
        f"After pre-filter + location: {len(candidates)}"
    )
    print(f"  Skipped already seen/actioned: {skipped_repeat_count}")
    print(
        f"  Batch scoring with Claude: {len(candidates_to_score)} / "
        f"{len(candidates)} candidates"
    )

    scored = score_candidates(candidates_to_score, tracker)
    top = scored[:MAX_JOBS_MSG]
    print(f"  Scored >= {MIN_SCORE}: {len(scored)}  Sending top: {len(top)}")

    send_digest(top, tracker, candidates_to_score, len(candidates))

    seen.update(all_jobs.keys())
    save_seen(seen)
    print("  Done.")
