"""Monthly report: one month of spending as structured data and as a printable PDF.

``build_monthly_report`` only *collects* results from the existing modules
(analytics SQL, kpis, insights, budgets, subscription detector, quality,
anomaly detector). It performs no financial arithmetic of its own, so the
report always matches the dashboard for the same month and filters (tested in
tests/test_report.py). ``render_pdf`` only lays that data out.
"""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import date, datetime, timezone

from src import analytics, anomaly_detector, budgets, config, database, insights, kpis, quality, subscription_detector
from src.analytics import Filters
from src.money import format_inr

FONT_DIR = config.PROJECT_ROOT / "assets" / "fonts"

LIMITATIONS = [
    "Figures cover only the statements imported into Spendly; accounts or cards that weren't imported are missing.",
    "Expenditure is spending before refunds. Transfers between your own accounts and credit-card bill payments are excluded.",
    "Categories come from merchant rules (and your corrections); uncategorised payments count as \"Other\".",
    "Recurring costs and spending pace are estimates. \"Unusual\" payments are statistical flags, not fraud findings.",
    "Spendly is not financial advice.",
]


def _records(frame, columns: list[str], limit: int | None = None) -> list[dict]:
    if frame is None or frame.empty:
        return []
    rows = frame[columns].head(limit) if limit else frame[columns]
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in rows.to_dict(orient="records")]


def build_monthly_report(conn, month: str, filters: Filters | None = None, mode: str = "user") -> dict:
    month = budgets.normalize_month(month)
    start, end = budgets.month_bounds(month)
    base = filters or Filters()
    f = replace(base, start_date=start, end_date=end)
    coverage = budgets.month_coverage(conn, month)
    candidates = subscription_detector.detect_for(conn, f)

    summary = kpis.executive_summary(conn, f, candidates)
    trend_filters = replace(base, start_date=date.fromisoformat(budgets.shift_month(month, -5)), end_date=end)
    trend = _records(analytics.monthly_summary(conn, trend_filters),
                     ["month_start", "expenditure_paise", "income_paise", "is_covered", "is_full_month"])
    comp = insights.compare_periods(conn, f)
    story = kpis.explain_change(conn, f, candidates)
    flagged, _ = anomaly_detector.detect_for_view(analytics.transactions(conn), analytics.transactions(conn, f),
                                                  database.anomaly_reviews(conn))
    budget = budgets.month_report(conn, month)
    recurring = subscription_detector.recurring_spend(conn, f, candidates)
    card = quality.scorecard(conn)

    limitations = list(LIMITATIONS)
    if not coverage.is_covered:
        limitations.insert(0, "No imported statement covers this month, so there is no spending data for it.")
    elif not coverage.is_full:
        limitations.insert(0, f"Partial month: statements cover {coverage.covered_from:%d %b} – {coverage.covered_to:%d %b %Y} "
                              f"({coverage.days_covered} of {coverage.days_in_month} days).")
    if any([base.categories, base.transaction_types, base.merchants, base.statuses, base.search]):
        limitations.insert(0, "Filters were applied (see header); budgets and data quality are shown for the whole account.")

    return {
        "month": month,
        "month_label": start.strftime("%B %Y"),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "is_demo": mode == "demo",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "filters": {"categories": list(base.categories), "types": list(base.transaction_types),
                    "merchants": list(base.merchants)},
        "coverage": coverage.as_dict(),
        "kpis": summary,
        "trend": trend,
        "categories": _records(analytics.category_spending(conn, f),
                               ["category", "transaction_count", "expenditure_paise", "share_pct"]),
        "top_merchants": _records(analytics.top_merchants(conn, f, limit=5),
                                  ["merchant", "category", "transaction_count", "expenditure_paise", "share_pct"]),
        "comparison": None if comp is None else {
            "current_label": comp.current_label, "previous_label": comp.previous_label,
            "categories": _records(comp.categories.reindex(comp.categories["change_paise"].abs()
                                                           .sort_values(ascending=False).index),
                                   ["category", "previous_paise", "current_paise", "change_paise", "change_pct"], 8),
        },
        "story": story,
        "budget": {
            "rows": [r for r in budget["rows"] if r["budget_paise"] is not None],
            "overall": budget["overall"],
        },
        "recurring": {
            "estimated_monthly_paise": recurring["estimated_monthly_paise"],
            "actual_recurring_paise": recurring["actual_recurring_paise"],
            "share_of_expenditure_pct": recurring["share_of_expenditure_pct"],
            "items": [{"merchant": c.merchant, "schedule": c.schedule, "median_amount_paise": c.median_amount_paise,
                       "est_monthly_paise": c.est_monthly_paise, "status": c.status}
                      for c in candidates if c.status in {"confirmed", "high_confidence"} and not c.possibly_stopped],
        },
        "quality": {
            "dimensions": [{k: d[k] for k in ("label", "numerator", "denominator", "value_pct", "note")}
                           for d in card["dimensions"]],
            "issues": [{k: i[k] for k in ("label", "severity", "count", "current_count", "implication")}
                       for i in card["issues"] if i["severity"] in {"error", "warning"}],
        },
        "unusual": _records(flagged, ["transaction_date", "merchant", "category", "amount_paise", "reason"], 5),
        "insights": [i.text for i in insights.build_insights(conn, f, candidates, flagged)
                     if i.key not in {"overall_change"}],
        "limitations": limitations,
    }


