# ruff: noqa: E501  (long lines of a PDF layout)
"""The one-page report for the community (the council, the parents and the teachers).

It answers three questions in plain words: how much came in and from where, how much went out and
on what, and how much is left. No person is named (only categories), so it can be printed, put on a
wall or read in a meeting. It is derived from the same entries as the cash book and CHECKED against
`statement_summary` before it is drawn (`ReportMismatch` otherwise).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from reportlab.platypus import Flowable, Spacer

from app.reports.closing_report import ReportMismatch
from app.reports.format import brl, local_date, local_datetime, month_name, percent
from app.reports.layout import (
    Column,
    build_pdf,
    data_table,
    identification_table,
    key_value_table,
    para,
)

TOP_CATEGORIES = 7  # the rest is summed in "Outros", so the report always fits one page


@dataclass(frozen=True)
class Slice:
    name: str
    cents: int


@dataclass(frozen=True)
class CommunityReport:
    organization_name: str
    school_name: str
    timezone: str
    period_start: date
    period_end: date
    generated_at: datetime
    opening_cents: int
    closing_cents: int
    total_in: int
    total_out: int
    incoming: list[Slice]
    outgoing: list[Slice]
    goal_cents: int | None
    expected_contributions: int | None
    paid_contributions: int
    contributions_cents: int


def _slices(totals: dict[str, int], names: dict[str, str]) -> list[Slice]:
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    top = [Slice(names.get(key, key), cents) for key, cents in ordered[:TOP_CATEGORIES]]
    rest = sum(cents for _, cents in ordered[TOP_CATEGORIES:])
    return [*top, Slice("Outros", rest)] if rest else top


def build_community_report(
    *,
    entries: list[dict[str, Any]],
    summary: dict[str, Any],
    category_names: dict[str, str],
    organization_name: str,
    school_name: str,
    period_start: date,
    period_end: date,
    generated_at: datetime,
    goal_cents: int | None,
    expected_contributions: int | None,
    paid_contributions: int,
) -> CommunityReport:
    incoming: dict[str, int] = {}
    outgoing: dict[str, int] = {}
    for entry in entries:
        signed = int(entry["signed_amount_cents"])
        key = str(entry["category_key"])
        if signed > 0:
            incoming[key] = incoming.get(key, 0) + signed
        elif signed < 0:
            outgoing[key] = outgoing.get(key, 0) - signed
    total_in, total_out = sum(incoming.values()), sum(outgoing.values())
    opening, closing = int(summary["opening_balance_cents"]), int(summary["closing_balance_cents"])
    if (
        total_in != int(summary["total_in_cents"])
        or total_out != int(summary["total_out_cents"])
        or opening + total_in - total_out != closing
    ):
        raise ReportMismatch("the community report does not add up to the summary of the period")
    return CommunityReport(
        organization_name=organization_name,
        school_name=school_name,
        timezone=str(summary["timezone"]),
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        opening_cents=opening,
        closing_cents=closing,
        total_in=total_in,
        total_out=total_out,
        incoming=_slices(incoming, category_names),
        outgoing=_slices(outgoing, category_names),
        goal_cents=goal_cents,
        expected_contributions=expected_contributions,
        paid_contributions=paid_contributions,
        contributions_cents=int(summary["contributions_in_cents"]),
    )


def _table(title: str, slices: list[Slice], total: int, empty: str) -> list[Flowable]:
    story: list[Flowable] = [para(title, "h2")]
    if not slices:
        return [*story, para(empty, "body")]
    rows = [[s.name, percent(s.cents, total), brl(s.cents)] for s in slices]
    columns = [
        Column("Categoria", 60),
        Column("Parte", 18, right=True),
        Column("Valor", 22, right=True),
    ]
    return [*story, data_table(columns, rows, footer=["Total", "", brl(total)])]


def render_community_pdf(report: CommunityReport) -> bytes:
    start = report.period_start
    story: list[Flowable] = [
        para("Prestação de contas para a comunidade", "title"),
        para(
            f"{month_name(start).capitalize()}  |  {local_date(start)} a {local_date(report.period_end)}",
            "subtitle",
        ),
        Spacer(1, 6),
        identification_table(
            [
                ("APM", report.organization_name),
                ("Escola", report.school_name),
                ("Gerado em", local_datetime(report.generated_at, report.timezone)),
            ]
        ),
        Spacer(1, 6),
        key_value_table(
            [
                ("Tínhamos no início do mês", brl(report.opening_cents), "normal"),
                ("Entrou no mês", brl(report.total_in), "normal"),
                ("Saiu no mês", brl(report.total_out), "normal"),
                ("Temos agora", brl(report.closing_cents), "big"),
            ]
        ),
    ]
    story.extend(
        _table(
            "De onde veio o dinheiro", report.incoming, report.total_in, "Nada entrou neste mês."
        )
    )
    story.extend(
        _table(
            "Em que o dinheiro foi gasto",
            report.outgoing,
            report.total_out,
            "Nada foi gasto neste mês.",
        )
    )
    if report.goal_cents:
        story.append(para("Meta do mês", "h2"))
        lines = [
            ("Meta de arrecadação", brl(report.goal_cents), "normal"),
            (
                "Arrecadado em contribuições",
                f"{brl(report.contributions_cents)} ({percent(report.contributions_cents, report.goal_cents)} da meta)",
                "normal",
            ),
        ]
        if report.expected_contributions:
            lines.append(
                (
                    "Famílias que contribuíram",
                    f"{report.paid_contributions} de {report.expected_contributions} esperadas",
                    "normal",
                )
            )
        story.append(key_value_table(lines))
    story.extend(
        [
            Spacer(1, 8),
            para(
                "Este relatório mostra o caixa próprio da APM (contribuições, campanhas e despesas). "
                "Não inclui verbas de programas do governo, que têm prestação de contas própria. "
                "Nenhum nome de pessoa aparece aqui. O Livro Caixa detalhado fica com a diretoria.",
                "small",
            ),
        ]
    )
    period = f"{start.year:04d}-{start.month:02d}"
    return build_pdf(
        story,
        title=f"Prestação de contas {period} - {report.school_name}",
        header=f"{report.organization_name} | {report.school_name} | Prestação de contas de {month_name(start)}",
        footer_code=f"Saldo em {local_date(report.period_end)}: {brl(report.closing_cents)}",
        footer_note="Valores em reais; datas no fuso horário da escola.",
    )
