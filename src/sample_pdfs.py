"""Builders for *synthetic* statement PDFs (used by the demo files and tests).

Requires ``reportlab`` (a dev dependency, see requirements-dev.txt). These
PDFs imitate common layouts so the parsers can be exercised end to end; they
are not copies of any real bank's statement.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
]


def _rupee_font() -> tuple[str, str]:
    """Use a font with the ₹ glyph when available, else fall back to 'Rs.'."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("DejaVu", candidate))
            return "DejaVu", "₹"
    return "Helvetica", "Rs."


def bank_statement_pdf(rows: list[dict], *, period: tuple[date, date] | None = None,
                       account_holder: str = "DEMO USER", wrap_first_description: bool = False,
                       opening_balance: int | None = None, closing_balance: int | None = None) -> bytes:
    """rows: dicts with date (date), description, debit/credit/balance (paise or None)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("<b>Demo Bank of India — Savings Account Statement</b>", styles["Title"]),
        Paragraph(f"Account holder: {account_holder} &nbsp;&nbsp; Account no: XXXXXXXX4521", styles["Normal"]),
    ]
    if period:
        story.append(Paragraph(
            f"Statement Period: {period[0].strftime('%d %b %Y')} to {period[1].strftime('%d %b %Y')}",
            styles["Normal"]))
    if opening_balance is not None:
        story.append(Paragraph(f"Opening Balance: {opening_balance / 100:,.2f}", styles["Normal"]))
    if closing_balance is not None:
        story.append(Paragraph(f"Closing Balance: {closing_balance / 100:,.2f}", styles["Normal"]))
    story.append(Spacer(1, 6 * mm))

    def money(p):
        return "" if p is None else f"{p / 100:,.2f}"

    data = [["Date", "Narration", "Withdrawal", "Deposit", "Balance"]]
    for i, r in enumerate(rows):
        desc = r["description"]
        data.append([r["date"].strftime("%d/%m/%Y"), desc[:58], money(r.get("debit")),
                     money(r.get("credit")), money(r.get("balance"))])
        if wrap_first_description and i == 0:
            data.append(["", "(continued) REMARKS: MONTHLY PAYMENT", "", "", ""])

    table = Table(data, colWidths=[22 * mm, 92 * mm, 24 * mm, 24 * mm, 24 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F0EE")),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def phonepe_statement_pdf(rows: list[dict], *, period: tuple[date, date] | None = None) -> bytes:
    """rows: dicts with date (date), details, direction ('debit'/'credit'), amount (paise), txn_id."""
    font, symbol = _rupee_font()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    def header(y):
        c.setFont(font, 14)
        c.drawString(40, y, "PhonePe — Transaction Statement")
        y -= 18
        c.setFont(font, 9)
        if period:
            c.drawString(40, y, f"{period[0].strftime('%b %d, %Y')} - {period[1].strftime('%b %d, %Y')}")
            y -= 22
        c.setFont(font, 9)
        c.drawString(40, y, "Date")
        c.drawString(130, y, "Transaction Details")
        c.drawString(400, y, "Type")
        c.drawString(470, y, "Amount")
        return y - 18

    y = header(height - 50)
    for r in rows:
        if y < 80:
            c.showPage()
            y = header(height - 50)
        c.setFont(font, 9)
        amount = f"{r['amount'] / 100:,.2f}".rstrip("0").rstrip(".")
        c.drawString(40, y, r["date"].strftime("%b %d, %Y"))
        c.drawString(130, y, r["details"])
        c.drawString(400, y, r["direction"].upper())
        c.drawString(470, y, f"{symbol}{amount}")
        c.setFont(font, 7)
        c.drawString(40, y - 11, r.get("time", "10:15 am"))
        c.drawString(130, y - 11, f"Transaction ID {r['txn_id']}")
        c.drawString(130, y - 21, "Paid by XXXXXX4521" if r["direction"] == "debit" else "Credited to XXXXXX4521")
        y -= 40
    c.save()
    return buffer.getvalue()


def image_only_pdf() -> bytes:
    """A PDF with a drawn shape but no text — mimics a scanned statement."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.rect(50, 50, 300, 200, fill=1)
    c.save()
    return buffer.getvalue()


def unrelated_text_pdf() -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "Minutes of the weekly project meeting. Nothing financial here at all.")
    c.save()
    return buffer.getvalue()
