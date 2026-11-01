"""Privacy helpers: PII scrubbing for free text and a logging filter.

Design rules for zero storage of personal data:
  * No database, no files, no cache. Profiles live only in the request handler's memory.
  * The profile model has no free-text fields.
  * Free-text queries are scrubbed before any use (search, prompts to third parties).
  * Request bodies are never logged. A logging filter scrubs anything that slips through.

Names and street addresses cannot be reliably detected by patterns, which is why the
profile uses closed choices and the UI asks users not to type personal details.
"""
import logging
import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("AADHAAR", re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)")),
    ("PINCODE", re.compile(r"(?<!\d)\d{6}(?!\d)")),
]


def scrub_text(text: str) -> tuple[str, list[str]]:
    """Return (clean_text, kinds_found). Replaces identifiers with [REDACTED_KIND]."""
    found: list[str] = []
    for kind, pattern in _PATTERNS:
        if pattern.search(text):
            found.append(kind)
            text = pattern.sub(f"[REDACTED_{kind}]", text)
    return text, found


class PIIScrubFilter(logging.Filter):
    """Last line of defence: scrub identifiers from any log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        clean, found = scrub_text(message)
        if found:
            record.msg = clean
            record.args = ()
        return True


def install_log_filter() -> None:
    for name in ("civicease", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, PIIScrubFilter) for f in logger.filters):
            logger.addFilter(PIIScrubFilter())
