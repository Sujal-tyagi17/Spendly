"""Hybrid, rule-first transaction categorization.

Order of decisions for every transaction:

1. **Type rules** (``type_rules`` in config/rules.json) — recognise internal
   transfers, credit-card repayments, refunds, salary, rent, ATM cash, etc.
   These decide the *transaction type* as well as the category.
2. **Default type from direction** — a debit is an expense; a credit with no
   rule is "other" (it is NOT assumed to be income — money from a friend is
   not salary).
3. **Merchant category** — known merchants map to a category.
   A *credit* from a known shop/food merchant is treated as a refund.
4. Nothing matched → category "Other", method "none", flagged for review.

The optional AI step (src/ai.py) only ever fills in rows left at step 4,
and its answers are validated against the allowed category list.
"""

from __future__ import annotations

from dataclasses import dataclass

from src import config
from src.merchant_normalizer import MerchantResult, clean_description, normalize_merchant
from src.rules import RuleSet, load_rules

# Credits from these categories are almost always refunds, not income.
_REFUNDABLE_CATEGORIES = {
    "Food & Dining", "Groceries", "Shopping", "Transport", "Travel",
    "Entertainment", "Subscriptions", "Healthcare", "Education", "Bills & Utilities",
}


@dataclass(frozen=True)
class Categorization:
    merchant: str
    merchant_method: str
    transaction_type: str
    category: str
    method: str  # "rule" | "merchant" | "ai" | "manual" | "none" ("user_rule" is set by the pipeline)
    rule_name: str | None
    needs_review: bool
    review_reason: str | None


def categorize(description: str, direction: str, rules: RuleSet | None = None) -> Categorization:
    rules = rules or load_rules()
    merchant: MerchantResult = normalize_merchant(description, rules)
    searchable = clean_description(description)

    # 1. Type rules
    for rule in rules.type_rules:
        if rule.direction and rule.direction != direction:
            continue
        if rule.pattern.search(searchable):
            merchant_name = merchant.merchant
            if rule.merchant and merchant.method != "alias":
                merchant_name = rule.merchant
            return Categorization(
                merchant=merchant_name,
                merchant_method=merchant.method,
                transaction_type=rule.transaction_type,
                category=rule.category,
                method="rule",
                rule_name=rule.name,
                needs_review=False,
                review_reason=None,
            )

    # 2 + 3. Direction default, then merchant category
    if direction == "debit":
        if merchant.alias_category:
            return Categorization(merchant.merchant, merchant.method, "expense",
                                  merchant.alias_category, "merchant", None, False, None)
        return Categorization(merchant.merchant, merchant.method, "expense",
                              config.UNCATEGORIZED, "none", None, True, "No rule matched this merchant")

    # Credits
    if merchant.alias_category in _REFUNDABLE_CATEGORIES:
        return Categorization(merchant.merchant, merchant.method, "refund", "Refunds", "merchant",
                              "credit_from_merchant", True,
                              "Credit from a merchant — treated as a refund, please confirm")
    return Categorization(merchant.merchant, merchant.method, "other", config.UNCATEGORIZED, "none",
                          None, True, "Credit with no matching rule (not assumed to be income)")


def is_valid_category(category: str) -> bool:
    return category in config.CATEGORIES


def type_for_manual_category(category: str, direction: str, current_type: str) -> str:
    """Keep transaction type consistent when a user re-categorizes a row."""
    if category == "Income" and direction == "credit":
        return "income"
    if category == "Refunds" and direction == "credit":
        return "refund"
    if category == "Transfers":
        return current_type if current_type in {"transfer", "cc_repayment"} else "transfer"
    if direction == "debit":
        return "expense"
    return current_type if current_type in {"income", "refund", "other"} else "other"
