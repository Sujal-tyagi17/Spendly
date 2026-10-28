"""Turns raw statement descriptions into clean merchant names.

    UPI/DR/412345678901/ZOMATO/YESB/zomato@ybl/Payment  ->  Zomato
    ZOMATO*ORDER123                                    ->  Zomato
    POS 4111XXXXXXXX1111 AMZN MKTPLACE                 ->  Amazon
    Paid to Sharma General Store                       ->  Sharma General Store

Approach (deterministic, in this order):
1. Clean the text: upper-case, drop reference numbers, UPI handles,
   masked card numbers and "*ORDER123"-style suffixes.
2. Alias match: check the cleaned text against the merchant patterns in
   ``config/rules.json``. First match wins.
3. Fallback: take the first meaningful segment of the description after
   removing banking noise words (UPI, NEFT, DR, bank IFSC codes ...).

Fuzzy matching is deliberately *not* used to merge merchants: "Amazon" and
"Amazing Bakery" are similar strings but different businesses. Unknown
merchants keep their own cleaned name instead of being merged by guesswork.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.rules import RuleSet, load_rules

_HANDLE = re.compile(r"[\w.\-+]+@[\w.\-]+")
_MASKED = re.compile(r"[X*]{2,}\d{0,4}", re.IGNORECASE)
_ORDER_SUFFIX = re.compile(r"\*\s*[A-Z0-9]+")
_DIGITS = re.compile(r"\d+")
_PREFIX_PHRASES = re.compile(
    r"^(PAID TO|PAYMENT TO|RECEIVED FROM|MONEY SENT TO|SENT TO|TRANSFER TO|TRANSFER FROM)\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MerchantResult:
    merchant: str
    method: str  # "alias" | "fallback" | "unknown"
    alias_category: str | None = None


def clean_description(description: str) -> str:
    """Upper-case and strip identifiers/noise characters, keep words."""
    text = (description or "").upper()
    text = _HANDLE.sub(" ", text)
    text = _MASKED.sub(" ", text)
    text = _ORDER_SUFFIX.sub(" ", text)
    text = _DIGITS.sub(" ", text)
    text = re.sub(r"[_|:;,#()\[\]{}\"]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _title(text: str) -> str:
    words = []
    for word in text.split():
        if len(word) <= 3 and word.isalpha() and word in {"ATM", "UPI", "EMI", "LIC", "HP"}:
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _fallback_name(description: str, rules: RuleSet) -> str | None:
    text = _PREFIX_PHRASES.sub("", (description or "").strip())
    segments = re.split(r"[/\\\-]| {2,}", text) if "/" in text or "\\" in text else [text]
    for segment in segments:
        cleaned = clean_description(segment)
        tokens = [
            t
            for t in re.split(r"[\s.]+", cleaned)
            if t
            and t not in rules.noise_tokens
            and t not in rules.bank_codes
            and len(t) > 1
            and re.search(r"[A-Z]", t)
        ]
        if tokens:
            return _title(" ".join(tokens[:4]))
    return None


def normalize_merchant(description: str, rules: RuleSet | None = None) -> MerchantResult:
    rules = rules or load_rules()
    cleaned = clean_description(_PREFIX_PHRASES.sub("", description or ""))
    # Treat "/" and "-" as spaces for alias matching (UPI/ZOMATO/...).
    searchable = re.sub(r"[/\\\-]", " ", cleaned)
    searchable = re.sub(r"\s+", " ", searchable)

    for rule in rules.merchants:
        if any(p.search(searchable) for p in rule.patterns):
            return MerchantResult(rule.name, "alias", rule.category)

    fallback = _fallback_name(description, rules)
    if fallback:
        return MerchantResult(fallback, "fallback", None)
    return MerchantResult("Unknown", "unknown", None)
