"""Optional Gemini integration. Spendly works fully without it.

AI is used only when BOTH are true:
    SPENDLY_ENABLE_AI=true   and   GEMINI_API_KEY is set

Two narrow jobs:

1. ``suggest_categories`` — given *merchant labels only* (sanitized: digits,
   UPI IDs and masked numbers removed), suggest one of Spendly's categories.
   Answers outside the allowed list are discarded. Suggestions are shown
   as "AI-suggested" and stay editable.
2. ``rephrase_insights`` — turn already-computed insight sentences into a
   short friendly summary. The model never calculates anything: if its text
   contains any number that wasn't in the input, the output is rejected and
   the deterministic text is used instead.

Full statements, balances, account numbers and dates are never sent.
An LLM's "confidence" is not a calibrated probability, so none is shown.
"""

from __future__ import annotations

import json
import re

import requests

from src import config
from src.privacy import get_logger, sanitize_for_ai

log = get_logger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
AI_CATEGORIES = [c for c in config.CATEGORIES if c not in {"Income", "Refunds", "Transfers"}]


class AIError(RuntimeError):
    """User-safe error message."""


def ai_status() -> tuple[bool, str]:
    settings = config.ai_settings()
    if not settings.enabled_flag:
        return False, "AI features are off (set SPENDLY_ENABLE_AI=true to enable)."
    if not settings.api_key:
        return False, "AI is enabled but GEMINI_API_KEY is not set."
    return True, f"AI enabled ({settings.model})."


def _generate(prompt: str) -> str:
    settings = config.ai_settings()
    if not settings.enabled:
        raise AIError("AI features are not enabled.")
    try:
        response = requests.post(
            API_URL.format(model=settings.model),
            headers={"x-goog-api-key": settings.api_key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}},
            timeout=settings.timeout_seconds,
        )
    except requests.RequestException as exc:
        log.warning("Gemini request failed: %s", type(exc).__name__)
        raise AIError("Could not reach the Gemini API. Check your internet connection and try again.") from exc

    if response.status_code == 429:
        raise AIError("Gemini rate limit reached. Wait a minute and try again — rule-based results are kept.")
    if response.status_code in (401, 403):
        raise AIError("Gemini rejected the API key. Check GEMINI_API_KEY.")
    if response.status_code >= 400:
        log.warning("Gemini returned HTTP %s", response.status_code)
        raise AIError(f"Gemini returned an error (HTTP {response.status_code}).")
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as exc:
        raise AIError("Gemini returned an unexpected response.") from exc


def preview_payload(merchants: list[str]) -> list[str]:
    """Exactly what would be sent — shown to the user before they click."""
    labels = []
    for m in merchants:
        label = sanitize_for_ai(m)
        if label and label not in labels:
            labels.append(label)
    return labels[: config.ai_settings().max_merchants_per_request]


def suggest_categories(merchants: list[str]) -> dict[str, str]:
    """Return {original merchant: category} for answers that pass validation."""
    sanitized = {m: sanitize_for_ai(m) for m in merchants}
    labels = preview_payload(merchants)
    if not labels:
        return {}
    prompt = (
        "You categorize Indian personal-finance merchants. For each merchant label, choose exactly one "
        f"category from this list: {json.dumps(AI_CATEGORIES)}. If unsure, use \"Other\". "
        "Reply with a JSON object mapping each label to its category and nothing else.\n"
        f"Labels: {json.dumps(labels)}"
    )
    raw = _generate(prompt)
    try:
        answer = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIError("Gemini's answer was not valid JSON; nothing was changed.") from exc
    if not isinstance(answer, dict):
        raise AIError("Gemini's answer had the wrong shape; nothing was changed.")

    result = {}
    for original, label in sanitized.items():
        category = answer.get(label)
        if isinstance(category, str) and category in AI_CATEGORIES and category != "Other":
            result[original] = category
    log.info("AI suggested categories for %d of %d merchants", len(result), len(labels))
    return result


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def validate_rephrase(source_texts: list[str], output: str) -> bool:
    """Every number in the AI output must appear in the deterministic insights."""
    allowed = set().union(*(_numbers(t) for t in source_texts)) if source_texts else set()
    return _numbers(output) <= allowed


def rephrase_insights(texts: list[str]) -> str | None:
    """Return a friendly 2–3 sentence summary, or None if validation fails."""
    if not texts:
        return None
    prompt = (
        "Rewrite these personal-finance facts as a friendly 2-3 sentence summary for the user. "
        "Use ONLY the facts and numbers given; do not calculate, round or add any number. "
        'Reply as JSON: {"summary": "..."}\nFacts:\n' + "\n".join(f"- {t}" for t in texts)
    )
    raw = _generate(prompt)
    try:
        summary = json.loads(raw)["summary"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(summary, str) or not validate_rephrase(texts, summary):
        log.info("AI summary rejected by number validation")
        return None
    return summary.strip()
