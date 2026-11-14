import re
import secrets
import time
from threading import Lock


def redact(text: str) -> str:
    text = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|token|api[_-]?key|secret)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    return re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)


class Confirmations:
    """Server-owned single-use capabilities. Tool/model arguments cannot grant consent."""

    def __init__(self, ttl=120):
        self.ttl = ttl
        self.pending = {}
        self.lock = Lock()

    def issue(self, call):
        with self.lock:
            now = time.monotonic()
            self.pending = {k: v for k, v in self.pending.items() if v[0] > now}
            if len(self.pending) >= 1000:
                raise ValueError("Too many pending confirmations")
            token = secrets.token_urlsafe(32)
            self.pending[token] = (now + self.ttl, call)
            return token

    def consume(self, token):
        with self.lock:
            item = self.pending.pop(token, None)
        if not item or item[0] <= time.monotonic():
            raise PermissionError("Confirmation is invalid, expired, or already used")
        return item[1]