# --------------------------------------------------------------------- PDF

def _fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    regular, bold = FONT_DIR / "DejaVuSans.ttf", FONT_DIR / "DejaVuSans-Bold.ttf"
    if regular.exists() and bold.exists():
        if "SpendlySans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SpendlySans", str(regular)))
            pdfmetrics.registerFont(TTFont("SpendlySans-Bold", str(bold)))
        return "SpendlySans", "SpendlySans-Bold"
    return "Helvetica", "Helvetica-Bold"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def _signed(paise) -> str:
    if paise is None:
        return "—"
    return ("+" if paise > 0 else "−" if paise < 0 else "") + format_inr(abs(paise))


def render_pdf(data: dict) -> bytes:
    """Lay out ``build_monthly_report`` output as an A4 PDF (prints in black and white)."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font, bold = _fonts()
    rupee = (lambda s: s) if font == "SpendlySans" else (lambda s: s.replace("₹", "Rs. "))
    ink, muted, accent, line = colors.HexColor("#111511"), colors.HexColor("#5b6359"), colors.HexColor("#3f6e00"), colors.HexColor("#d5dbd2")
    s_body = ParagraphStyle("body", fontName=font, fontSize=9, leading=12.5, textColor=ink, alignment=TA_LEFT)
    s_small = ParagraphStyle("small", parent=s_body, fontSize=7.8, leading=10.5, textColor=muted)
    s_h1 = ParagraphStyle("h1", parent=s_body, fontName=bold, fontSize=19, leading=23)
    s_h2 = ParagraphStyle("h2", parent=s_body, fontName=bold, fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=4, textColor=ink)

    def P(text, style=s_body):
        return Paragraph(rupee(str(text)).replace("&", "&amp;").replace("<", "&lt;"), style)

    def table(rows, widths, header=True, align_right_from=1):
        t = Table([[P(c, s_small if (header and i == 0) else s_body) if isinstance(c, str) else c for c in r]
                   for i, r in enumerate(rows)], colWidths=widths, repeatRows=1 if header else 0)
        style = [("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if header:
            style.append(("LINEBELOW", (0, 0), (-1, 0), 0.8, ink))
        t.setStyle(TableStyle(style))
        return t

    k = data["kpis"]
    story = []
    story.append(P(f"Spendly monthly report · {data['month_label']}", s_h1))
    cov = data["coverage"]
    cov_text = ("no statement data" if not cov["is_covered"] else "complete month" if cov["is_full"]
                else f"partial: {cov['covered_from']} to {cov['covered_to']} ({cov['days_covered']} of {cov['days_in_month']} days)")
    filt = [f"{k_}: {', '.join(v)}" for k_, v in data["filters"].items() if v]
    story.append(P(f"Reporting period {data['period']['start']} to {data['period']['end']} · coverage: {cov_text}"
                   + (f" · filters: {'; '.join(filt)}" if filt else "")
                   + f" · generated {data['generated_at'][:16].replace('T', ' ')} UTC", s_small))
    if data["is_demo"]:
        banner = Table([[P("SYNTHETIC DEMO DATA. These transactions were generated for demonstration. "
                           "They are not anyone's real money.", ParagraphStyle("b", parent=s_body, fontName=bold))]],
                       colWidths=[180 * mm])
        banner.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#a66f00")),
                                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4d6")),
                                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [Spacer(1, 4), banner]

    # ---- KPIs
    mom = k["month_over_month"]
    b = k["budget"]
    kpi_rows = [
        ["Expenditure", format_inr(k["expenditure_paise"]), "Income", format_inr(k["income_paise"])],
        ["Net cash flow", _signed(k["net_cash_flow_paise"]), "Refunds", format_inr(k["refunds_paise"])],
        ["Change vs previous month",
         "n/a" if not mom or mom["change_pct"] is None
         else f"{mom['change_pct']:+.1f}% ({_signed(mom['change_paise'])})".replace("-", "−"),
         "Recurring (est. per month)", format_inr(k["recurring"]["estimated_monthly_paise"])],
        ["Budget used", "no budget" if not b else f"{_pct(b['utilisation_pct'])} of {format_inr(b['budget_paise'])}",
         "Transactions", str(k["transaction_count"])],
    ]
    story.append(P("Key figures", s_h2))
    story.append(table(kpi_rows, [44 * mm, 46 * mm, 44 * mm, 46 * mm], header=False))
    story.append(P("Expenditure = spending debits before refunds; net cash flow = all credits − all debits, excluding "
                   "transfers between your own accounts. Same definitions as the Spendly dashboard.", s_small))

    # ---- trend chart
    if data["trend"]:
        story.append(P("Spending trend (last 6 months)", s_h2))
        d = Drawing(180 * mm, 52 * mm)
        chart = VerticalBarChart()
        chart.x, chart.y, chart.width, chart.height = 14 * mm, 9 * mm, 160 * mm, 38 * mm
        chart.data = [[r["expenditure_paise"] / 100 for r in data["trend"]]]
        chart.categoryAxis.categoryNames = [
            date.fromisoformat(str(r["month_start"])[:10]).strftime("%b %y") + ("" if r["is_covered"] else "*")
            for r in data["trend"]]
        chart.bars[0].fillColor = accent
        chart.valueAxis.valueMin = 0
        chart.valueAxis.labelTextFormat = lambda v: f"{v / 1000:.0f}K"
        for axis in (chart.valueAxis.labels, chart.categoryAxis.labels):
            axis.fontName, axis.fontSize = font, 7
        d.add(chart)
        d.add(String(0, 2, rupee("Expenditure in ₹ thousands. * = month not covered by a statement (missing, not zero)."),
                     fontName=font, fontSize=6.5, fillColor=muted))
        story.append(d)

    # ---- change story
    st = data["story"]
    story.append(P("What changed and why", s_h2))
    if st["available"]:
        story.append(P(st["headline"]))
        for point in st["points"]:
            title = point["title"] if point["title"].endswith("?") else point["title"] + "."
            story.append(P(f"• {title} {point['text']}"))
    for c in st["caveats"]:
        story.append(P(c, s_small))

    # ---- categories / merchants
    if data["categories"]:
        story.append(P("Spending by category", s_h2))
        rows = [["Category", "Payments", "Expenditure", "Share"]] + [
            [c["category"], str(c["transaction_count"]), format_inr(c["expenditure_paise"]), _pct(c["share_pct"])]
            for c in data["categories"]]
        story.append(table(rows, [70 * mm, 30 * mm, 45 * mm, 35 * mm]))
    if data["top_merchants"]:
        story.append(P("Top merchants", s_h2))
        rows = [["Merchant", "Category", "Payments", "Expenditure", "Share"]] + [
            [m["merchant"], m["category"], str(m["transaction_count"]), format_inr(m["expenditure_paise"]), _pct(m["share_pct"])]
            for m in data["top_merchants"]]
        story.append(table(rows, [50 * mm, 45 * mm, 22 * mm, 38 * mm, 25 * mm]))
    if data["comparison"] and data["comparison"]["categories"]:
        comp = data["comparison"]
        story.append(P(f"Month-over-month by category ({comp['previous_label']} → {comp['current_label']})", s_h2))
        rows = [["Category", "Previous", "Current", "Change", "Change %"]] + [
            [r["category"], format_inr(r["previous_paise"]), format_inr(r["current_paise"]), _signed(r["change_paise"]),
             "new" if r["change_pct"] is None else f"{r['change_pct']:+.1f}%".replace("-", "−")] for r in comp["categories"]]
        story.append(table(rows, [50 * mm, 33 * mm, 33 * mm, 35 * mm, 29 * mm]))

    # ---- budget
    story.append(P("Budget vs actual", s_h2))
    if data["budget"]["rows"] or data["budget"]["overall"]["overall_budget_paise"] is not None:
        o = data["budget"]["overall"]
        rows = [["Budget", "Budgeted", "Spent", "Remaining", "Used", "Status"]]
        if o["overall_budget_paise"] is not None:
            rows.append(["Overall", format_inr(o["overall_budget_paise"]), format_inr(o["expenditure_paise"]),
                         _signed(o["remaining_paise"]), _pct(o["utilisation_pct"]), o["status"].replace("_", " ")])
        rows += [[r["category"], format_inr(r["budget_paise"]), format_inr(r["actual_paise"]), _signed(r["remaining_paise"]),
                  _pct(r["utilisation_pct"]), r["status"].replace("_", " ")] for r in data["budget"]["rows"]]
        story.append(table(rows, [42 * mm, 28 * mm, 28 * mm, 30 * mm, 22 * mm, 30 * mm]))
        story.append(P("Budgets apply to the whole account (filters don't change them). Variance = spent − budget.", s_small))
    else:
        story.append(P("No budgets were set for this month.", s_small))

    # ---- recurring
    r = data["recurring"]
    story.append(P("Recurring payments", s_h2))
    if r["items"]:
        story.append(P(f"Paid to recurring merchants this month: {format_inr(r['actual_recurring_paise'])}"
                       + (f" ({_pct(r['share_of_expenditure_pct'])} of expenditure)" if r["share_of_expenditure_pct"] is not None else "")
                       + f". Estimated monthly cost of active recurring payments: {format_inr(r['estimated_monthly_paise'])}."))
        rows = [["Merchant", "Schedule", "Typical amount", "Est. per month"]] + [
            [i["merchant"], i["schedule"], format_inr(i["median_amount_paise"]), format_inr(i["est_monthly_paise"])]
            for i in r["items"]]
        story.append(table(rows, [60 * mm, 35 * mm, 42 * mm, 43 * mm]))
    else:
        story.append(P("No active recurring payments were detected.", s_small))

    # ---- unusual + insights
    if data["unusual"]:
        story.append(P("Unusual payments (statistical flags, not fraud findings)", s_h2))
        for u in data["unusual"]:
            story.append(P(f"• {u['transaction_date']} · {u['merchant']}: {u['reason']}"))
    if data["insights"]:
        story.append(P("Other observations", s_h2))
        for text in data["insights"][:6]:
            story.append(P(f"• {text}"))

    # ---- quality + limitations
    q = data["quality"]
    block = [P("Data quality (whole account)", s_h2),
             table([["Dimension", "Result", "Basis"]] + [
                 [d["label"], _pct(d["value_pct"]) if d["value_pct"] is not None else "not measurable",
                  f"{d['numerator']} of {d['denominator']}" if d["denominator"] else (d["note"] or "—")]
                 for d in q["dimensions"]], [60 * mm, 35 * mm, 85 * mm])]
    for i in q["issues"]:
        block.append(P(f"• {i['severity'].title()}: {i['label']} ({i['count']} at import"
                       + (f", {i['current_count']} still flagged" if i["current_count"] is not None else "") + f"). {i['implication']}", s_small))
    story.append(KeepTogether(block))
    story.append(P("Limitations", s_h2))
    for text in data["limitations"]:
        story.append(P(f"• {text}", s_small))

    buffer = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(muted)
        label = "Spendly · " + data["month_label"] + (" · SYNTHETIC DEMO DATA" if data["is_demo"] else "")
        canvas.drawString(15 * mm, 9 * mm, label)
        canvas.drawRightString(195 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"Spendly report {data['month_label']}", author="Spendly")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
