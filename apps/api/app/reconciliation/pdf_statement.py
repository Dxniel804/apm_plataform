# ruff: noqa: E501  (patterns)
"""A best-effort reader of bank statements in PDF (the ones that have text in them).

A PDF is a drawing, not data: this reader looks, line by line, for "a date, a text and an amount",
which most banks print. What it reads is NEVER trusted as much as an OFX: every line it makes is
marked for review and the management must confer it before it becomes an entry of the ledger. A line
where it cannot tell money in from money out is left out (never guessed). A scanned PDF (a picture
of paper, with no text) is not read: ask the bank for an OFX or a CSV.

Bounded (size, pages, lines); nothing in the file is executed, only its text is read.
"""

import hashlib
import re
from datetime import date
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.reconciliation.csv_statement import _cents
from app.reconciliation.ofx import (
    _E2E,
    _FEE_WORDS,
    MAX_BYTES,
    MAX_LINES,
    OfxLine,
    OfxStatement,
    clean_memo,
)

MAX_PAGES = 40
_LINE = re.compile(r"^\s*(\d{2})/(\d{2})(?:/(\d{4}|\d{2}))?\s+(.*)$")
_MONEY = re.compile(r"[-+]?\(?(?:R\$)?\s?\d{1,3}(?:\.\d{3})*,\d{2}\)?(?:\s?[CD])?(?![\w,])")
_YEAR = re.compile(r"\b\d{2}/\d{2}/(\d{4})\b")
_OUT_WORDS = re.compile(
    r"pagamento|pgto|enviad|d[eé]bito|compra|saque|tarifa|\btar\b|taxa|iof|transfer[eê]ncia enviada|pix enviado",
    re.IGNORECASE,
)
_IN_WORDS = re.compile(
    r"recebid|cr[eé]dito|dep[oó]sito|rendimento|estorno|transfer[eê]ncia recebida|pix recebido",
    re.IGNORECASE,
)


class PdfError(Exception):
    """The file cannot be used. `code` is stable (the site writes the sentence)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sign(token: str, memo: str) -> int | None:
    """-1 out, +1 in, None when it cannot be told."""
    upper = token.strip().upper()
    if upper.startswith("-") or upper.startswith("(") or upper.endswith("D"):
        return -1
    if upper.startswith("+") or upper.endswith("C"):
        return 1
    out, into = _OUT_WORDS.search(memo), _IN_WORDS.search(memo)
    if out and not into:
        return -1
    if into and not out:
        return 1
    return None


def parse_pdf(data: bytes) -> OfxStatement:
    if len(data) > MAX_BYTES * 2:
        raise PdfError("file_too_large")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise PdfError("pdf_encrypted")
        if len(reader.pages) > MAX_PAGES:
            raise PdfError("pdf_too_many_pages")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError):
        raise PdfError("not_pdf") from None
    if not text.strip():
        raise PdfError("pdf_without_text")
    found_year = _YEAR.search(text)
    lines: list[OfxLine] = []
    seen: dict[str, int] = {}
    for raw in text.splitlines():
        match = _LINE.match(raw)
        if match is None:
            continue
        day, month, year, rest = match.groups()
        money = list(_MONEY.finditer(rest))
        if not money:
            continue
        if year is None:
            if found_year is None:
                raise PdfError("pdf_year_unknown")
            full_year = int(found_year.group(1))
        else:
            full_year = int(year) + (2000 if len(year) == 2 else 0)
        try:
            posted = date(full_year, int(month), int(day))
        except ValueError:
            continue
        token = money[0].group(0)
        memo = rest[: money[0].start()].strip()
        sign = _sign(token, memo)
        cents = _cents(re.sub(r"[-+()]", "", token), ",")
        if sign is None or cents is None or cents == 0:
            continue
        amount = sign * abs(cents)
        base = f"{posted.isoformat()}|{amount}|{' '.join(memo.split())}"
        seen[base] = seen.get(base, 0) + 1
        e2e = _E2E.search(rest)
        lines.append(
            OfxLine(
                posted_on=posted,
                amount_cents=amount,
                bank_ref="pdf:" + hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:24],
                memo=clean_memo(memo),
                end_to_end_id=None if e2e is None else e2e.group(0),
                looks_like_fee=amount < 0 and _FEE_WORDS.search(memo) is not None,
            )
        )
        if len(lines) > MAX_LINES:
            raise PdfError("too_many_lines")
    if not lines:
        raise PdfError("no_lines")
    days = [line.posted_on for line in lines]
    return OfxStatement(
        lines=lines, period_start=min(days), period_end=max(days), closing_balance_cents=None
    )
