"""A reader of bank statements in OFX (the format every Brazilian bank can export), version 1.x
(SGML: tags that are never closed) and 2.x (XML).

It is deliberately NOT an XML parser: it looks for the few tags it needs with a regular expression,
which reads both versions the same way and has no entities, no external files and nothing to
execute. The file is bounded (size and number of lines) and what it reads is cleaned: the CPF and
the CNPJ that banks write inside the text of a line are masked, and the text is cut short, because
they are personal data the school does not need to keep.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 5000
MEMO_LENGTH = 120

# The end-to-end id of a Pix: E, then 31 letters and digits.
_E2E = re.compile(r"(?<![0-9A-Za-z])E[0-9A-Za-z]{31}(?![0-9A-Za-z])")
_CPF = re.compile(r"(?<![0-9])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![0-9])")
_CNPJ = re.compile(r"(?<![0-9])\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?![0-9])")
_FEE_WORDS = re.compile(r"tarifa|\btar\b|taxa|iof|anuidade|manuten", re.IGNORECASE)


class OfxError(Exception):
    """The file cannot be used. `code` is stable (the site writes the sentence)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class OfxLine:
    posted_on: date
    amount_cents: int  # positive: money in; negative: money out
    bank_ref: str
    memo: str
    end_to_end_id: str | None
    looks_like_fee: bool


@dataclass(frozen=True)
class OfxStatement:
    lines: list[OfxLine]
    period_start: date
    period_end: date
    closing_balance_cents: int | None


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _tag(block: str, name: str) -> str | None:
    found = re.search(rf"<{name}>\s*([^<\r\n]*)", block, re.IGNORECASE)
    return None if found is None else found.group(1).strip()


def _day(raw: str | None) -> date | None:
    if raw is None or not re.match(r"^\d{8}", raw):
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _cents(raw: str | None) -> int | None:
    """'-150.25' or '-150,25' -> -15025; None when it is not a plain amount (2 decimals at most)."""
    if raw is None:
        return None
    text = raw.strip().replace(" ", "")
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    if not re.fullmatch(r"[+-]?\d{1,12}(\.\d{1,2})?", text):
        return None
    try:
        return int((Decimal(text) * 100).to_integral_value())
    except InvalidOperation:
        return None


def clean_memo(raw: str) -> str:
    """The text of a line without the CPF and the CNPJ in it, on one line, and short."""
    text = " ".join(raw.split())
    text = _CNPJ.sub("***", text)
    text = _CPF.sub("***", text)
    return text[:MEMO_LENGTH]


def parse_ofx(data: bytes) -> OfxStatement:
    if len(data) > MAX_BYTES:
        raise OfxError("file_too_large")
    text = _decode(data)
    if not re.search(r"<OFX>", text, re.IGNORECASE):
        raise OfxError("not_ofx")
    chunks = re.split(r"<STMTTRN>", text, flags=re.IGNORECASE)[1:]
    if len(chunks) > MAX_LINES:
        raise OfxError("too_many_lines")
    lines: list[OfxLine] = []
    for chunk in chunks:
        block = re.split(r"</STMTTRN>|</BANKTRANLIST>", chunk, maxsplit=1, flags=re.IGNORECASE)[0]
        posted = _day(_tag(block, "DTPOSTED"))
        amount = _cents(_tag(block, "TRNAMT"))
        ref = _tag(block, "FITID")
        if posted is None or amount is None or not ref or len(ref) > 255:
            raise OfxError("bad_line")
        if amount == 0:
            continue
        raw_memo = " ".join(part for part in (_tag(block, "NAME"), _tag(block, "MEMO")) if part)
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
    if not lines:
        raise OfxError("no_lines")
    start = _day(_tag(text, "DTSTART")) or min(line.posted_on for line in lines)
    end = _day(_tag(text, "DTEND")) or max(line.posted_on for line in lines)
    balance = re.search(
        r"<LEDGERBAL>(.*?)(?:</LEDGERBAL>|<AVAILBAL>|</STMTRS>|$)", text, re.IGNORECASE | re.DOTALL
    )
    closing = None if balance is None else _cents(_tag(balance.group(1), "BALAMT"))
    return OfxStatement(
        lines=lines,
        period_start=min(start, end),
        period_end=max(start, end),
        closing_balance_cents=closing,
    )
