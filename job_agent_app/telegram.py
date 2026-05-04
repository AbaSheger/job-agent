import json
from datetime import datetime

import requests

from .config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from .state import load_update_offset, save_tracker, save_update_offset


ROLE_LABEL = {
    "junior-dev": "DEV",
    "qa-test": "QA",
    "devops": "OPS",
    "adjacent": "ADJ",
    "long-shot": "TRY",
}

SOURCE_LABEL = {
    "Remotive": "REMOTE",
    "RemoteOK": "REMOTE",
    "Arbetsformedlingen": "AF",
}

STATUS_LABELS = {
    "applied": "Applied",
    "skip": "Not interested",
    "save": "Saved",
}


def score_label(score):
    if score >= 8:
        return "HIGH"
    if score >= 6:
        return "MED"
    return "LOW"


def tg(method, **kwargs):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            json=kwargs,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"  tg.{method} error: {exc}")
        return None


def process_callback_updates(tracker):
    offset = load_update_offset()
    params = {"timeout": 0, "allowed_updates": json.dumps(["callback_query"])}
    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        updates = response.json().get("result", [])
    except Exception as exc:
        error_text = str(exc)
        response = getattr(exc, "response", None)
        if response is not None:
            error_text += f" {response.text}"
        if "webhook" in error_text.lower():
            print("  Telegram webhook is active; skipping getUpdates polling")
            return tracker
        print(f"  tg.getUpdates error: {exc}")
        return tracker

    if not updates:
        return tracker

    changed = 0
    next_offset = offset

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
        if status not in STATUS_LABELS:
            continue

        tracker.setdefault(key, {})
        tracker[key]["status"] = status
        tracker[key]["updated"] = datetime.now().strftime("%Y-%m-%d")
        changed += 1

        if callback_id:
            tg(
                "answerCallbackQuery",
                callback_query_id=callback_id,
                text=STATUS_LABELS[status],
            )

    if next_offset is not None:
        save_update_offset(next_offset)
    if changed:
        save_tracker(tracker)
        print(f"  Processed {changed} Telegram button update(s)")
    return tracker


def send_plain(text):
    tg(
        "sendMessage",
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def send_job(job):
    src = SOURCE_LABEL.get(job.get("source", ""), "JOB")
    role = ROLE_LABEL.get(job.get("role_type", ""), "JOB")
    text = (
        f"[{score_label(job['score'])}] <b>{job['score']}/10</b> "
        f"{role} {src}  {job['title']}\n"
        f"<i>{job['company']} - {job['location']}</i>\n"
        f"{job.get('reason', '')}\n"
    )
    if job["url"].startswith("http"):
        text += f"<a href=\"{job['url']}\">Apply -></a>"
    else:
        text += "Search manually"
    if job.get("published"):
        text += f"  -  {job['published']}"

    key = job["key"]
    keyboard = {
        "inline_keyboard": [[
            {"text": "Applied", "callback_data": f"applied|{key}"},
            {"text": "Not interested", "callback_data": f"skip|{key}"},
            {"text": "Save", "callback_data": f"save|{key}"},
        ]]
    }

    tg(
        "sendMessage",
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )


def pipeline_summary(tracker):
    counts = {"applied": 0, "save": 0, "skip": 0}
    for item in tracker.values():
        status = item.get("status")
        if status in counts:
            counts[status] += 1

    if sum(counts.values()) == 0:
        return ""

    return (
        f"<b>Your pipeline</b>\n"
        f"Applied: {counts['applied']}  "
        f"Saved: {counts['save']}  "
        f"Skipped: {counts['skip']}\n"
        "---------------------\n"
    )

