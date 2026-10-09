"""HTTP hardening: security headers and a per-client rate limiter."""

from __future__ import annotations

import threading
import time
from collections import deque

FONT_CSS = "https://fonts.googleapis.com"
FONT_FILES = "https://fonts.gstatic.com"


def content_security_policy(web_fonts: bool) -> str:
    styles = f"'self' {FONT_CSS}" if web_fonts else "'self'"
    fonts = f"'self' {FONT_FILES}" if web_fonts else "'self'"
    return (f"default-src 'self'; script-src 'self'; style-src {styles}; font-src {fonts}; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'")


def security_headers(web_fonts: bool) -> dict[str, str]:
    return {
        "Content-Security-Policy": content_security_policy(web_fonts),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    }


class RateLimiter:
    """Sliding one-minute window per client. In-process only: put a shared
    limiter (for example at the reverse proxy) in front of multi-process
    deployments."""

    def __init__(self, per_minute: int, window: float = 60.0) -> None:
        self.per_minute = per_minute
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client: str, now: float | None = None) -> tuple[bool, int]:
        """(allowed, seconds until a slot frees up)."""
        if self.per_minute <= 0:
            return True, 0
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False, max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > 10_000:
                for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    del self._hits[key]
            return True, 0
