"""Canonical metric definitions, shared by every SQL file.

SQL files refer to these with ``{{name}}`` placeholders, e.g.

    SUM(CASE WHEN {{is_expense}} THEN amount_paise ELSE 0 END)

``analytics.load_sql`` substitutes them before the query runs, so the rule for
"what counts as spending" lives in exactly one place. Change it here and every
query, chart, insight and API response changes together.

All amounts are integer paise and always positive; ``direction`` says whether
money left (debit) or arrived (credit).
"""

from __future__ import annotations

import re

DEFINITIONS: dict[str, tuple[str, str]] = {
    # name: (SQL predicate / expression, plain-English meaning)
    "is_expense": (
        "(transaction_type = 'expense' AND direction = 'debit')",
        "Spending: debits classified as expenses. Excludes own-account transfers and credit-card bill "
        "payments (the card purchases are the spending).",
    ),
    "is_refund": (
        "(transaction_type = 'refund' AND direction = 'credit')",
        "Money returned by a merchant.",
    ),
    "is_income": (
        "(transaction_type = 'income' AND direction = 'credit')",
        "Salary, stipend, interest and dividends. Money from friends is not income.",
    ),
    "is_transfer": (
        "(transaction_type = 'transfer')",
        "Money moved between your own accounts, in either direction. Never income or spending.",
    ),
    "is_cc_repayment": (
        "(transaction_type = 'cc_repayment')",
        "Credit-card bill payment. Excluded from spending to avoid double counting.",
    ),
    "is_weekend": (
        "(CAST(strftime('%w', transaction_date) AS INTEGER) IN (0, 6))",
        "Saturday or Sunday.",
    ),
    "cash_flow_paise": (
        "(CASE WHEN transaction_type = 'transfer' THEN 0 "
        "WHEN direction = 'credit' THEN amount_paise ELSE -amount_paise END)",
        "Signed contribution to net cash flow: credits minus debits, internal transfers excluded. "
        "Card-bill payments are included because the money really left the account.",
    ),
}

_TOKEN = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


class UnknownMetricError(KeyError):
    pass


def render(sql: str) -> str:
    """Replace ``{{name}}`` placeholders with the canonical SQL."""
    def sub(match: re.Match) -> str:
        name = match.group(1)
        if name not in DEFINITIONS:
            raise UnknownMetricError(f"Unknown metric placeholder {{{{{name}}}}}")
        return DEFINITIONS[name][0]
    return _TOKEN.sub(sub, sql)


def glossary() -> dict[str, str]:
    return {name: meaning for name, (_, meaning) in DEFINITIONS.items()}
