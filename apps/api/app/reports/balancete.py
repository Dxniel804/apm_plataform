# ruff: noqa: E501  (long lines of a PDF)
"""The monthly balancete, in the shape the accountant of an APM hands the school.

Her sheet has the balance carried from the month before by place (cash, bank, invested), the revenue,
the permanent goods bought, the expenses by purpose, the balance of the month and where the money
is at the end, with the lines of the president and of the treasurer. The point of drawing the same
sheet is the monthly conference: the school puts hers beside the accountant's and every line either
matches or shows where to look.

It is DERIVED, never stored, and the numbers are the ledger's: the rows are `statement_entries` and the
totals are CHECKED against `statement_summary` of the same period before anything is drawn
(`ReportMismatch` otherwise). What the ledger does not know is typed by the treasurer in
`balancete_balances` (migration 0027): what the school already had the day it started, and, at the end
of each month, how much is in cash and how much is invested. The bank is what is left of the total.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from reportlab.platypus import Flowable, KeepTogether, Spacer, Table, TableStyle

from app.reports.closing_report import ReportMismatch
from app.reports.format import brl, local_date, month_name, printable
from app.reports.layout import (
    BAND,
    CONTENT_WIDTH,
    INK,
    RULE,
    build_pdf,
    identification_table,
    para,
)

CAPITAL_PREFIX = "capital_"


@dataclass(frozen=True)
class Place:
    """Where the money is: three places that add up to the balance."""

    bank_cents: int
    cash_cents: int
    investment_cents: int

    @property
    def total_cents(self) -> int:
        return self.bank_cents + self.cash_cents + self.investment_cents


@dataclass(frozen=True)
class Line:
    name: str
    cents: int


@dataclass(frozen=True)
class Balances:
    """What the treasurer typed (the latest row of each kind counts)."""

    opening: dict[str, Any] | None  # OPENING: bank_cents, cash_cents, investment_cents
    previous: dict[str, Any] | None  # MONTH of the month before: cash_cents, investment_cents
    current: dict[str, Any] | None  # MONTH of this month


@dataclass(frozen=True)
class Balancete:
    organization_name: str
    school_name: str
    timezone: str
    period_start: date
    period_end: date
    generated_at: datetime
    opening: Place
    opening_typed: bool  # False: cash and invested were carried (or are zero), nobody typed them
    revenue: list[Line]
    capital: list[Line]
    expenses: list[Line]
    closing: Place
    closing_typed: bool

    @property
    def total_revenue(self) -> int:
        return sum(line.cents for line in self.revenue)

    @property
    def total_capital(self) -> int:
        return sum(line.cents for line in self.capital)

    @property
    def total_expenses(self) -> int:
        return sum(line.cents for line in self.expenses)

    @property
    def balance_of_month(self) -> int:
        return (
            self.opening.total_cents + self.total_revenue - self.total_capital - self.total_expenses
        )


def _grouped(totals: dict[str, int], names: dict[str, str]) -> list[Line]:
    """One line per purpose, the biggest first (the name breaks a tie, so the order is stable)."""
    lines = [Line(names.get(key, key), cents) for key, cents in totals.items() if cents != 0]
    return sorted(lines, key=lambda line: (-line.cents, line.name))


def build_balancete(
    *,
    entries: list[dict[str, Any]],
    summary: dict[str, Any],
    category_names: dict[str, str],
    balances: Balances,
    organization_name: str,
    school_name: str,
    period_start: date,
    period_end: date,
    generated_at: datetime,
) -> Balancete:
    """The sheet of the month, checked against the summary of the same period."""
    revenue: dict[str, int] = {}
    capital: dict[str, int] = {}
    expenses: dict[str, int] = {}
    for entry in entries:
        signed = int(entry["signed_amount_cents"])
        key = str(entry["category_key"])
        if signed > 0:
            revenue[key] = revenue.get(key, 0) + signed
        elif key.startswith(CAPITAL_PREFIX):
            capital[key] = capital.get(key, 0) + -signed
        else:
            expenses[key] = expenses.get(key, 0) + -signed

    # What the school had before the ledger started is part of every balance.
    start_total = 0 if balances.opening is None else _total(balances.opening)
    opening_total = start_total + int(summary["opening_balance_cents"])
    closing_total = start_total + int(summary["closing_balance_cents"])

    # Where it was: the month before if somebody typed it, else what the school started with.
    carried = balances.previous or balances.opening
    cash = 0 if carried is None else int(carried["cash_cents"])
    invested = 0 if carried is None else int(carried["investment_cents"])
    opening_place = Place(opening_total - cash - invested, cash, invested)

    if balances.current is not None:
        cash, invested = (
            int(balances.current["cash_cents"]),
            int(balances.current["investment_cents"]),
        )
    closing_place = Place(closing_total - cash - invested, cash, invested)

    sheet = Balancete(
        organization_name=organization_name,
        school_name=school_name,
        timezone=str(summary["timezone"]),
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        opening=opening_place,
        opening_typed=carried is not None,
        revenue=_grouped(revenue, category_names),
        capital=_grouped(capital, category_names),
        expenses=_grouped(expenses, category_names),
        closing=closing_place,
        closing_typed=balances.current is not None,
    )
    if (
        sum(revenue.values()) != int(summary["total_in_cents"])
        or sheet.total_capital + sheet.total_expenses != int(summary["total_out_cents"])
        or sheet.balance_of_month != closing_total
        or closing_place.total_cents != closing_total
    ):
        raise ReportMismatch("the balancete does not add up to the summary of the period")
    return sheet


def _total(row: dict[str, Any]) -> int:
    return int(row["bank_cents"]) + int(row["cash_cents"]) + int(row["investment_cents"])


# --- PDF ------------------------------------------------------------------------------------------


def _sheet_table(rows: list[tuple[str, str, str]]) -> Table:
    """The accountant's block: a label and an amount, with 'head' rows centred, 'total' rows bold."""
    cells = [
        [
            para(label, "cell_bold" if kind in ("total", "head") else "cell"),
            para(amount, "cell_bold_right" if kind == "total" else "cell_right"),
        ]
        for kind, label, amount in rows
    ]
    table = Table(cells, colWidths=[CONTENT_WIDTH * 0.72, CONTENT_WIDTH * 0.28])
    style: list[tuple[Any, ...]] = [
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for index, (kind, _label, _amount) in enumerate(rows):
        if kind == "head":
            style.extend(
                [("BACKGROUND", (0, index), (-1, index), BAND), ("SPAN", (0, index), (-1, index))]
            )
        if kind == "total":
            style.extend(
                [
                    ("BACKGROUND", (0, index), (-1, index), BAND),
                    ("LINEABOVE", (0, index), (-1, index), 0.9, INK),
                ]
            )
    table.setStyle(TableStyle(style))
    return table


def _lines(items: list[Line]) -> list[tuple[str, str, str]]:
    return [("line", line.name, brl(line.cents)) for line in items]


def render_pdf(sheet: Balancete) -> bytes:
    start = sheet.period_start
    rows: list[tuple[str, str, str]] = [
        ("head", "SALDO ANTERIOR", ""),
        ("line", "Caixa", brl(sheet.opening.cash_cents)),
        ("line", "Banco c/ movimento", brl(sheet.opening.bank_cents)),
        ("line", "Em aplicação", brl(sheet.opening.investment_cents)),
        ("total", "Total em caixa", brl(sheet.opening.total_cents)),
        ("head", "RECEITAS", ""),
        *(_lines(sheet.revenue) or [("line", "Nenhuma receita no mês", brl(0))]),
        ("total", "TOTAL DE RECEITAS", brl(sheet.total_revenue)),
        (
            "total",
            "SALDO ANTERIOR + RECEITAS",
            brl(sheet.opening.total_cents + sheet.total_revenue),
        ),
        ("head", "(-) BENS PERMANENTES", ""),
        *_lines(sheet.capital),
        ("total", "TOTAL DE BENS PERMANENTES", brl(sheet.total_capital)),
        ("head", "(-) DESPESAS", ""),
        *(_lines(sheet.expenses) or [("line", "Nenhuma despesa no mês", brl(0))]),
        ("total", "TOTAL DAS DESPESAS", brl(sheet.total_expenses)),
        ("total", "SALDO DO MÊS", brl(sheet.balance_of_month)),
        ("head", "DEMONSTRAÇÃO DO SALDO FINAL", ""),
        ("line", "Em caixa", brl(sheet.closing.cash_cents)),
        ("line", "Em banco", brl(sheet.closing.bank_cents)),
        ("line", "Em aplicação", brl(sheet.closing.investment_cents)),
        ("total", "SALDO FINAL", brl(sheet.closing.total_cents)),
    ]
    story: list[Flowable] = [
        para(printable(f"BALANCETE REFERENTE AO PERÍODO DE {month_name(start).upper()}"), "title"),
        para(printable(sheet.organization_name), "subtitle"),
        Spacer(1, 6),
        identification_table(
            [
                ("APM", sheet.organization_name),
                ("Escola", sheet.school_name),
                ("Período", f"{local_date(start)} a {local_date(sheet.period_end)}"),
            ]
        ),
        Spacer(1, 6),
        _sheet_table(rows),
    ]
    notes: list[str] = []
    if not sheet.closing_typed:
        notes.append(
            "Caixa e aplicação deste mês não foram informados: foram mantidos os valores do mês anterior."
            if sheet.opening_typed
            else "Caixa e aplicação não foram informados: todo o saldo aparece em banco."
        )
    if sheet.closing.bank_cents < 0 or sheet.opening.bank_cents < 0:
        notes.append("Atenção: o banco ficou negativo. Confira os valores de caixa e de aplicação.")
    for note in notes:
        story.extend([Spacer(1, 6), para(note, "notice")])
    story.extend(
        [
            Spacer(1, 22),
            KeepTogether(
                [
                    para("Local e data: ______________________________________", "cell"),
                    Spacer(1, 34),
                    _signatures(),
                ]
            ),
        ]
    )
    return build_pdf(
        story,
        title=f"Balancete {start.strftime('%Y-%m')}",
        header=printable(f"{sheet.organization_name} - {sheet.school_name}"),
        footer_code=f"balancete {start.strftime('%Y-%m')}",
        footer_note="Gerado a partir do livro caixa do APM Digital; confira com o balancete da contabilidade.",
    )


def _signatures() -> Table:
    cells = [
        [
            para("______________________________", "cell"),
            para("______________________________", "cell"),
        ],
        [para("PRESIDENTE", "cell_bold"), para("TESOUREIRO(A)", "cell_bold")],
    ]
    table = Table(cells, colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2])
    table.setStyle(
        TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    )
    return table
