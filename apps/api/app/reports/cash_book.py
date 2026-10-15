# ruff: noqa: E501  (openapi blocks, long lines of a PDF)
"""The cash book (Livro Caixa) of a month, and the package of the month.

The book is the ledger as the secretaria reads it: the balance carried from the month before, every
entry in the order it was settled with the running balance, and the balance at the end. It is
DERIVED, never stored: the rows are `statement_entries` and the figures are CHECKED against
`statement_summary` of the same period before anything is written (`ReportMismatch` otherwise).

Two forms: a CSV a spreadsheet opens in Brazil (`;`, decimal comma, UTF-8 with BOM) and a PDF. The
package is a ZIP with both and the attachments of the expenses of the month.
"""

import csv
import re
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO, StringIO
from typing import Any

from reportlab.platypus import Flowable, Spacer

from app.reports.closing_report import KIND_LABELS, ReportMismatch, _who
from app.reports.format import (
    brl,
    local_date,
    local_datetime,
    month_name,
    printable,
    reference,
)
from app.reports.layout import (
    Column,
    build_pdf,
    data_table,
    identification_table,
    key_value_table,
    para,
)
from app.storage import StorageNotFoundError

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
MAX_PACKAGE_FILES = 300
MAX_PACKAGE_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class BookRow:
    day: date
    reference_code: int
    kind: str
    description: str
    category: str
    who: str
    entry_cents: int
    exit_cents: int
    balance_cents: int


@dataclass(frozen=True)
class CashBook:
    organization_name: str
    school_name: str
    timezone: str
    period_start: date
    period_end: date
    generated_at: datetime
    personal_data: bool
    opening_cents: int
    closing_cents: int
    rows: list[BookRow]

    @property
    def total_in(self) -> int:
        return sum(r.entry_cents for r in self.rows)

    @property
    def total_out(self) -> int:
        return sum(r.exit_cents for r in self.rows)


def build_cash_book(
    *,
    entries: list[dict[str, Any]],
    summary: dict[str, Any],
    category_names: dict[str, str],
    organization_name: str,
    school_name: str,
    period_start: date,
    period_end: date,
    generated_at: datetime,
    personal_data: bool,
) -> CashBook:
    """The rows in the order of the ledger, checked against the summary of the same period."""
    rows: list[BookRow] = []
    for entry in entries:
        signed = int(entry["signed_amount_cents"])
        rows.append(
            BookRow(
                day=entry["local_date"],
                reference_code=int(entry["reference_code"]),
                kind=str(entry["kind"]),
                description=str(entry["description"] or "").strip() or "—",
                category=category_names.get(str(entry["category_key"]), str(entry["category_key"])),
                who=_who(entry, personal_data),
                entry_cents=signed if signed > 0 else 0,
                exit_cents=-signed if signed < 0 else 0,
                balance_cents=int(entry["running_balance_cents"]),
            )
        )
    opening = int(summary["opening_balance_cents"])
    closing = int(summary["closing_balance_cents"])
    book = CashBook(
        organization_name=organization_name,
        school_name=school_name,
        timezone=str(summary["timezone"]),
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        personal_data=personal_data,
        opening_cents=opening,
        closing_cents=closing,
        rows=rows,
    )
    carried = rows[-1].balance_cents if rows else opening
    if (
        len(rows) != int(summary["entries_count"])
        or opening + book.total_in - book.total_out != closing
        or carried != closing
        or book.total_in != int(summary["total_in_cents"])
        or book.total_out != int(summary["total_out_cents"])
    ):
        raise ReportMismatch("the cash book does not add up to the summary of the period")
    return book


# --- CSV ------------------------------------------------------------------------------------------


def _safe(value: str) -> str:
    """A spreadsheet runs what starts like a formula: the text is shown, never run."""
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def _decimal(cents: int) -> str:
    whole, fraction = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}{whole},{fraction:02d}"


def render_csv(book: CashBook) -> bytes:
    out = StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        ["Data", "Referência", "Tipo", "Descrição", "Categoria", "Origem/Destino", "Entrada",
         "Saída", "Saldo"]
    )  # fmt: skip
    writer.writerow(
        [local_date(book.period_start), "", "", "Saldo anterior", "", "", "", "",
         _decimal(book.opening_cents)]
    )  # fmt: skip
    for r in book.rows:
        writer.writerow(
            [
                local_date(r.day),
                reference(r.reference_code),
                KIND_LABELS.get(r.kind, r.kind),
                _safe(r.description),
                _safe(r.category),
                _safe(r.who),
                _decimal(r.entry_cents) if r.entry_cents else "",
                _decimal(r.exit_cents) if r.exit_cents else "",
                _decimal(r.balance_cents),
            ]
        )
    writer.writerow(
        [local_date(book.period_end), "", "", "Saldo final", "", "", _decimal(book.total_in),
         _decimal(book.total_out), _decimal(book.closing_cents)]
    )  # fmt: skip
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


