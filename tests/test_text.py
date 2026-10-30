from src.text import plural


def test_plural_singular_and_plural():
    assert plural(1, "payment") == "1 payment"
    assert plural(0, "payment") == "0 payments"
    assert plural(2, "payment") == "2 payments"
    assert plural(1, "category", "categories") == "1 category"
    assert plural(3, "category", "categories") == "3 categories"


def test_plural_uses_indian_grouping():
    assert plural(123456, "row") == "1,23,456 rows"
    assert plural(1000, "row") == "1,000 rows"
