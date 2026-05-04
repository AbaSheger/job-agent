import json

import state_store

from .config import SEEN_FILE, TRACKER_FILE, UPDATE_OFFSET_FILE


def load_seen():
    remote_seen = state_store.get_state("seen_jobs")
    if remote_seen is not None:
        return set(remote_seen[-3000:])
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text())[-3000:])
    return set()


def save_seen(seen):
    payload = sorted(seen)[-3000:]
    if state_store.set_state("seen_jobs", payload):
        return
    SEEN_FILE.write_text(json.dumps(payload))


def load_tracker():
    remote_tracker = state_store.get_state("tracker")
    if remote_tracker is not None:
        return remote_tracker
    if TRACKER_FILE.exists():
        return json.loads(TRACKER_FILE.read_text())
    return {}


def save_tracker(data):
    if state_store.set_state("tracker", data):
        return
    TRACKER_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_update_offset():
    remote_offset = state_store.get_state("telegram_update_offset")
    if remote_offset is not None:
        try:
            return int(remote_offset)
        except (TypeError, ValueError):
            return None
    if UPDATE_OFFSET_FILE.exists():
        try:
            return int(UPDATE_OFFSET_FILE.read_text().strip())
        except ValueError:
            return None
    return None


def save_update_offset(offset):
    if state_store.set_state("telegram_update_offset", offset):
        return
    UPDATE_OFFSET_FILE.write_text(str(offset))

