"""Small helpers for user-facing wording."""

from __future__ import annotations


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """``plural(1, "payment")`` → ``"1 payment"``; ``plural(3, "payment")`` → ``"3 payments"``.

    The number is formatted with Indian digit grouping (1,23,456) to match the rest of the app.
    """
    n = int(count)
    word = singular if n == 1 else (plural_form or singular + "s")
    return f"{_group_in(n)} {word}"


def _group_in(n: int) -> str:
    sign, s = ("-", str(-n)) if n < 0 else ("", str(n))
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail
