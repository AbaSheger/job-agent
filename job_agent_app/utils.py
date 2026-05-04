import hashlib
import re


def job_key(title, company):
    raw = title.lower().strip() + "|" + company.lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()

