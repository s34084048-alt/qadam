"""Logging that cannot leak PHI or image bytes.

Access logs record the route template, not the path, so a patient reference in
a URL segment never reaches a log file. A regex filter is the backstop.
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                    # email
    re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),                    # id-like numbers
    re.compile(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+"),   # inline images
]
_MAX = 2000


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = msg
        for pattern in _PATTERNS:
            redacted = pattern.sub("[redacted]", redacted)
        if len(redacted) > _MAX:
            redacted = redacted[:_MAX] + "…[truncated]"
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s")
    )
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(name).addFilter(RedactFilter())
