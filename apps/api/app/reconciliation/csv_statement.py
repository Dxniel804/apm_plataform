# ruff: noqa: E501  (patterns)
"""A reader of bank statements in CSV, whatever the bank calls its columns.

Banks export CSV in their own way (the separator, the date format, one column of amounts or one of
credits and one of debits, a decimal comma). A `CsvProfile` says how ONE bank's file is read; it is
detected from the file (`detect`) and kept on the account once the management confirms it. Like the
OFX reader it is bounded (size and lines), has no dependency and executes nothing, and the text of
a line is cleaned (CPF and CNPJ masked) before it is kept.

A CSV has no id for a line: the id is made from the line itself (date, amount, text and the position
among identical lines of the file), so the same line sent in an overlapping file is the same line.
"""

import csv
import hashlib
import io
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.reconciliation.ofx import (
    _E2E,
    _FEE_WORDS,
    MAX_BYTES,
    MAX_LINES,
    OfxLine,
    OfxStatement,
    _decode,
    clean_memo,
)

SAMPLE_ROWS = 5
DELIMITERS = (";", ",", "\t")
_DMY = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s*$")
_YMD = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$")
_MONEY = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?$|^[+-]?\d+(?:[.,]\d{1,2})?$")
_HEADER_DATE = re.compile(r"^data|^dt\b|date", re.IGNORECASE)
_HEADER_MEMO = re.compile(
    r"descri|hist[oó]rico|memo|lan[cç]amento|detalhe|estabelecimento", re.IGNORECASE
)
_HEADER_AMOUNT = re.compile(r"^valor|amount|quantia", re.IGNORECASE)
_HEADER_CREDIT = re.compile(r"cr[eé]dito|entrada", re.IGNORECASE)
_HEADER_DEBIT = re.compile(r"d[eé]bito|sa[ií]da", re.IGNORECASE)
_HEADER_ID = re.compile(r"^(id|identificador|documento|n[uú]mero|c[oó]digo)", re.IGNORECASE)


