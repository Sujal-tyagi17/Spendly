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


def test_whole_pct_rounds_halves_up_like_the_web_app():
    from src.text import whole_pct
    assert whole_pct(28.5) == "29"
    assert whole_pct(28.49) == "28"
    assert whole_pct(22.5) == "23"
    assert whole_pct(0.5) == "1"
    assert whole_pct(100) == "100"
