"""Run the parser evaluation and print a Markdown report.

    python -m scripts.evaluate_parsers            # synthetic + any local real fixtures
    python -m scripts.evaluate_parsers --write    # also update docs/PARSER_EVALUATION.md (synthetic only)

Real statements (consented, anonymised) go in data/parser_eval/real/ as
<name>.pdf + <name>.expected.csv. They are git-ignored and never written to the docs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.parser_eval import run_all

COLUMNS = [("fixture", "Fixture"), ("parser", "Parser"), ("pages", "Pages"), ("expected_rows", "Expected"),
           ("extracted_rows", "Extracted"), ("missed_rows", "Missed"), ("spurious_rows", "Spurious"),
           ("date_accuracy_pct", "Date %"), ("amount_accuracy_pct", "Amount %"),
           ("description_exact_pct", "Desc exact %"), ("description_similarity_pct", "Desc similarity %"),
           ("balance_reconciliation_pct", "Balance chain %")]


def _fmt(v):
    return "n/a" if v is None else str(v)


def report(include_real: bool) -> str:
    results, summary = run_all(include_real)
    lines = ["| " + " | ".join(c[1] for c in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for r in results:
        name = r["fixture"] if r["kind"] == "synthetic" else "real statement (local)"
        lines.append("| " + " | ".join(_fmt(name if k == "fixture" else r[k]) for k, _ in COLUMNS) + " |")
    s, real = summary["synthetic"], summary["real"]
    lines += ["", f"**Synthetic (pooled, {s['expected_rows']} rows, {s['fixtures']} fixtures):** count agreement "
              f"{s['count_agreement']}, dates {_fmt(s['date_accuracy_pct'])}%, amounts {_fmt(s['amount_accuracy_pct'])}%, "
              f"descriptions exact {_fmt(s['description_exact_pct'])}%, balance chain {_fmt(s['balance_reconciliation_pct'])}%.",
              f"**Real statements evaluated:** {real['fixtures']}."]
    return "\n".join(lines)


if __name__ == "__main__":
    write = "--write" in sys.argv
    text = report(include_real=not write)
    print(text)
    if write:
        doc = Path("docs/PARSER_EVALUATION.md")
        current = doc.read_text(encoding="utf-8")
        head = current.split("<!-- results -->")[0]
        tail = current.split("<!-- /results -->")[1] if "<!-- /results -->" in current else ""
        doc.write_text(head + "<!-- results -->\n\n" + text + "\n\n<!-- /results -->" + tail, encoding="utf-8")
        print(f"\nUpdated {doc}")