class CsvError(Exception):
    """The file cannot be used. `code` is stable (the site writes the sentence)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CsvProfile:
    delimiter: str  # ";" "," or a tab
    has_header: bool
    date_col: int
    date_order: str  # "DMY" (31/12/2025) or "YMD" (2025-12-31)
    memo_col: int
    decimal: str  # "," (1.234,56) or "." (1234.56)
    amount_col: int | None = None  # one column, signed...
    debit_positive: bool = False  # ...unless debits are written as positive numbers
    credit_col: int | None = None  # or one column of credits and one of debits
    debit_col: int | None = None
    id_col: int | None = None  # a column with the id the bank gave the line, when there is one

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def profile_from_dict(raw: object) -> CsvProfile:
    """A profile sent by the site or kept on the account, checked: anything odd is refused."""
    if not isinstance(raw, dict):
        raise CsvError("bad_profile")

    def column(name: str, *, required: bool) -> int | None:
        value = raw.get(name)
        if value is None:
            if required:
                raise CsvError("bad_profile")
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 100:
            raise CsvError("bad_profile")
        return value

    delimiter = raw.get("delimiter")
    order = raw.get("date_order")
    decimal = raw.get("decimal")
    if delimiter not in DELIMITERS or order not in ("DMY", "YMD") or decimal not in (",", "."):
        raise CsvError("bad_profile")
    has_header = raw.get("has_header", True)
    debit_positive = raw.get("debit_positive", False)
    if not isinstance(has_header, bool) or not isinstance(debit_positive, bool):
        raise CsvError("bad_profile")
    profile = CsvProfile(
        delimiter=delimiter,
        has_header=has_header,
        date_col=column("date_col", required=True) or 0,
        date_order=order,
        memo_col=column("memo_col", required=True) or 0,
        decimal=decimal,
        amount_col=column("amount_col", required=False),
        debit_positive=debit_positive,
        credit_col=column("credit_col", required=False),
        debit_col=column("debit_col", required=False),
        id_col=column("id_col", required=False),
    )
    if profile.amount_col is None and (profile.credit_col is None or profile.debit_col is None):
        raise CsvError("bad_profile")
    return profile


def _rows(data: bytes, delimiter: str) -> list[list[str]]:
    if len(data) > MAX_BYTES:
        raise CsvError("file_too_large")
    text = _decode(data).lstrip("﻿")
    if "\x00" in text:
        raise CsvError("not_csv")
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[str]] = []
    try:
        for row in reader:
            if any(cell.strip() for cell in row):
                rows.append([cell.strip() for cell in row])
            if len(rows) > MAX_LINES + 50:
                raise CsvError("too_many_lines")
    except csv.Error:
        raise CsvError("not_csv") from None
    return rows


def _day(raw: str, order: str) -> date | None:
    try:
        if order == "DMY":
            found = _DMY.match(raw)
            return None if found is None else date(int(found[3]), int(found[2]), int(found[1]))
        found = _YMD.match(raw)
        return None if found is None else date(int(found[1]), int(found[2]), int(found[3]))
    except ValueError:
        return None


def _cents(raw: str, decimal: str) -> int | None:
    """'-1.234,56', 'R$ 12,30', '(45,00)', '12,30 D' -> cents; None when it is not an amount."""
    text = raw.strip().upper().replace("R$", "").replace(" ", "")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("D"):
        negative, text = True, text[:-1]
    elif text.endswith("C"):
        text = text[:-1]
    text = text.replace(".", "").replace(",", ".") if decimal == "," else text.replace(",", "")
    if not re.fullmatch(r"[+-]?\d{1,12}(\.\d{1,2})?", text):
        return None
    try:
        value = int((Decimal(text) * 100).to_integral_value())
    except InvalidOperation:
        return None
    return -abs(value) if negative else value


def _delimiter_of(data: bytes) -> str:
    sample = _decode(data[:8192]).splitlines()[:20]
    best = max(DELIMITERS, key=lambda d: sum(line.count(d) for line in sample))
    return best


def detect(data: bytes) -> tuple[list[str] | None, list[list[str]], CsvProfile | None]:
    """The header (if any), a few rows to show and the profile this file looks like (None when the
    columns could not be told apart: the management then maps them by hand)."""
    delimiter = _delimiter_of(data)
    rows = _rows(data, delimiter)
    if not rows:
        raise CsvError("no_lines")
    width = max(len(r) for r in rows[:50])
    for order in ("DMY", "YMD"):
        date_hits = [
            sum(1 for r in rows[:60] if i < len(r) and _day(r[i], order) is not None)
            for i in range(width)
        ]
        if max(date_hits) >= 1:
            break
    else:
        return None, rows[: SAMPLE_ROWS + 1], None
    date_col = date_hits.index(max(date_hits))
    first_data = next(
        (n for n, r in enumerate(rows) if date_col < len(r) and _day(r[date_col], order)), 0
    )
    header = rows[first_data - 1] if first_data > 0 else None
    data_rows = rows[first_data:][:60]
    sample = [header, *data_rows[:SAMPLE_ROWS]] if header else data_rows[:SAMPLE_ROWS]
    names = header or [""] * width

    def find(pattern: re.Pattern[str]) -> int | None:
        return next((i for i, n in enumerate(names) if pattern.search(n)), None)

    decimal = ","
    money_cells = [c for r in data_rows for c in r if _MONEY.match(c.replace("R$", "").strip())]
    if (
        money_cells
        and not any("," in c for c in money_cells)
        and any("." in c for c in money_cells)
    ):
        decimal = "."
    credit_col, debit_col = find(_HEADER_CREDIT), find(_HEADER_DEBIT)
    split = credit_col is not None and debit_col is not None
    amount_col = None if split else find(_HEADER_AMOUNT)
    if not split and amount_col is None:
        numeric = [
            i
            for i in range(width)
            if i != date_col
            and sum(1 for r in data_rows if i < len(r) and _cents(r[i], decimal) is not None)
            >= max(1, len(data_rows) // 2)
        ]
        if numeric:
            amount_col = numeric[0]
    if not split and amount_col is None:
        return header, sample, None
    taken = {date_col, amount_col, credit_col if split else None, debit_col if split else None}
    memo_col = find(_HEADER_MEMO)
    if memo_col is None or memo_col in taken:
        text_cols = [i for i in range(width) if i not in taken]
        if not text_cols:
            return header, sample, None
        memo_col = max(text_cols, key=lambda i: sum(len(r[i]) for r in data_rows if i < len(r)))
    id_col = find(_HEADER_ID)
    profile = CsvProfile(
        delimiter=delimiter,
        has_header=header is not None,
        date_col=date_col,
        date_order=order,
        memo_col=memo_col,
        decimal=decimal,
        amount_col=amount_col,
        credit_col=credit_col if split else None,
        debit_col=debit_col if split else None,
        id_col=id_col if id_col not in taken and id_col != memo_col else None,
    )
    return header, sample, profile


def _cell(row: list[str], index: int | None) -> str:
    return row[index] if index is not None and index < len(row) else ""


def parse_csv(data: bytes, profile: CsvProfile) -> OfxStatement:
    rows = _rows(data, profile.delimiter)
    if profile.has_header and rows:
        rows = rows[1:]
    lines: list[OfxLine] = []
    seen: dict[str, int] = {}
    for row in rows:
        posted = _day(_cell(row, profile.date_col), profile.date_order)
        if posted is None:
            continue  # a total, a note or a blank row between the lines
        if profile.amount_col is not None:
            amount = _cents(_cell(row, profile.amount_col), profile.decimal)
            if amount is not None and profile.debit_positive:
                amount = -amount
        else:
            credit = _cents(_cell(row, profile.credit_col), profile.decimal) or 0
            debit = _cents(_cell(row, profile.debit_col), profile.decimal) or 0
            amount = abs(credit) - abs(debit)
        if amount is None:
            raise CsvError("bad_line")
        if amount == 0:
            continue
        raw_memo = _cell(row, profile.memo_col)
        given = _cell(row, profile.id_col).strip()
        if given:
            ref = given[:200]
        else:
            base = f"{posted.isoformat()}|{amount}|{' '.join(raw_memo.split())}"
            seen[base] = seen.get(base, 0) + 1
            ref = "csv:" + hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:24]
        e2e = _E2E.search(raw_memo)
        lines.append(
            OfxLine(
                posted_on=posted,
                amount_cents=amount,
                bank_ref=ref,
                memo=clean_memo(raw_memo),
                end_to_end_id=None if e2e is None else e2e.group(0),
                looks_like_fee=amount < 0 and _FEE_WORDS.search(raw_memo) is not None,
            )
        )
        if len(lines) > MAX_LINES:
            raise CsvError("too_many_lines")
    if not lines:
        raise CsvError("no_lines")
    days = [line.posted_on for line in lines]
    return OfxStatement(
        lines=lines, period_start=min(days), period_end=max(days), closing_balance_cents=None
    )
