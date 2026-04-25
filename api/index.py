import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler

import requests

import state_store


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

STATUS_LABELS = {
    "applied": "Applied",
    "skip": "Not interested",
    "save": "Saved",
}


def telegram(method, **payload):
    if not TELEGRAM_TOKEN:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
        json=payload,
        timeout=10,
    ).raise_for_status()


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"ok": True, "service": "job-agent-telegram-webhook"})

    def do_POST(self):
        if WEBHOOK_SECRET:
            secret = self.headers.get("x-telegram-bot-api-secret-token")
            if secret != WEBHOOK_SECRET:
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return

        length = int(self.headers.get("content-length", "0"))
        try:
            update = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid json"})
            return

        callback = update.get("callback_query") or {}
        data = callback.get("data", "")
        callback_id = callback.get("id")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}

        if str(chat.get("id")) != str(TELEGRAM_CHAT_ID):
            self._send_json(200, {"ok": True, "ignored": "wrong chat"})
            return

        if "|" not in data:
            self._send_json(200, {"ok": True, "ignored": "unknown callback"})
            return

        status, job_key = data.split("|", 1)
        if status not in STATUS_LABELS:
            self._send_json(200, {"ok": True, "ignored": "unknown status"})
            return

        if not state_store.configured():
            self._send_json(500, {"ok": False, "error": "supabase not configured"})
            return

        state_store.update_tracker_status(
            job_key=job_key,
            status=status,
            updated=datetime.utcnow().strftime("%Y-%m-%d"),
        )

        if callback_id:
            telegram("answerCallbackQuery", callback_query_id=callback_id, text=STATUS_LABELS[status])

        self._send_json(200, {"ok": True, "status": status})
