"""Money helpers.

All amounts are stored as **integer paise** (₹1 = 100 paise). Integers avoid
floating-point surprises such as 0.1 + 0.2 != 0.3, and Decimal is used only
while parsing text.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_CURRENCY_TOKENS = re.compile(r"(₹|rs\.?|inr)", re.IGNORECASE)
_DRCR_SUFFIX = re.compile(r"\s*\b(dr|cr)\.?\s*$", re.IGNORECASE)


class AmountParseError(ValueError):
    """Raised when text cannot be read as a money amount."""


def parse_amount(text: object) -> tuple[int, str | None]:
    """Parse an amount string into (paise, drcr_hint).

    ``drcr_hint`` is "debit"/"credit" when the text carried an explicit
    Dr/Cr marker or a sign, otherwise None.

    >>> parse_amount("₹1,23,456.50")
    (12345650, None)
    >>> parse_amount("500.00 Dr")
    (50000, 'debit')
    """
    if text is None:
        raise AmountParseError("empty amount")
    raw = str(text).strip()
    if not raw or raw in {"-", "--", "—"}:
        raise AmountParseError("empty amount")

    hint: str | None = None
    suffix = _DRCR_SUFFIX.search(raw)
    if suffix:
        hint = "debit" if suffix.group(1).lower() == "dr" else "credit"
        raw = raw[: suffix.start()]

    raw = _CURRENCY_TOKENS.sub("", raw).replace(",", "").replace(" ", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    if raw.startswith("+"):
        hint = hint or "credit"
        raw = raw[1:]
    elif raw.startswith("-"):
        hint = hint or "debit"
        raw = raw[1:]

    if not re.fullmatch(r"\d+(\.\d{1,2})?", raw):
        raise AmountParseError(f"not a valid amount: {text!r}")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:  # pragma: no cover - regex guards this
        raise AmountParseError(f"not a valid amount: {text!r}") from exc
    return int((value * 100).to_integral_value()), hint


def try_parse_amount(text: object) -> int | None:
    """Return paise or None for blank / unparseable cells."""
    try:
        return parse_amount(text)[0]
    except AmountParseError:
        return None


def _indian_grouping(integer_part: str) -> str:
    if len(integer_part) <= 3:
        return integer_part
    last3 = integer_part[-3:]
    rest = integer_part[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups + [last3])


def format_inr(paise: int | float | None, decimals: bool = False) -> str:
    """Format paise as Indian Rupees with lakh/crore grouping.

    >>> format_inr(12345650)
    '₹1,23,457'
    >>> format_inr(12345650, decimals=True)
    '₹1,23,456.50'
    """
    if paise is None:
        return "—"
    paise = int(round(paise))
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    if decimals:
        rupees, rem = divmod(paise, 100)
        return f"{sign}₹{_indian_grouping(str(rupees))}.{rem:02d}"
    rupees = (paise + 50) // 100  # round half up
    return f"{sign}₹{_indian_grouping(str(rupees))}"


def format_inr_compact(paise: int | float | None, precision: int = 1) -> str:
    """Short labels for chart axes: ₹950, ₹12.5K, ₹1.2L, ₹3.4Cr."""
    if paise is None:
        return "—"
    rupees = paise / 100
    sign = "-" if rupees < 0 else ""
    r = abs(rupees)

    def short(value: float, suffix: str) -> str:
        text = f"{value:.{precision}f}".rstrip("0").rstrip(".")
        return f"{sign}₹{text}{suffix}"

    if r >= 1_00_00_000:
        return short(r / 1_00_00_000, "Cr")
    if r >= 1_00_000:
        return short(r / 1_00_000, "L")
    if r >= 1_000:
        return short(r / 1_000, "K")
    return f"{sign}₹{r:.0f}"


def paise_to_rupees(paise: int | None) -> float | None:
    """For display / charts only — never for further arithmetic."""
    return None if paise is None else paise / 100