# --- PDF ------------------------------------------------------------------------------------------


def render_pdf(book: CashBook) -> bytes:
    start = book.period_start
    columns = [
        Column("Data", 9),
        Column("Ref.", 10),
        Column("Descrição", 26),
        Column("Categoria", 15),
        Column("Origem/Destino", 15),
        Column("Entrada", 11, right=True),
        Column("Saída", 11, right=True),
        Column("Saldo", 12, right=True),
    ]
    rows: list[list[str]] = [
        ["", "", "Saldo anterior", "", "", "", "", brl(book.opening_cents)],
        *[
            [
                local_date(r.day)[:5],
                reference(r.reference_code),
                r.description,
                r.category,
                r.who,
                brl(r.entry_cents) if r.entry_cents else "",
                brl(r.exit_cents) if r.exit_cents else "",
                brl(r.balance_cents),
            ]
            for r in book.rows
        ],
    ]
    footer = ["Saldo final", "", "", "", "", brl(book.total_in), brl(book.total_out)]
    footer.append(brl(book.closing_cents))
    story: list[Flowable] = [
        para("Livro Caixa", "title"),
        para(
            f"{month_name(start).capitalize()}  |  {local_date(start)} a {local_date(book.period_end)}",
            "subtitle",
        ),
        Spacer(1, 6),
        identification_table(
            [
                ("APM", book.organization_name),
                ("Escola", book.school_name),
                ("Período", month_name(start)),
                ("Gerado em", local_datetime(book.generated_at, book.timezone)),
            ]
        ),
        Spacer(1, 6),
    ]
    if not book.personal_data:
        story.extend(
            [para("Versão sem dados pessoais: os nomes aparecem pelas iniciais.", "notice"),
             Spacer(1, 4)]
        )  # fmt: skip
    story.append(data_table(columns, rows, footer=footer))
    story.extend(
        [
            Spacer(1, 8),
            key_value_table(
                [
                    ("Saldo anterior", brl(book.opening_cents), "normal"),
                    ("Total de entradas", brl(book.total_in), "normal"),
                    ("Total de saídas", brl(book.total_out), "normal"),
                    ("Saldo final", brl(book.closing_cents), "medium"),
                ]
            ),
            Spacer(1, 4),
            para(
                "O livro mostra o que entrou e saiu do caixa da APM, na ordem em que foi baixado. "
                "Despesas pagas do próprio bolso por um colaborador só entram quando reembolsadas.",
                "small",
            ),
        ]
    )
    period = f"{start.year:04d}-{start.month:02d}"
    return build_pdf(
        story,
        title=f"Livro Caixa {period} - {book.school_name}",
        header=f"{book.organization_name} | {book.school_name} | Livro Caixa de {month_name(start)}",
        footer_code=f"Livro Caixa {period}: {len(book.rows)} lançamentos, saldo final {brl(book.closing_cents)}",
        footer_note="Valores em reais; datas no fuso horário da escola.",
    )


# --- the package of the month ---------------------------------------------------------------------

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _file_name(value: str) -> str:
    """What a name inside the ZIP keeps: letters, digits, dot, dash, underscore (no path)."""
    cleaned = _UNSAFE.sub("_", printable(value)).strip("._") or "arquivo"
    return cleaned[:80]


class PackageTooLarge(Exception):
    """More files or more bytes than a package carries."""


def build_package(
    *,
    period: str,
    csv_bytes: bytes,
    pdf_bytes: bytes,
    attachments: Iterable[tuple[int, str, int, Callable[[], bytes]]],
) -> bytes:
    """The ZIP: the cash book as CSV and PDF, and `anexos/<reference>-<n>-<name>` for each file of
    an expense of the month. Each attachment is `(reference_code, file_name, size, read)`. A file
    the store no longer has does not stop the package: it is listed in `anexos-faltando.txt`."""
    buffer = BytesIO()
    total = len(csv_bytes) + len(pdf_bytes)
    missing: list[str] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"livro-caixa-{period}.csv", csv_bytes)
        archive.writestr(f"livro-caixa-{period}.pdf", pdf_bytes)
        for number, (code, name, size, read) in enumerate(attachments, start=1):
            total += size
            if number > MAX_PACKAGE_FILES or total > MAX_PACKAGE_BYTES:
                raise PackageTooLarge
            label = f"{reference(code)}-{number}-{_file_name(name)}"
            try:
                archive.writestr(f"anexos/{label}", read())
            except StorageNotFoundError:
                missing.append(label)
        if missing:
            archive.writestr(
                "anexos-faltando.txt",
                "Arquivos que não foram encontrados no armazenamento:\r\n" + "\r\n".join(missing),
            )
    return buffer.getvalue()
