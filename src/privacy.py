"""Privacy helpers: masking identifiers and keeping sensitive text out of logs.

Spendly masks long digit runs (account / card numbers, UPI reference
numbers), phone numbers and e-mail / UPI IDs before anything is stored or
displayed. The original statement wording is otherwise preserved so users
can audit merchant normalization.
"""

from __future__ import annotations

import logging
import re

# 9+ digit runs: account numbers, card numbers, UPI/IMPS reference numbers.
_LONG_DIGITS = re.compile(r"\d{9,}")
# Already partially masked numbers such as XXXXXX1234 or ****1234.
_MASKED_NUMBER = re.compile(r"[xX*]{4,}\d{2,4}")
# Indian mobile numbers (+91 / 0 prefixes optional).
_PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?|0)?[6-9]\d{9}(?!\d)")
# e-mail addresses and UPI handles (name@bank).
_HANDLE = re.compile(r"[\w.\-+]+@[\w.\-]+")


def mask_digits(match: re.Match) -> str:
    digits = match.group(0)
    return "XXXX" + digits[-4:]


def mask_sensitive(text: str | None) -> str:
    """Mask identifiers while keeping the description readable."""
    if not text:
        return ""
    masked = _HANDLE.sub("[upi-id]", text)
    masked = _PHONE.sub("[phone]", masked)
    masked = _LONG_DIGITS.sub(mask_digits, masked)
    return masked


def sanitize_for_ai(text: str | None, max_length: int = 60) -> str:
    """Strip anything identifying before a merchant label is sent to an LLM.

    Only short merchant-like text survives: digits, handles and masked
    numbers are removed entirely, not just masked.
    """
    if not text:
        return ""
    cleaned = _HANDLE.sub(" ", text)
    cleaned = _MASKED_NUMBER.sub(" ", cleaned)
    cleaned = re.sub(r"\d+", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z&' ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


class RedactingFilter(logging.Filter):
    """Logging filter that masks identifiers in any message that slips through.

    The codebase deliberately logs only counts and statuses, never
    transaction descriptions — this filter is a second line of defence.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed log call
            return True
        record.msg = mask_sensitive(message)
        record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
