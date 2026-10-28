import json

import pytest

from src import config, pipeline
from src.categorizer import categorize, type_for_manual_category
from src.rules import RulesConfigError, load_rules, parse_rules


@pytest.mark.parametrize("description, direction, ttype, category", [
    ("UPI/DR/1/ZOMATO/YESB/z@ybl", "debit", "expense", "Food & Dining"),
    ("SWIGGY INSTAMART ORDER", "debit", "expense", "Groceries"),
    ("UPI/DR/1/SWIGGY/ICIC", "debit", "expense", "Food & Dining"),
    ("UBER INDIA TRIP", "debit", "expense", "Transport"),
    ("ACH/DR/1/NETFLIX.COM", "debit", "expense", "Subscriptions"),
    ("NEFT/CR/1/ACME LTD/SALARY JUL 2026", "credit", "income", "Income"),
    ("IMPS/DR/1/SELF TRANSFER TO OWN A/C", "debit", "transfer", "Transfers"),
    ("SWEEP IN FROM OWN A/C", "credit", "transfer", "Transfers"),
    ("BILLDESK/CREDIT CARD PAYMENT/HDFC", "debit", "cc_repayment", "Transfers"),
    ("UPI/CR/1/AMAZON REFUND", "credit", "refund", "Refunds"),
    ("IMPS/DR/1/HOUSE RENT/LANDLORD", "debit", "expense", "Rent & Housing"),
    ("ATM WDL/XXXX1111/MG ROAD", "debit", "expense", "Other"),
    ("BBPS/BESCOM ELECTRICITY BILL", "debit", "expense", "Bills & Utilities"),
    ("YOUTUBE PREMIUM", "debit", "expense", "Subscriptions"),  # not caught by an insurance "premium" rule
])
def test_rule_based_categorization(description, direction, ttype, category):
    result = categorize(description, direction)
    assert (result.transaction_type, result.category) == (ttype, category)
    assert result.method in {"rule", "merchant"}


def test_unknown_debit_is_flagged_for_review():
    result = categorize("UPI/DR/1/GREEN LEAF SALON/SBIN", "debit")
    assert result.transaction_type == "expense"
    assert result.category == config.UNCATEGORIZED
    assert result.method == "none" and result.needs_review


def test_credit_is_not_assumed_to_be_income():
    result = categorize("UPI/CR/1/ROHAN MEHTA/HDFC", "credit")
    assert result.transaction_type == "other"
    assert result.category != "Income"


def test_credit_from_known_merchant_is_treated_as_refund_and_flagged():
    result = categorize("UPI/CR/1/ZOMATO/YESB", "credit")
    assert result.transaction_type == "refund"
    assert result.needs_review  # user should confirm


def test_rule_direction_constraint():
    # "SALARY" on a debit (e.g. paying a cook's salary) is not income.
    result = categorize("UPI/DR/1/SALARY FOR COOK", "debit")
    assert result.transaction_type == "expense"


def test_every_configured_category_is_valid():
    rules = load_rules()
    for merchant in rules.merchants:
        assert merchant.category in config.CATEGORIES
    for rule in rules.type_rules:
        assert rule.category in config.CATEGORIES


def test_invalid_rules_config_is_rejected():
    with pytest.raises(RulesConfigError):
        parse_rules({"merchants": [{"name": "X", "patterns": ["X"], "category": "Gambling"}]})
    with pytest.raises(RulesConfigError):
        parse_rules({"merchants": [{"name": "X", "patterns": ["(unclosed"], "category": "Other"}]})


def test_manual_category_keeps_type_consistent():
    assert type_for_manual_category("Income", "credit", "other") == "income"
    assert type_for_manual_category("Food & Dining", "debit", "expense") == "expense"
    assert type_for_manual_category("Transfers", "debit", "expense") == "transfer"
    assert type_for_manual_category("Transfers", "debit", "cc_repayment") == "cc_repayment"


def test_demo_pipeline_matches_ground_truth(demo_conn, demo_truth):
    """The synthetic CSV carries ground-truth labels; every row must match."""
    truth = [t for t in demo_truth if t["truth_type"] != "duplicate"]
    rows = [dict(r) for r in demo_conn.execute(
        "SELECT transaction_type, category FROM transactions ORDER BY id")]
    assert len(rows) == len(truth)
    mismatches = [(t["description"], t["truth_type"], t["truth_category"], r)
                  for t, r in zip(truth, rows)
                  if (t["truth_type"], t["truth_category"]) != (r["transaction_type"], r["category"])]
    assert mismatches == []


def test_ai_suggestions_only_fill_uncategorized_debits(small_conn):
    from tests.conftest import SMALL_CSV
    preview = pipeline.prepare_csv_rows_import(SMALL_CSV, display_name="x", conn=None)
    changed = pipeline.apply_ai_suggestions(preview, {"Rohan Mehta": "Education", "Zomato": "Travel"})
    # Rohan Mehta is a *credit* and Zomato is already rule-categorized -> nothing changes.
    assert changed == 0
    preview2 = pipeline.prepare_csv_rows_import(
        "date,description,debit,credit,balance\n2026-01-01,UPI/DR/1/GREEN LEAF SALON/SBIN,200,,\n",
        display_name="y", conn=None)
    assert pipeline.apply_ai_suggestions(preview2, {"Green Leaf Salon": "Not a category"}) == 0
    assert pipeline.apply_ai_suggestions(preview2, {"Green Leaf Salon": "Shopping"}) == 1
    row = preview2.rows[0]
    assert row["categorization_method"] == "ai" and row["review_status"] == "needs_review"


def test_rules_file_is_valid_json():
    with open(config.RULES_PATH, encoding="utf-8") as handle:
        assert "merchants" in json.load(handle)
