"""PDF validation and statement parsing.

Architecture
------------
Every supported layout is a ``StatementParser`` subclass with two methods:

* ``can_parse(document)`` — cheap check: does this PDF look like my format?
* ``parse(document)``     — return the raw rows (strings only).

``PARSERS`` lists them in priority order; ``parse_statement`` tries each one.
To support a new bank, write a new subclass and add it to ``PARSERS``
(see README → "Adding a statement format"). There is intentionally no
"parse anything" magic: an unknown layout gets a clear error instead of
silently wrong numbers.

Uploaded files are processed **in memory** (``io.BytesIO``) and never
written to disk.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field

import pdfplumber

from src import config
from src.privacy import get_logger
from src.transaction_normalizer import DEFAULT_DATE_FORMATS, RawRow, parse_date, DateParseError

log = get_logger(__name__)
# pdfminer's DEBUG output includes raw page content (i.e. transaction text).
# Keep it quiet so statement contents never reach the logs.
logging.getLogger("pdfminer").setLevel(logging.WARNING)


# ------------------------------------------------------------------ errors

class StatementError(Exception):
    """Base class: ``str(error)`` is safe to show to the user."""


class InvalidFileError(StatementError):
    pass


class PasswordRequiredError(StatementError):
    pass


class NoTextError(StatementError):
    pass


class UnsupportedFormatError(StatementError):
    pass


# ---------------------------------------------------------------- document

@dataclass
class PdfDocument:
    pdf: "pdfplumber.PDF"
    page_texts: list[str]

    @property
    def full_text(self) -> str:
        return "\n".join(self.page_texts)


@dataclass
class ParseResult:
    parser_name: str
    parser_label: str
    rows: list[RawRow]
    date_formats: tuple[str, ...]
    period_start: str | None = None
    period_end: str | None = None
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)
    # Printed on the statement (never derived from the rows), when the layout shows them.
    opening_balance_paise: int | None = None
    closing_balance_paise: int | None = None


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_upload(filename: str, data: bytes) -> None:
    """Check extension, size and PDF signature before opening anything."""
    if not filename or not filename.lower().endswith(".pdf"):
        raise InvalidFileError("Only PDF files are supported. Please upload a .pdf statement.")
    if not data:
        raise InvalidFileError("The uploaded file is empty.")
    if len(data) > config.UPLOAD.max_file_size_bytes:
        raise InvalidFileError(
            f"The file is larger than {config.UPLOAD.max_file_size_mb} MB. "
            "Try exporting a shorter date range."
        )
    if not data.lstrip()[:5].startswith(b"%PDF-"):
        raise InvalidFileError("This file does not look like a real PDF (missing PDF header).")


def open_pdf(data: bytes, password: str | None = None) -> PdfDocument:
    try:
        pdf = pdfplumber.open(io.BytesIO(data), password=password or "")
        page_count = len(pdf.pages)
    except Exception as exc:  # pdfminer raises several unrelated exception types
        name = type(exc).__name__
        details = f"{name} {exc!r}".lower()
        if "password" in details or "encrypt" in details:
            raise PasswordRequiredError(
                "This PDF is password-protected. Enter the statement password "
                "(banks often use a mix of your name and date of birth) and try again."
            ) from exc
        log.warning("PDF could not be opened: %s", name)
        raise InvalidFileError("The PDF appears to be damaged or malformed and could not be opened.") from exc

    if page_count == 0:
        raise InvalidFileError("The PDF has no pages.")
    if page_count > config.UPLOAD.max_pages:
        raise InvalidFileError(
            f"The PDF has {page_count} pages; the limit is {config.UPLOAD.max_pages}. "
            "Export a shorter period."
        )
    try:
        texts = [(page.extract_text() or "") for page in pdf.pages]
    except Exception as exc:
        log.warning("Text extraction failed: %s", type(exc).__name__)
        raise InvalidFileError("Text could not be extracted from this PDF.") from exc

    if sum(len(t.strip()) for t in texts) < 20:
        raise NoTextError(
            "No selectable text was found — this looks like a scanned or image-only PDF. "
            "Scanned statements need OCR, which Spendly does not support yet. "
            "Download the statement directly from your bank or UPI app instead."
        )
    return PdfDocument(pdf=pdf, page_texts=texts)


# ------------------------------------------------------------------ helpers

_DATE_TOKEN = (r"(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}[ -][A-Za-z]{3,9}[ -]\d{2,4}"
               r"|[A-Za-z]{3} \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})")
_PERIOD_PATTERNS = [
    re.compile(rf"(?:statement\s+period|period|from)?\s*:?\s*(?P<a>{_DATE_TOKEN})\s*(?:to|-|–)\s*(?P<b>{_DATE_TOKEN})",
               re.IGNORECASE),
]


def find_period(text: str, formats: tuple[str, ...]) -> tuple[str | None, str | None]:
    for pattern in _PERIOD_PATTERNS:
        for match in pattern.finditer(text):
            try:
                start = parse_date(match.group("a").strip(" ,"), formats)
                end = parse_date(match.group("b").strip(" ,"), formats)
            except DateParseError:
                continue
            if start <= end:
                return start.isoformat(), end.isoformat()
    return None, None


_REPORTED_BALANCE = re.compile(
    r"\b(?P<kind>opening|closing)\s+balance\b[^\d\n-]{0,24}(?P<sign>-)?(?P<value>\d[\d,]*\.\d{1,2})\s*(?P<drcr>dr|cr)?\b",
    re.IGNORECASE)


def find_reported_balances(text: str) -> tuple[int | None, int | None]:
    """Opening and closing balances *printed* on the statement, in paise.
    Only an explicit "Opening/Closing Balance <number>" counts; nothing is inferred."""
    found: dict[str, int] = {}
    for match in _REPORTED_BALANCE.finditer(text or ""):
        kind = match.group("kind").lower()
        if kind in found:
            continue
        paise = int(round(float(match.group("value").replace(",", "")) * 100))
        if match.group("sign") or (match.group("drcr") or "").lower() == "dr":
            paise = -paise
        found[kind] = paise
    return found.get("opening"), found.get("closing")


def _cell(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


# ----------------------------------------------------------------- parsers

class StatementParser:
    name = "base"
    label = "Base parser"
    date_formats: tuple[str, ...] = DEFAULT_DATE_FORMATS

    def can_parse(self, document: PdfDocument) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def parse(self, document: PdfDocument) -> ParseResult:  # pragma: no cover - interface
        raise NotImplementedError


class BankTableParser(StatementParser):
    """Bank account statements printed as a table with a header row such as

        Date | Narration | Withdrawal | Deposit | Balance
        Txn Date | Description | Debit | Credit | Balance
        Date | Particulars | Amount | Dr/Cr | Balance

    Column names are matched against synonyms, so the parser follows the
    header rather than assuming fixed positions. Dates are read day-first
    (Indian convention).
    """

    name = "bank_table"
    label = "Bank statement (table with Date / Description / Debit / Credit / Balance)"

    SYNONYMS = {
        "date": ["txn date", "transaction date", "tran date", "date", "value date", "posting date"],
        "description": ["narration", "description", "particulars", "transaction details", "details", "remarks"],
        "debit": ["withdrawal amt", "withdrawal amount", "withdrawals", "withdrawal", "debit amount", "debit", "dr amount", "paid out"],
        "credit": ["deposit amt", "deposit amount", "deposits", "deposit", "credit amount", "credit", "cr amount", "paid in"],
        "amount": ["transaction amount", "amount"],
        "drcr": ["dr/cr", "dr / cr", "cr/dr", "type"],
        "balance": ["closing balance", "balance amount", "available balance", "balance"],
    }
    SKIP_ROW = re.compile(r"^(opening|closing)\s+balance|^total|^b/f|^c/f|brought forward|carried forward", re.IGNORECASE)
    TABLE_SETTINGS = [
        None,  # pdfplumber default: ruled lines
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    ]

    def _map_header(self, cells: list[str]) -> dict[str, int] | None:
        mapping: dict[str, int] = {}
        lowered = [c.lower().strip(" .:") for c in cells]
        for field_name, names in self.SYNONYMS.items():
            for idx, cell in enumerate(lowered):
                if idx in mapping.values():
                    continue
                if any(cell == n or cell.startswith(n) for n in names):
                    # "value date" should not steal the main date column
                    if field_name == "date" and "date" in mapping:
                        continue
                    mapping[field_name] = idx
                    break
        has_amounts = ("debit" in mapping and "credit" in mapping) or "amount" in mapping
        if "date" in mapping and "description" in mapping and has_amounts:
            return mapping
        return None

    def _tables(self, document: PdfDocument):
        cache = getattr(document, "_bank_tables", None)
        if cache is not None:
            return cache
        document._bank_tables = self._find_tables(document)
        return document._bank_tables

    def _find_tables(self, document: PdfDocument):
        for settings in self.TABLE_SETTINGS:
            found = []
            for page_number, page in enumerate(document.pdf.pages, start=1):
                tables = page.extract_tables(settings) if settings else page.extract_tables()
                for table in tables:
                    found.append((page_number, [[_cell(c) for c in row] for row in table if row]))
            if any(self._map_header(row) for _, t in found for row in t[:3]):
                return found
        return []

    def can_parse(self, document: PdfDocument) -> bool:
        return bool(self._tables(document))

    def parse(self, document: PdfDocument) -> ParseResult:
        rows: list[RawRow] = []
        warnings: list[str] = []
        mapping: dict[str, int] | None = None
        width = None
        continuation_lines = 0

        for page_number, table in self._tables(document):
            for cells in table:
                header = self._map_header(cells)
                if header:
                    mapping, width = header, len(cells)
                    continue  # repeated header on every page
                if mapping is None or len(cells) != width:
                    continue
                get = lambda key: cells[mapping[key]] if key in mapping else None  # noqa: E731
                date_text, description = get("date"), get("description")
                if description and self.SKIP_ROW.search(description):
                    continue
                if not date_text and description and rows and not (get("debit") or get("credit") or get("amount")):
                    # Wrapped narration line belongs to the previous transaction.
                    rows[-1].description = f"{rows[-1].description} {description}".strip()
                    continuation_lines += 1
                    continue
                if not any(cells):
                    continue
                rows.append(RawRow(
                    date_text=date_text,
                    description=description,
                    debit_text=get("debit"),
                    credit_text=get("credit"),
                    amount_text=get("amount"),
                    drcr_text=get("drcr"),
                    balance_text=get("balance"),
                    page=page_number,
                    row_number=len(rows) + 1,
                ))

        if continuation_lines:
            warnings.append(f"Joined {continuation_lines} wrapped description line(s) to the row above.")
        start, end = find_period(document.full_text, self.date_formats)
        opening, closing = find_reported_balances(document.full_text)
        return ParseResult(self.name, self.label, rows, self.date_formats, start, end,
                           len(document.pdf.pages), warnings, opening, closing)


class PhonePeParser(StatementParser):
    """PhonePe-style transaction statements, which are printed as text:

        Date            Transaction Details        Type     Amount
        Sep 30, 2026    Paid to Zomato             DEBIT    ₹350
        07:45 pm        Transaction ID T2609301945123456
                        UTR No. 426812345678
                        Paid by XXXXXX1234

    Modeled on the publicly documented PhonePe statement layout. Real exports
    vary between app versions, so verify the preview before importing.
    """

    name = "phonepe"
    label = "PhonePe-style UPI statement (text: date · details · DEBIT/CREDIT · amount)"
    date_formats = ("%b %d, %Y", "%d %b %Y", "%d-%b-%Y")

    LINE = re.compile(
        r"^(?P<date>[A-Z][a-z]{2} \d{1,2}, \d{4})\s+(?P<details>.+?)\s+"
        r"(?P<type>DEBIT|CREDIT|Debit|Credit)\s+(?:₹|INR|Rs\.?)\s?(?P<amount>[\d,]+(?:\.\d{1,2})?)\s*$"
    )
    TXN_ID = re.compile(r"Transaction ID\s*:?\s*(?P<id>[A-Z0-9]{8,})", re.IGNORECASE)

    def can_parse(self, document: PdfDocument) -> bool:
        text = document.full_text
        looks_like = "phonepe" in text.lower() or "transaction details" in text.lower()
        return looks_like and any(self.LINE.match(line.strip()) for line in text.splitlines())

    def parse(self, document: PdfDocument) -> ParseResult:
        rows: list[RawRow] = []
        for page_number, text in enumerate(document.page_texts, start=1):
            for line in text.splitlines():
                line = line.strip()
                match = self.LINE.match(line)
                if match:
                    rows.append(RawRow(
                        date_text=match.group("date"),
                        description=match.group("details"),
                        amount_text=match.group("amount"),
                        drcr_text=match.group("type"),
                        page=page_number,
                        row_number=len(rows) + 1,
                    ))
                    continue
                txn = self.TXN_ID.search(line)
                if txn and rows and rows[-1].reference is None:
                    rows[-1].reference = txn.group("id")
        start, end = find_period(document.full_text, self.date_formats)
        warnings = []
        if rows and not any(r.reference for r in rows):
            warnings.append("No transaction IDs found; duplicate detection will be less certain.")
        return ParseResult(self.name, self.label, rows, self.date_formats, start, end,
                           len(document.pdf.pages), warnings)


PARSERS: list[StatementParser] = [PhonePeParser(), BankTableParser()]


def supported_formats() -> list[str]:
    return [p.label for p in PARSERS]


def parse_statement(data: bytes, filename: str, password: str | None = None) -> ParseResult:
    """Validate, open and parse a PDF held in memory."""
    validate_upload(filename, data)
    document = open_pdf(data, password)
    try:
        for parser in PARSERS:
            if parser.can_parse(document):
                result = parser.parse(document)
                if result.rows:
                    log.info("Parsed statement with %s: %d rows", parser.name, len(result.rows))
                    return result
        raise UnsupportedFormatError(
            "This statement layout is not supported yet. Supported formats: "
            + "; ".join(supported_formats())
            + ". See the README section 'Adding a statement format' to add a parser."
        )
    finally:
        document.pdf.close()
