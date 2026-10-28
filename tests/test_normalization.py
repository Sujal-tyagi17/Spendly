from datetime import date

import pytest

from src.duplicates import fingerprint, mark_duplicates
from src.merchant_normalizer import normalize_merchant
from src.money import AmountParseError, format_inr, format_inr_compact, parse_amount
from src.transaction_normalizer import DateParseError, RawRow, normalize_row, parse_date
from src.data_validator import check_running_balance, summarize
from src.transaction_normalizer import normalize_rows


# ------------------------------------------------------------------ dates

@pytest.mark.parametrize("text, expected", [
    ("05/07/2026", date(2026, 7, 5)),      # day-first
    ("05-07-2026", date(2026, 7, 5)),
    ("05 Jul 2026", date(2026, 7, 5)),
    ("05-Jul-26", date(2026, 7, 5)),
    ("Jul 5, 2026", date(2026, 7, 5)),
    ("2026-07-05", date(2026, 7, 5)),
    ("05/07/26", date(2026, 7, 5)),         # two-digit year not misread as year 0026
])
def test_parse_date_supported_formats(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["", None, "31/02/2026", "not a date", "13/13/2026"])
def test_parse_date_invalid(text):
    with pytest.raises(DateParseError):
        parse_date(text)


def test_ambiguous_date_is_not_guessed():
    # If a parser declared both day-first and month-first formats, 03/04/2026 is ambiguous.
    with pytest.raises(DateParseError, match="ambiguous"):
        parse_date("03/04/2026", ("%d/%m/%Y", "%m/%d/%Y"))
    # ...but 25/04/2026 can only be day-first, so it's fine.
    assert parse_date("25/04/2026", ("%d/%m/%Y", "%m/%d/%Y")) == date(2026, 4, 25)


# ---------------------------------------------------------------- amounts

@pytest.mark.parametrize("text, paise, hint", [
    ("₹1,23,456.50", 12345650, None),
    ("Rs. 500", 50000, None),
    ("INR 1,000.5", 100050, None),
    ("500.00 Dr", 50000, "debit"),
    ("1,200.00 Cr", 120000, "credit"),
    ("-250.75", 25075, "debit"),
    ("(99.99)", 9999, "debit"),
    ("0.1", 10, None),
])
def test_parse_amount(text, paise, hint):
    assert parse_amount(text) == (paise, hint)


def test_amounts_have_no_float_rounding_error():
    # 0.1 + 0.2 != 0.3 in floats; in paise it is exact.
    assert parse_amount("0.10")[0] + parse_amount("0.20")[0] == parse_amount("0.30")[0]


@pytest.mark.parametrize("text", ["abc", "12.345", "", "1.2.3", None])
def test_parse_amount_invalid(text):
    with pytest.raises(AmountParseError):
        parse_amount(text)


def test_format_inr_indian_grouping():
    assert format_inr(12345650) == "₹1,23,457"
    assert format_inr(12345650, decimals=True) == "₹1,23,456.50"
    assert format_inr(99900) == "₹999"
    assert format_inr(-150000) == "-₹1,500"
    assert format_inr(10_00_00_000_00) == "₹10,00,00,000"
    assert format_inr_compact(1_50_000_00) == "₹1.5L"
    assert format_inr_compact(12_500_00) == "₹12.5K"


# --------------------------------------------------------------- row level

def test_normalize_row_debit_credit_columns():
    rec = normalize_row(RawRow("05/07/2026", "UPI/DR/412345678901/ZOMATO", debit_text="350.00",
                               credit_text="", balance_text="10,000.00"), 0)
    assert rec.is_valid
    assert rec.direction == "debit" and rec.amount_paise == 35000 and rec.balance_paise == 1000000
    assert "412345678901" not in rec.description and "XXXX8901" in rec.description


def test_normalize_row_single_amount_with_drcr():
    rec = normalize_row(RawRow("05/07/2026", "Salary", amount_text="50,000.00", drcr_text="Cr"), 0)
    assert rec.direction == "credit" and rec.amount_paise == 5000000


@pytest.mark.parametrize("row, expected_issue", [
    (RawRow("05/07/2026", "x", debit_text="10", credit_text="10"), "both debit and credit"),
    (RawRow("05/07/2026", "x"), "Amount: missing"),
    (RawRow("garbage", "x", debit_text="10"), "Date"),
    (RawRow("05/07/2026", "", debit_text="10"), "Description: missing"),
    (RawRow("05/07/2026", "x", amount_text="10"), "cannot tell whether"),
    (RawRow("05/07/2026", "x", debit_text="ten"), "Amount"),
])
def test_invalid_rows_are_flagged_not_raised(row, expected_issue):
    rec = normalize_row(row, 0)
    assert not rec.is_valid
    assert any(expected_issue in issue for issue in rec.issues)


