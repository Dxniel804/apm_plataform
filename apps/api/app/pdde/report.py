# ruff: noqa: E501  (long lines of a PDF)
"""The PDDE accountability of a year as a "mirror" of the screen of the BB Gestão Ágil: for every line of
the PDDE account, in the order of the bank, the date, the amount, the program, custeio or capital, the
object and the documents. It is what the school keeps and sends to the prefeitura; the classification
itself is made in the bank's system (there is no public interface to do it from here)."""

import csv
from datetime import datetime
from io import StringIO

from reportlab.platypus import Flowable, KeepTogether, Spacer

from app.pdde.schemas import LineOut, ProgramBalance
from app.reports.format import brl, local_date, printable
from app.reports.layout import (
    Column,
    build_pdf,
    data_table,
    identification_table,
    key_value_table,
    para,
)

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
PROGRAMS = {
    "BASICO": "PDDE Básico",
    "EQUIDADE": "PDDE Equidade",
    "QUALIDADE": "PDDE Qualidade",
    "CONECTADO": "Educação Conectada",
}
KINDS = {
    "TRANSFER": "Repasse",
    "EXPENSE": "Despesa",
    "TAX_TO_EEX": "Imposto pago direto à prefeitura",
    "REFUND": "Estorno ou devolução",
    "INELIGIBLE": "Despesa não elegível",
}
STATUS = {"PENDING": "Pendente", "PARTIAL": "Parcial", "DONE": "Concluída"}
CATEGORIES = {"CUSTEIO": "Custeio", "CAPITAL": "Capital"}


def program_name(program: str | None, label: str | None) -> str:
    if program is None:
        return ""
    return (
        label or PROGRAMS.get(program, program)
        if program == "OUTRO"
        else PROGRAMS.get(program, program)
    )


def _documents(line: LineOut) -> str:
    parts = []
    for d in line.documents:
        if d.voided:
            continue
        ident = d.access_key or d.doc_number or d.vendor
        parts.append(f"{ident} ({brl(d.amount_cents)}{'' if d.stamped else ', sem carimbo'})")
    return "; ".join(parts)


def _cells(line: LineOut) -> list[str]:
    c = line.classification
    return [
        local_date(line.posted_on),
        brl(line.amount_cents),
        line.account_nickname,
        "" if c is None else KINDS[c.kind],
        "" if c is None else program_name(c.program, c.program_label),
        "" if c is None or c.economic_category is None else CATEGORIES[c.economic_category],
        "" if c is None or c.object is None else c.object,
        _documents(line),
        STATUS[line.status],
    ]


HEAD = [
    "Data",
    "Valor",
    "Conta",
    "Tipo",
    "Programa",
    "Custeio/Capital",
    "Objeto",
    "Documentos",
    "Situação",
]


def _safe(value: str) -> str:
    """A spreadsheet runs what starts like a formula: the text is shown, never run."""
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def render_csv(lines: list[LineOut]) -> bytes:
    out = StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(HEAD)
    for line in lines:
        cells = [_safe(c) for c in _cells(line)]
        # The amount is a number, not text: a minus sign is not a formula (and Excel reads it as one).
        sign = "-" if line.amount_cents < 0 else ""
        cells[1] = f"{sign}{abs(line.amount_cents) // 100},{abs(line.amount_cents) % 100:02d}"
        writer.writerow(cells)
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def render_pdf(
    *,
    lines: list[LineOut],
    programs: list[ProgramBalance],
    year: int,
    organization_name: str,
    school_name: str,
    generated_at: datetime,
) -> bytes:
    columns = [
        Column("Data", 8), Column("Valor", 10, right=True), Column("Tipo", 10), Column("Programa", 12),
        Column("C/K", 7), Column("Objeto", 17), Column("Documentos", 26), Column("Situação", 8),
    ]  # fmt: skip
    rows = []
    for line in lines:
        c = _cells(line)
        rows.append([c[0][:5], c[1], c[3], c[4], c[5][:1], c[6], c[7], c[8]])
    story: list[Flowable] = [
        para(f"PDDE: prestação de contas de {year}", "title"),
        para("Espelho da classificação feita no BB Gestão Ágil", "subtitle"),
        Spacer(1, 6),
        identification_table(
            [
                ("APM", organization_name),
                ("Escola", school_name),
                ("Ano", str(year)),
                ("Gerado em", generated_at.strftime("%d/%m/%Y %H:%M")),
            ]
        ),
        Spacer(1, 6),
    ]
    if programs:
        story.append(
            key_value_table(
                [
                    (
                        program_name(p.program, p.program_label),
                        f"recebido {brl(p.received_cents)} | custeio {brl(p.spent_custeio_cents)} | capital {brl(p.spent_capital_cents)} | saldo {brl(p.balance_cents)}",
                        "normal",
                    )
                    for p in programs
                ]
            )
        )
        story.append(Spacer(1, 6))
    story.append(
        data_table(columns, rows)
        if rows
        else para("Nenhum lançamento nas contas do PDDE neste ano.", "body")
    )
    story.extend(
        [
            Spacer(1, 10),
            para(
                "Cópias dos documentos enviadas à prefeitura levam a expressão \"Confere com o original\", assinada por um dirigente da UEx "
                "(Res. CD/FNDE 15/2021, art. 33, § 1º, II). Notas, faturas e recibos de despesas de cada programa levam a expressão "
                "\"Pagos com recursos do\" seguida do nome do programa. Guarde os originais por cinco anos, após a aprovação da prestação (art. 28). "
                "O prazo de envio à prefeitura é definido por ela, até 30 de abril do ano seguinte (art. 32).",
                "small",
            ),
            Spacer(1, 22),
            KeepTogether([para("______________________________          ______________________________", "cell"), Spacer(1, 2),
                          para("Presidente da APM                                          Tesoureiro(a)", "cell_bold")]),
        ]
    )  # fmt: skip
    return build_pdf(
        story,
        title=f"PDDE {year}",
        header=printable(f"{organization_name} - {school_name}"),
        footer_code=f"pdde {year}",
        footer_note="Espelho gerado pelo APM Digital; a prestação oficial é feita no BB Gestão Ágil.",
    )
