"""From the TEXT of a Brazilian receipt (nota fiscal, cupom, recibo) to the fields an expense needs.

Pure and deterministic: no model, no network, so it is tested on its own and does not change when
the model changes. The engine only produces text; this module finds, in that text, the total, the
date, the CNPJ and the name of the shop, and says how sure it is of each (0 to 1):

* 0.9: found next to its label ("VALOR A PAGAR", "EMISSÃO", a CNPJ whose check digits are right);
* 0.7: found without a label, but only one candidate;
* 0.4-0.5: a guess (the largest amount of the page, a date that is not near a label).

A field it cannot find is simply absent. It never invents one.
"""

import datetime as dt
import re
from dataclasses import dataclass

# 1.234,56  87,50  0,99 (Brazilian). A dot before two digits (87.50) is also read (some printers).
_MONEY = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d+\.\d{2})(?![\d])")
_DATE = re.compile(r"(?<!\d)(\d{2})[/.\-](\d{2})[/.\-](\d{4}|\d{2})(?!\d)")
_CNPJ = re.compile(r"(?<!\d)(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?!\d)")

# Lines that carry a total, from the strongest label to the weakest. The first label that matches
# wins; inside it, the last amount of the line (or of the next line) is the total.
_TOTAL_LABELS: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"VALOR\s+(?:A\s+)?PAGAR|TOTAL\s+A\s+PAGAR|VALOR\s+TOTAL|TOTAL\s+GERAL"), 0.9),
    (re.compile(r"\bTOTAL\b(?!\s+(?:DE\s+)?(?:ITENS|TRIBUTOS|IMPOSTOS|DESC))"), 0.8),
)
# A line with one of these is never the total, even if it says TOTAL.
_NOT_TOTAL = re.compile(
    r"SUB\s*-?\s*TOTAL|DESCONTO|TROCO|TRIBUT|IMPOST|ICMS|PIS|COFINS|ACRESC|FRETE"
)
_DATE_LABEL = re.compile(r"EMISS|DATA|EMITID")
_SHOP_NOISE = re.compile(
    r"CNPJ|CPF|IE\b|INSC|CUPOM|NOTA|FISCAL|DANFE|NFC|NF-?E|SAT\b|EXTRATO|CONSUMIDOR|DOCUMENTO|"
    r"AUXILIAR|VIA\b|RECIBO|COMPROVANTE|RECEB|QUANTIA|REFERENTE|IMPORT"
)


@dataclass(frozen=True)
class Parsed:
    value: object
    confidence: float


def to_cents(token: str) -> int | None:
    """'1.234,56' -> 123456; '87.50' -> 8750; None when it is not an amount."""
    clean = token.strip()
    if "," in clean:
        whole, _, cents = clean.replace(".", "").partition(",")
    elif re.fullmatch(r"\d+\.\d{2}", clean):
        whole, _, cents = clean.partition(".")
    else:
        return None
    if not whole.isdigit() or not cents.isdigit() or len(cents) != 2:
        return None
    return int(whole) * 100 + int(cents)


def _amounts(line: str) -> list[int]:
    found = [to_cents(m.group(1)) for m in _MONEY.finditer(line)]
    return [value for value in found if value is not None and value > 0]


def find_total(text: str) -> Parsed | None:
    lines = [" ".join(line.upper().split()) for line in text.splitlines()]
    for pattern, confidence in _TOTAL_LABELS:
        for index, line in enumerate(lines):
            if not pattern.search(line) or _NOT_TOTAL.search(line):
                continue
            amounts = _amounts(line)
            if not amounts and index + 1 < len(lines) and not _NOT_TOTAL.search(lines[index + 1]):
                amounts = _amounts(lines[index + 1])  # the number is on the next line
            if amounts:
                return Parsed(amounts[-1], confidence)
    every = [value for line in lines if not _NOT_TOTAL.search(line) for value in _amounts(line)]
    if every:
        return Parsed(max(every), 0.4)
    return None


def _valid_date(day: int, month: int, year: int) -> dt.date | None:
    if year < 100:
        year += 2000
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def find_date(text: str) -> Parsed | None:
    lines = [line.upper() for line in text.splitlines()]
    labelled: list[dt.date] = []
    other: list[dt.date] = []
    for line in lines:
        for match in _DATE.finditer(line):
            found = _valid_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if found is None:
                continue
            (labelled if _DATE_LABEL.search(line) else other).append(found)
    if labelled:
        return Parsed(labelled[0].isoformat(), 0.9)
    if other:
        return Parsed(other[0].isoformat(), 0.7 if len(set(other)) == 1 else 0.5)
    return None


def cnpj_is_valid(digits: str) -> bool:
    """The two check digits of a CNPJ (14 digits, not all equal)."""
    if len(digits) != 14 or not digits.isdigit() or len(set(digits)) == 1:
        return False

    def check(base: str, weights: list[int]) -> int:
        total = sum(int(d) * w for d, w in zip(base, weights, strict=True))
        rest = total % 11
        return 0 if rest < 2 else 11 - rest

    first = check(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = check(digits[:12] + str(first), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[12:] == f"{first}{second}"


def find_cnpj(text: str) -> tuple[Parsed | None, int | None]:
    """The CNPJ of the shop (formatted) and the index of the line it was on."""
    lines = text.splitlines()
    best: tuple[int, Parsed, int] | None = None
    for index, line in enumerate(lines):
        for match in _CNPJ.finditer(line):
            digits = "".join(match.groups())
            valid = cnpj_is_valid(digits)
            labelled = "CNPJ" in line.upper()
            score = (2 if valid else 0) + (1 if labelled else 0)
            if score == 0:
                continue  # 14 digits that are not a CNPJ and say nothing: a barcode, a number
            formatted = f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
            confidence = 0.9 if valid else 0.4
            if best is None or score > best[0]:
                best = (score, Parsed(formatted, confidence), index)
    if best is None:
        return None, None
    return best[1], best[2]


def _letters_ratio(line: str) -> float:
    compact = line.replace(" ", "")
    return sum(ch.isalpha() for ch in compact) / len(compact) if compact else 0.0


def _shop_candidate(line: str) -> str | None:
    clean = " ".join(line.split())
    if (
        len(clean) < 3
        or len(clean) > 80
        or _letters_ratio(clean) < 0.6
        or _SHOP_NOISE.search(clean.upper())
    ):
        return None
    return clean


def find_merchant(text: str, cnpj_line: int | None) -> Parsed | None:
    lines = text.splitlines()
    if cnpj_line is not None:
        # The name is printed just above the CNPJ (or on its line, before it).
        same = re.split(r"CNPJ", lines[cnpj_line], flags=re.IGNORECASE)[0]
        found = _shop_candidate(same)
        if found:
            return Parsed(found, 0.7)
        for line in reversed(lines[max(0, cnpj_line - 3) : cnpj_line]):
            found = _shop_candidate(line)
            if found:
                return Parsed(found, 0.7)
    for line in lines[:8]:
        found = _shop_candidate(line)
        if found:
            return Parsed(found, 0.5)
    return None


def parse_receipt(text: str) -> dict[str, Parsed]:
    """The fields found in `text`, by the names of the contract (`docs/expenses.md`)."""
    fields: dict[str, Parsed] = {}
    total = find_total(text)
    if total:
        fields["total_cents"] = total
    date = find_date(text)
    if date:
        fields["date"] = date
    cnpj, cnpj_line = find_cnpj(text)
    if cnpj:
        fields["document_number"] = cnpj
    merchant = find_merchant(text, cnpj_line)
    if merchant:
        fields["merchant"] = merchant
    return fields