# --------------------------------------------------------------- merchants

@pytest.mark.parametrize("description, merchant", [
    ("ZOMATO*ORDER123", "Zomato"),
    ("UPI/DR/412345678901/ZOMATO/YESB/zomato@ybl/Payment", "Zomato"),
    ("SWIGGY INSTAMART", "Swiggy Instamart"),
    ("UPI/DR/1234/SWIGGY/ICIC/swiggy@icici", "Swiggy"),
    ("POS 4111XXXXXXXX1111 AMZN MKTPLACE", "Amazon"),
    ("AMAZON PRIME MEMBERSHIP", "Amazon Prime"),
    ("Paid to Sharma General Store", "Sharma General Store"),
    ("UPI/DR/600000000034/SHARMA GENERAL STORE/SBIN/sharmastore@okaxis/Payment", "Sharma General Store"),
    ("ACH/DR/600000000123/NETFLIX.COM", "Netflix"),
])
def test_merchant_normalization(description, merchant):
    assert normalize_merchant(description).merchant == merchant


def test_unrelated_similar_names_are_not_merged():
    # Fuzzy matching would merge these; deterministic rules keep them apart.
    assert normalize_merchant("AMAZING BAKERY").merchant == "Amazing Bakery"
    assert normalize_merchant("OLAKSHA TEXTILES").merchant != "Ola"


# -------------------------------------------------------------- duplicates

def _row(date_, amount, desc, merchant, balance=None):
    return {"transaction_date": date_, "direction": "debit", "amount_paise": amount,
            "normalized_merchant": merchant, "balance_paise": balance, "has_strong_key": balance is not None,
            "fingerprint": fingerprint(date_, "debit", amount, desc, balance)}


def test_exact_duplicate_in_file_needs_matching_balance():
    rows = [_row("2026-07-01", 100, "TEA", "Tea", 5000), _row("2026-07-01", 100, "TEA", "Tea", 5000)]
    mark_duplicates(rows)
    assert [r["duplicate_status"] for r in rows] == ["none", "exact_in_file"]


def test_identical_payments_without_balance_are_only_possible_duplicates():
    # Two ₹20 chai payments the same day are legitimate — never auto-removed.
    rows = [_row("2026-07-01", 2000, "CHAI", "Chai"), _row("2026-07-01", 2000, "CHAI", "Chai")]
    mark_duplicates(rows)
    assert [r["duplicate_status"] for r in rows] == ["none", "possible"]


def test_same_amount_different_balance_is_possible_not_exact():
    rows = [_row("2026-07-01", 2000, "CHAI A", "Chai", 9000), _row("2026-07-01", 2000, "CHAI B", "Chai", 7000)]
    mark_duplicates(rows)
    assert rows[1]["duplicate_status"] == "possible"


def test_different_days_are_not_duplicates():
    rows = [_row("2026-07-01", 2000, "CHAI", "Chai"), _row("2026-07-02", 2000, "CHAI", "Chai")]
    mark_duplicates(rows)
    assert {r["duplicate_status"] for r in rows} == {"none"}


# ----------------------------------------------------------- data quality

def test_running_balance_check_detects_missing_row():
    rows = [RawRow("01/07/2026", "a", credit_text="1000", balance_text="1000"),
            RawRow("02/07/2026", "b", debit_text="100", balance_text="900"),
            RawRow("04/07/2026", "d", debit_text="50", balance_text="650")]  # a ₹200 row is missing
    check = check_running_balance(normalize_rows(rows))
    assert check.checked_pairs == 2 and check.mismatches == 1


def test_running_balance_check_handles_newest_first_statements():
    rows = [RawRow("02/07/2026", "b", debit_text="100", balance_text="900"),
            RawRow("01/07/2026", "a", credit_text="1000", balance_text="1000")]
    check = check_running_balance(normalize_rows(rows))
    assert check.mismatches == 0 and check.order == "newest_first"


def test_quality_summary_counts():
    rows = [RawRow("01/07/2026", "a", debit_text="10"), RawRow("bad", "b", debit_text="10")]
    summary = summarize(normalize_rows(rows))
    assert (summary.total_extracted, summary.valid, summary.invalid) == (2, 1, 1)
    assert summary.issue_counts == {"Date": 1}
