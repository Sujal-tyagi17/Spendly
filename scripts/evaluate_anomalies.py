"""Evaluate the unusual-payment detectors on the labelled synthetic dataset.

    python -m scripts.evaluate_anomalies          # print the results
    python -m scripts.evaluate_anomalies --write  # also refresh docs/anomaly_evaluation.json
                                                  # and the results table in docs/ANOMALY_EVALUATION.md

Deterministic: the same seed always gives the same dataset and the same numbers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.anomaly_detector import METHOD_LABELS
from src.anomaly_eval import evaluate


def _f(v):
    return "n/a" if v is None else f"{v:.3f}"


def table(result: dict) -> str:
    lines = ["| Method | Params | TP | FP | FN | TN | Precision | Recall | F1 | Not checked | F1 over 5 other seeds (mean ± sd) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in result["results"]:
        t = r["test_default"]
        params = ", ".join(f"{k}={v}" for k, v in r["default_params"].items()) or "per-category thresholds"
        s = r["seeds"]["f1"]
        lines.append(f"| {METHOD_LABELS[r['method']]} | {params} | {t['tp']} | {t['fp']} | {t['fn']} | {t['tn']} | "
                     f"{_f(t['precision'])} | {_f(t['recall'])} | {_f(t['f1'])} | {t['not_checked']} | "
                     f"{_f(s['mean'])} ± {_f(s['sd'])} |")
    lines += ["", "Grid-searched on the tuning half (Jan–Jun), then applied to the test half (Jul–Dec):", "",
              "| Method | Best params on tune half | Tune F1 | Test P | Test R | Test F1 |", "|---|---|---|---|---|---|"]
    for r in result["results"]:
        if "tuned_params" in r:
            best = max(r["grid"], key=lambda g: (g["f1"] or 0, g["precision"] or 0))
            t = r["test_tuned"]
            lines.append(f"| {METHOD_LABELS[r['method']]} | {', '.join(f'{k}={v}' for k, v in r['tuned_params'].items())} | "
                         f"{_f(best['f1'])} | {_f(t['precision'])} | {_f(t['recall'])} | {_f(t['f1'])} |")
    lines += ["", "Flags by kind of payment on the test half (flagged / count):", "",
              "| Method | " + " | ".join(sorted(result["results"][0]["test_default"]["by_kind"])) + " |",
              "|---|" + "---|" * len(result["results"][0]["test_default"]["by_kind"])]
    for r in result["results"]:
        kinds = r["test_default"]["by_kind"]
        lines.append(f"| {METHOD_LABELS[r['method']]} | " +
                     " | ".join(f"{kinds[k]['flagged']}/{kinds[k]['count']}" for k in sorted(kinds)) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    result = evaluate()
    text = table(result)
    print(text)
    if "--write" in sys.argv:
        Path("docs/anomaly_evaluation.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        doc = Path("docs/ANOMALY_EVALUATION.md")
        current = doc.read_text(encoding="utf-8")
        head = current.split("<!-- results -->")[0]
        tail = current.split("<!-- /results -->")[1] if "<!-- /results -->" in current else ""
        doc.write_text(head + "<!-- results -->\n\n" + text + "\n\n<!-- /results -->" + tail, encoding="utf-8")
        print("\nUpdated docs/anomaly_evaluation.json and docs/ANOMALY_EVALUATION.md")
